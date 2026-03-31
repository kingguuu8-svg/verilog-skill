#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

STAGE3_SCRIPTS = (Path(__file__).resolve().parents[1] / ".." / "verilog-waveform-observation" / "scripts").resolve()
if str(STAGE3_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STAGE3_SCRIPTS))

from waveform_support import maybe_build_vcd_index  # noqa: E402

from simulation_support import (
    build_runtime_env,
    build_vivado_runtime_env,
    classify_backend_failure,
    classify_run_failure,
    collect_wave_files,
    detect_runtime_failure_markers,
    detect_xpm_usage,
    ensure_temp_dir,
    filter_hdl_locations,
    make_stage_result,
    normalize_inputs,
    parse_locations,
    probe_backend,
    probe_vvp_backend,
    probe_xsim_backend,
    resolve_vivado_xpm_sources,
    run_command_in_dir,
    simulation_support_range,
)
from tb_event_support import build_tb_event_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-2 Verilog/SystemVerilog simulation executor")
    parser.add_argument("inputs", nargs="+", help="Source files or .f file lists")
    parser.add_argument(
        "--backend",
        choices=["iverilog", "xsim"],
        default="iverilog",
        help="Simulation backend to execute",
    )
    parser.add_argument("--top", help="Optional top module name")
    parser.add_argument(
        "--include-dir",
        action="append",
        default=[],
        help="Include directory",
    )
    parser.add_argument(
        "--define",
        action="append",
        default=[],
        help="Macro definition in NAME or NAME=VALUE form",
    )
    parser.add_argument(
        "--runtime-arg",
        action="append",
        default=[],
        help="Runtime plusarg or backend argument",
    )
    parser.add_argument("--wave-file", help="Requested waveform file path")
    parser.add_argument("--output-dir", help="Directory for compiled image and logs")
    parser.add_argument(
        "--wave-index",
        choices=["auto", "always", "never"],
        default="never",
        help="Generate sidecar VCD indexes after simulation",
    )
    return parser.parse_args()


def resolve_output_dir(path_text: str | None) -> Path:
    if path_text:
        candidate = Path(path_text).expanduser()
        if not candidate.is_absolute():
            candidate = (Path.cwd() / candidate).resolve()
        else:
            candidate = candidate.resolve()
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    return Path(tempfile.mkdtemp(prefix="run-", dir=ensure_temp_dir())).resolve()


def resolve_wave_file(path_text: str | None, output_dir: Path) -> Path | None:
    if not path_text:
        return None
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = (output_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def write_log(path: Path, stdout: str, stderr: str) -> None:
    path.write_text(
        "=== STDOUT ===\n"
        f"{stdout}"
        "\n=== STDERR ===\n"
        f"{stderr}",
        encoding="utf-8",
    )


def ensure_backend_log(path: Path, stdout: str, stderr: str) -> None:
    if path.exists():
        return
    write_log(path, stdout, stderr)


def build_iverilog_compile_command(
    backend_path: str,
    normalized: dict,
    top: str | None,
    output_image: Path,
) -> list[str]:
    command = [backend_path, "-g2012", "-o", str(output_image)]
    if top:
        command.extend(["-s", top])
    for include_dir in normalized["include_dirs"]:
        command.extend(["-I", include_dir])
    for define in normalized["defines"]:
        command.append(f"-D{define}")
    command.extend(normalized["source_files"])
    return command


def build_vvp_run_command(
    vvp_path: str,
    output_image: Path,
    runtime_args: list[str],
    wave_file: Path | None,
) -> list[str]:
    command = [vvp_path, str(output_image)]
    if wave_file is not None:
        wave_text = wave_file.as_posix()
        command.extend([f"+WAVE_FILE={wave_text}", f"+wave={wave_text}"])
    command.extend(runtime_args)
    return command


def sanitize_top_name(top: str | None) -> str | None:
    if top is None:
        return None
    top_name = top.strip()
    if not top_name:
        return None
    if "." in top_name:
        top_name = top_name.split(".")[-1]
    return top_name


def build_xvlog_command(
    toolchain: dict,
    normalized: dict,
    compile_log: Path,
    source_files: list[str],
) -> list[str]:
    command = [
        toolchain["backend_tools"]["xvlog"],
        "--relax",
        "-sv",
        "-work",
        "work",
        "--log",
        str(compile_log),
    ]
    for include_dir in normalized["include_dirs"]:
        command.extend(["-i", include_dir])
    for define in normalized["defines"]:
        command.extend(["-d", define])
    command.extend(source_files)
    return command


def build_xelab_command(toolchain: dict, top: str, snapshot_name: str, elaborate_log: Path) -> list[str]:
    return [
        toolchain["backend_tools"]["xelab"],
        "--relax",
        "-debug",
        "typical",
        "-mt",
        "2",
        "-L",
        "unisims_ver",
        "-L",
        "unimacro_ver",
        "-L",
        "secureip",
        f"work.{top}",
        "work.glbl",
        "-s",
        snapshot_name,
        "--log",
        str(elaborate_log),
    ]


def build_xsim_run_command(
    toolchain: dict,
    snapshot_name: str,
    runtime_args: list[str],
    wave_file: Path | None,
    run_log: Path,
) -> list[str]:
    command = [
        toolchain["backend_tools"]["xsim"],
        snapshot_name,
        "--runall",
        "--onfinish",
        "quit",
        "--onerror",
        "quit",
        "--log",
        str(run_log),
    ]
    if wave_file is not None and wave_file.suffix.lower() == ".wdb":
        command.extend(["--wdb", wave_file.as_posix()])
    elif wave_file is not None:
        wave_text = wave_file.as_posix()
        command.extend(["--testplusarg", f"WAVE_FILE={wave_text}"])
        command.extend(["--testplusarg", f"wave={wave_text}"])

    for runtime_arg in runtime_args:
        if runtime_arg.startswith("-"):
            command.append(runtime_arg)
            continue
        normalized_arg = runtime_arg[1:] if runtime_arg.startswith("+") else runtime_arg
        command.extend(["--testplusarg", normalized_arg])
    return command


def make_input_error_payload(args: argparse.Namespace, details: dict, support_range: dict) -> dict:
    return {
        "status": details["status"],
        "message": details["message"],
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": {
            "compile": None,
            "run": None,
        },
        "details": details,
        "interpretation": "simulation inputs are invalid before backend execution",
    }


def make_environment_error_payload(args: argparse.Namespace, backend_result: dict, support_range: dict) -> dict:
    stage = make_stage_result(
        backend=backend_result["backend"],
        status=backend_result["status"],
        category=backend_result["category"],
        message=backend_result["message"],
        stdout=backend_result.get("stdout", ""),
        stderr=backend_result.get("stderr", ""),
    )
    checks = {
        "compile": None,
        "run": None,
    }
    if backend_result["backend"] == "vvp":
        checks["run"] = stage
    else:
        checks["compile"] = stage
    return {
        "status": backend_result["status"],
        "message": backend_result["message"],
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": checks,
        "interpretation": "required simulation backend is unavailable or not runnable",
    }


def finalize_payload(
    *,
    args: argparse.Namespace,
    support_range: dict,
    compile_stage: dict | None,
    run_stage: dict | None,
    status: str,
    message: str,
    interpretation: str,
    artifacts: dict,
) -> dict:
    return {
        "status": status,
        "message": message,
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": {
            "compile": compile_stage,
            "run": run_stage,
        },
        "artifacts": artifacts,
        "interpretation": interpretation,
    }


def make_artifacts(
    *,
    output_dir: Path,
    compiled_image: Path,
    compile_log: Path,
    run_log: Path,
    wave_file: Path | None,
    backend: str,
    elaborate_log: Path | None = None,
) -> dict:
    artifacts = {
        "backend": backend,
        "output_dir": str(output_dir),
        "compiled_image": str(compiled_image),
        "compile_log": str(compile_log),
        "run_log": str(run_log),
        "wave_files": [],
        "wave_indexes": [],
        "wave_index_errors": [],
        "tb_event_index": None,
        "tb_event_summary": None,
    }
    if elaborate_log is not None:
        artifacts["elaborate_log"] = str(elaborate_log)
    if wave_file is not None:
        artifacts["requested_wave_file"] = str(wave_file)
    return artifacts


def enrich_wave_indexes(artifacts: dict, mode: str) -> None:
    if mode == "never":
        return
    for wave_text in artifacts.get("wave_files", []):
        wave_path = Path(wave_text)
        index_path, index_error = maybe_build_vcd_index(wave_path, mode=mode)
        if index_path is not None:
            artifacts["wave_indexes"].append(str(index_path))
        if index_error is not None:
            artifacts["wave_index_errors"].append(
                {
                    "wave_file": str(wave_path),
                    "error": index_error,
                }
            )


def enrich_tb_event_index(artifacts: dict, run_stdout: str, run_stderr: str) -> None:
    output_dir = Path(artifacts["output_dir"])
    run_log = Path(artifacts["run_log"])
    index_path, summary = build_tb_event_index(
        run_log=run_log,
        stdout=run_stdout,
        stderr=run_stderr,
        output_path=output_dir / "tb-events.json",
    )
    if index_path is not None:
        artifacts["tb_event_index"] = str(index_path)
        artifacts["tb_event_summary"] = summary


def handle_requested_wave_missing(
    *,
    args: argparse.Namespace,
    support_range: dict,
    artifacts: dict,
    compile_stage: dict,
    run_command: list[str],
    run_stdout: str,
    run_stderr: str,
    backend_name: str,
) -> tuple[dict, int]:
    run_stage = make_stage_result(
        backend=backend_name,
        status="run_error",
        category="wave_missing",
        message="Simulation finished without emitting the requested wave file",
        command=run_command,
        stdout=run_stdout,
        stderr=run_stderr,
        locations=[],
    )
    payload = finalize_payload(
        args=args,
        support_range=support_range,
        compile_stage=compile_stage,
        run_stage=run_stage,
        status="run_error",
        message="Simulation ran but did not produce the requested wave artifact",
        interpretation="the testbench or simulator did not honor the requested wave path",
        artifacts=artifacts,
    )
    return payload, 1


def handle_runtime_completion(
    *,
    args: argparse.Namespace,
    support_range: dict,
    artifacts: dict,
    compile_stage: dict,
    run_command: list[str],
    run_stdout: str,
    run_stderr: str,
    run_returncode: int,
    backend_name: str,
) -> tuple[dict, int]:
    failure_markers = detect_runtime_failure_markers(run_stdout, run_stderr)
    if run_returncode != 0 or failure_markers:
        status, category = classify_run_failure(run_stdout, run_stderr, run_returncode)
        runtime_message = "Simulation runtime failed"
        interpretation = "the testbench executed but reported a runtime failure or exited non-zero"
        if failure_markers and run_returncode == 0:
            runtime_message = "Simulation runtime reported failure markers"
            interpretation = "the testbench completed but its own logs declared a failure condition"
        run_stage = make_stage_result(
            backend=backend_name,
            status=status,
            category=category,
            message=runtime_message,
            command=run_command,
            stdout=run_stdout,
            stderr=run_stderr,
            locations=filter_hdl_locations(parse_locations("\n".join(part for part in [run_stdout, run_stderr] if part))),
        )
        payload = finalize_payload(
            args=args,
            support_range=support_range,
            compile_stage=compile_stage,
            run_stage=run_stage,
            status=status,
            message="Simulation runtime failed after compile/elaboration passed",
            interpretation=interpretation,
            artifacts=artifacts,
        )
        return payload, 1

    run_stage = make_stage_result(
        backend=backend_name,
        status="ok",
        category="run_ok",
        message="Simulation runtime completed",
        command=run_command,
        stdout=run_stdout,
        stderr=run_stderr,
        locations=[],
    )
    payload = finalize_payload(
        args=args,
        support_range=support_range,
        compile_stage=compile_stage,
        run_stage=run_stage,
        status="ok",
        message="Simulation compile and runtime checks passed",
        interpretation="simulation executed successfully and any emitted waveform artifacts were captured",
        artifacts=artifacts,
    )
    return payload, 0


def run_iverilog_backend(
    args: argparse.Namespace,
    normalized: dict,
    support_range: dict,
    output_dir: Path,
    wave_file: Path | None,
) -> tuple[dict, int]:
    compile_log = output_dir / "compile.log"
    run_log = output_dir / "run.log"
    compiled_image = output_dir / "sim.out"
    artifacts = make_artifacts(
        output_dir=output_dir,
        compiled_image=compiled_image,
        compile_log=compile_log,
        run_log=run_log,
        wave_file=wave_file,
        backend="iverilog",
    )
    if wave_file is not None and wave_file.exists():
        wave_file.unlink()

    iverilog_info = probe_backend("iverilog")
    if iverilog_info["status"] != "ok":
        return make_environment_error_payload(args, iverilog_info, support_range), 2

    vvp_info = probe_vvp_backend(iverilog_info)
    if vvp_info["status"] != "ok":
        return make_environment_error_payload(args, vvp_info, support_range), 2

    env = build_runtime_env()
    compile_command = build_iverilog_compile_command(
        iverilog_info["backend_path"],
        normalized,
        sanitize_top_name(args.top),
        compiled_image,
    )
    compile_proc = run_command_in_dir(compile_command, env, output_dir)
    write_log(compile_log, compile_proc.stdout, compile_proc.stderr)

    compile_text = "\n".join(part for part in [compile_proc.stdout, compile_proc.stderr] if part)
    if compile_proc.returncode != 0:
        status, category = classify_backend_failure(compile_text)
        compile_stage = make_stage_result(
            backend="iverilog",
            status=status,
            category=category,
            message="Icarus compile/elaboration failed",
            command=compile_command,
            stdout=compile_proc.stdout,
            stderr=compile_proc.stderr,
            locations=filter_hdl_locations(parse_locations(compile_text)),
        )
        payload = finalize_payload(
            args=args,
            support_range=support_range,
            compile_stage=compile_stage,
            run_stage=None,
            status=status,
            message="Simulation compile/elaboration failed before runtime execution",
            interpretation="fix compile or elaboration issues before expecting simulator output or wave artifacts",
            artifacts=artifacts,
        )
        exit_code = 2 if status in {"environment_error", "input_error"} else 1
        return payload, exit_code

    compile_stage = make_stage_result(
        backend="iverilog",
        status="ok",
        category="compile_ok",
        message="Icarus compile/elaboration passed",
        command=compile_command,
        stdout=compile_proc.stdout,
        stderr=compile_proc.stderr,
        locations=[],
    )

    run_command = build_vvp_run_command(vvp_info["backend_path"], compiled_image, args.runtime_arg, wave_file)
    run_proc = run_command_in_dir(run_command, env, output_dir)
    write_log(run_log, run_proc.stdout, run_proc.stderr)

    artifacts["wave_files"] = collect_wave_files(output_dir, wave_file)
    enrich_wave_indexes(artifacts, args.wave_index)
    enrich_tb_event_index(artifacts, run_proc.stdout, run_proc.stderr)
    if wave_file is not None and not wave_file.exists():
        return handle_requested_wave_missing(
            args=args,
            support_range=support_range,
            artifacts=artifacts,
            compile_stage=compile_stage,
            run_command=run_command,
            run_stdout=run_proc.stdout,
            run_stderr=run_proc.stderr,
            backend_name="vvp",
        )

    return handle_runtime_completion(
        args=args,
        support_range=support_range,
        artifacts=artifacts,
        compile_stage=compile_stage,
        run_command=run_command,
        run_stdout=run_proc.stdout,
        run_stderr=run_proc.stderr,
        run_returncode=run_proc.returncode,
        backend_name="vvp",
    )


def run_xsim_backend(
    args: argparse.Namespace,
    normalized: dict,
    support_range: dict,
    output_dir: Path,
    wave_file: Path | None,
) -> tuple[dict, int]:
    top_name = sanitize_top_name(args.top)
    if top_name is None:
        details = {
            "status": "input_error",
            "category": "invalid_input",
            "message": "The xsim backend requires --top so xelab can build the intended snapshot",
        }
        return make_input_error_payload(args, details, support_range), 2

    xsim_info = probe_xsim_backend()
    if xsim_info["status"] != "ok":
        return make_environment_error_payload(args, xsim_info, support_range), 2

    snapshot_name = f"{top_name}_behav"
    compile_log = output_dir / "compile.log"
    elaborate_log = output_dir / "elaborate.log"
    run_log = output_dir / "run.log"
    compiled_image = output_dir / "xsim.dir" / snapshot_name / "xsimk.exe"
    artifacts = make_artifacts(
        output_dir=output_dir,
        compiled_image=compiled_image,
        compile_log=compile_log,
        elaborate_log=elaborate_log,
        run_log=run_log,
        wave_file=wave_file,
        backend="xsim",
    )
    if wave_file is not None and wave_file.exists():
        wave_file.unlink()

    extra_sources: list[str] = []
    if detect_xpm_usage(normalized["source_files"]):
        extra_sources.extend(resolve_vivado_xpm_sources(xsim_info["vivado_root"]))
    extra_sources.append(xsim_info["glbl_path"])
    source_files = list(dict.fromkeys([*normalized["source_files"], *extra_sources]))

    env = build_vivado_runtime_env()
    compile_command = build_xvlog_command(xsim_info, normalized, compile_log, source_files)
    compile_proc = run_command_in_dir(compile_command, env, output_dir)
    ensure_backend_log(compile_log, compile_proc.stdout, compile_proc.stderr)

    compile_text = "\n".join(part for part in [compile_proc.stdout, compile_proc.stderr] if part)
    if compile_proc.returncode != 0:
        status, category = classify_backend_failure(compile_text)
        compile_stage = make_stage_result(
            backend="xsim",
            status=status,
            category=category,
            message="Vivado xvlog compile failed",
            command=compile_command,
            stdout=compile_proc.stdout,
            stderr=compile_proc.stderr,
            locations=filter_hdl_locations(parse_locations(compile_text)),
        )
        payload = finalize_payload(
            args=args,
            support_range=support_range,
            compile_stage=compile_stage,
            run_stage=None,
            status=status,
            message="Simulation compile failed before elaboration or runtime execution",
            interpretation="fix xvlog compile issues before expecting simulator output or wave artifacts",
            artifacts=artifacts,
        )
        exit_code = 2 if status in {"environment_error", "input_error"} else 1
        return payload, exit_code

    elaborate_command = build_xelab_command(xsim_info, top_name, snapshot_name, elaborate_log)
    elaborate_proc = run_command_in_dir(elaborate_command, env, output_dir)
    ensure_backend_log(elaborate_log, elaborate_proc.stdout, elaborate_proc.stderr)

    elaborate_text = "\n".join(part for part in [elaborate_proc.stdout, elaborate_proc.stderr] if part)
    if elaborate_proc.returncode != 0:
        status, category = classify_backend_failure(elaborate_text)
        compile_stage = make_stage_result(
            backend="xsim",
            status=status,
            category=category,
            message="Vivado xelab elaboration failed",
            command=elaborate_command,
            stdout=elaborate_proc.stdout,
            stderr=elaborate_proc.stderr,
            locations=filter_hdl_locations(parse_locations(elaborate_text)),
        )
        payload = finalize_payload(
            args=args,
            support_range=support_range,
            compile_stage=compile_stage,
            run_stage=None,
            status=status,
            message="Simulation elaboration failed before runtime execution",
            interpretation="fix xelab elaboration issues before expecting simulator output or wave artifacts",
            artifacts=artifacts,
        )
        exit_code = 2 if status in {"environment_error", "input_error"} else 1
        return payload, exit_code

    compile_stage = make_stage_result(
        backend="xsim",
        status="ok",
        category="compile_ok",
        message="Vivado compile/elaboration passed",
        command=elaborate_command,
        stdout="\n".join(part for part in [compile_proc.stdout, elaborate_proc.stdout] if part),
        stderr="\n".join(part for part in [compile_proc.stderr, elaborate_proc.stderr] if part),
        locations=[],
    )

    run_command = build_xsim_run_command(xsim_info, snapshot_name, args.runtime_arg, wave_file, run_log)
    run_proc = run_command_in_dir(run_command, env, output_dir)
    ensure_backend_log(run_log, run_proc.stdout, run_proc.stderr)

    artifacts["wave_files"] = collect_wave_files(output_dir, wave_file)
    enrich_wave_indexes(artifacts, args.wave_index)
    enrich_tb_event_index(artifacts, run_proc.stdout, run_proc.stderr)
    if wave_file is not None and not wave_file.exists():
        return handle_requested_wave_missing(
            args=args,
            support_range=support_range,
            artifacts=artifacts,
            compile_stage=compile_stage,
            run_command=run_command,
            run_stdout=run_proc.stdout,
            run_stderr=run_proc.stderr,
            backend_name="xsim",
        )

    return handle_runtime_completion(
        args=args,
        support_range=support_range,
        artifacts=artifacts,
        compile_stage=compile_stage,
        run_command=run_command,
        run_stdout=run_proc.stdout,
        run_stderr=run_proc.stderr,
        run_returncode=run_proc.returncode,
        backend_name="xsim",
    )


def main() -> int:
    args = parse_args()
    support_range = simulation_support_range()
    normalized, input_error = normalize_inputs(args.inputs, args.include_dir, args.define)
    if input_error is not None:
        print(json.dumps(make_input_error_payload(args, input_error, support_range), indent=2))
        return 2

    output_dir = resolve_output_dir(args.output_dir)
    wave_file = resolve_wave_file(args.wave_file, output_dir)

    if args.backend == "xsim":
        payload, exit_code = run_xsim_backend(args, normalized, support_range, output_dir, wave_file)
    else:
        payload, exit_code = run_iverilog_backend(args, normalized, support_range, output_dir, wave_file)

    print(json.dumps(payload, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
