#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from simulation_support import (
    build_runtime_env,
    classify_backend_failure,
    classify_run_failure,
    collect_wave_files,
    detect_runtime_failure_markers,
    ensure_temp_dir,
    make_stage_result,
    normalize_inputs,
    parse_locations,
    probe_backend,
    probe_vvp_backend,
    run_command,
    run_command_in_dir,
    simulation_support_range,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-2 Verilog/SystemVerilog simulation executor")
    parser.add_argument("inputs", nargs="+", help="Source files or .f file lists")
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
        help="Runtime plusarg or vvp argument appended after the compiled image",
    )
    parser.add_argument("--wave-file", help="Requested waveform file path")
    parser.add_argument("--output-dir", help="Directory for compiled image and logs")
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


def build_compile_command(backend_path: str, normalized: dict, top: str | None, output_image: Path) -> list[str]:
    command = [backend_path, "-g2012", "-o", str(output_image)]
    if top:
        command.extend(["-s", top])
    for include_dir in normalized["include_dirs"]:
        command.extend(["-I", include_dir])
    for define in normalized["defines"]:
        command.append(f"-D{define}")
    command.extend(normalized["source_files"])
    return command


def build_run_command(vvp_path: str, output_image: Path, runtime_args: list[str], wave_file: Path | None) -> list[str]:
    command = [vvp_path, str(output_image)]
    if wave_file is not None:
        wave_text = wave_file.as_posix()
        command.extend([f"+WAVE_FILE={wave_text}", f"+wave={wave_text}"])
    command.extend(runtime_args)
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
    if backend_result["backend"] == "iverilog":
        checks["compile"] = stage
    else:
        checks["run"] = stage
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


def main() -> int:
    args = parse_args()
    support_range = simulation_support_range()
    normalized, input_error = normalize_inputs(args.inputs, args.include_dir, args.define)
    if input_error is not None:
        print(json.dumps(make_input_error_payload(args, input_error, support_range), indent=2))
        return 2

    output_dir = resolve_output_dir(args.output_dir)
    compile_log = output_dir / "compile.log"
    run_log = output_dir / "run.log"
    compiled_image = output_dir / "sim.out"
    wave_file = resolve_wave_file(args.wave_file, output_dir)
    if wave_file is not None and wave_file.exists():
        wave_file.unlink()

    artifacts = {
        "output_dir": str(output_dir),
        "compiled_image": str(compiled_image),
        "compile_log": str(compile_log),
        "run_log": str(run_log),
        "wave_files": [],
    }
    if wave_file is not None:
        artifacts["requested_wave_file"] = str(wave_file)

    iverilog_info = probe_backend("iverilog")
    if iverilog_info["status"] != "ok":
        print(json.dumps(make_environment_error_payload(args, iverilog_info, support_range), indent=2))
        return 2

    vvp_info = probe_vvp_backend(iverilog_info)
    if vvp_info["status"] != "ok":
        print(json.dumps(make_environment_error_payload(args, vvp_info, support_range), indent=2))
        return 2

    env = build_runtime_env()
    compile_command = build_compile_command(iverilog_info["backend_path"], normalized, args.top, compiled_image)
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
            locations=parse_locations(compile_text),
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
        print(json.dumps(payload, indent=2))
        return 2 if status in {"environment_error", "input_error"} else 1

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

    run_command_args = build_run_command(vvp_info["backend_path"], compiled_image, args.runtime_arg, wave_file)
    run_proc = run_command_in_dir(run_command_args, env, output_dir)
    write_log(run_log, run_proc.stdout, run_proc.stderr)

    wave_files = collect_wave_files(output_dir, wave_file)
    artifacts["wave_files"] = wave_files

    if wave_file is not None and not wave_file.exists():
        run_stage = make_stage_result(
            backend="vvp",
            status="run_error",
            category="wave_missing",
            message="Simulation finished without emitting the requested wave file",
            command=run_command_args,
            stdout=run_proc.stdout,
            stderr=run_proc.stderr,
            locations=[],
        )
        payload = finalize_payload(
            args=args,
            support_range=support_range,
            compile_stage=compile_stage,
            run_stage=run_stage,
            status="run_error",
            message="Simulation ran but did not produce the requested wave artifact",
            interpretation="the testbench did not honor the requested wave path or did not emit any dump file",
            artifacts=artifacts,
        )
        print(json.dumps(payload, indent=2))
        return 1

    failure_markers = detect_runtime_failure_markers(run_proc.stdout, run_proc.stderr)
    if run_proc.returncode != 0 or failure_markers:
        status, category = classify_run_failure(run_proc.stdout, run_proc.stderr, run_proc.returncode)
        runtime_message = "Simulation runtime failed"
        interpretation = "the testbench executed but reported a runtime failure or exited non-zero"
        if failure_markers and run_proc.returncode == 0:
            runtime_message = "Simulation runtime reported failure markers"
            interpretation = "the testbench completed but its own logs declared a failure condition"
        run_stage = make_stage_result(
            backend="vvp",
            status=status,
            category=category,
            message=runtime_message,
            command=run_command_args,
            stdout=run_proc.stdout,
            stderr=run_proc.stderr,
            locations=parse_locations("\n".join(part for part in [run_proc.stdout, run_proc.stderr] if part)),
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
        print(json.dumps(payload, indent=2))
        return 1

    run_stage = make_stage_result(
        backend="vvp",
        status="ok",
        category="run_ok",
        message="Simulation runtime completed",
        command=run_command_args,
        stdout=run_proc.stdout,
        stderr=run_proc.stderr,
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
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
