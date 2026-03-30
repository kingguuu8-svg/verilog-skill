#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from checker_support import (
    COMPILATION_UNIT_SUFFIXES,
    HEADER_SUFFIXES,
    SOURCE_INPUT_SUFFIXES,
    SUPPORT_RANGE,
    SUPPORTED_INPUT_SUFFIXES,
    build_runtime_env,
    classify_backend_failure,
    make_stage_result,
    parse_locations,
    run_command,
)
from probe_backend import probe_backend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-1 Verilog/SystemVerilog syntax dispatcher")
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
        "--syntax-backend",
        choices=["auto", "verible", "iverilog"],
        default="auto",
        help="Select syntax backend strategy",
    )
    return parser.parse_args()


def parse_command_file(source: Path) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    source_files: list[str] = []
    include_dirs: list[str] = []
    defines: list[str] = []
    unsupported_directives: list[str] = []
    missing_entries: list[str] = []

    for raw_line in source.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if stripped.startswith("+incdir+"):
            parts = [part for part in stripped.split("+")[2:] if part]
            for part in parts:
                include_dirs.append(str((source.parent / part).resolve()))
            continue
        if stripped.startswith("+define+"):
            parts = [part for part in stripped.split("+")[2:] if part]
            defines.extend(parts)
            continue
        if stripped.startswith("-I"):
            include_dirs.append(str((source.parent / stripped[2:].strip()).resolve()))
            continue
        if stripped.startswith("-D"):
            defines.append(stripped[2:].strip())
            continue
        if stripped.startswith("+") or stripped.startswith("-"):
            unsupported_directives.append(stripped)
            continue

        candidate = Path(stripped)
        if not candidate.is_absolute():
            candidate = (source.parent / candidate).resolve()
        if candidate.exists():
            source_files.append(str(candidate))
        else:
            missing_entries.append(str(candidate))

    return source_files, include_dirs, defines, unsupported_directives, missing_entries


def normalize_inputs(
    inputs: list[str],
    include_dirs: list[str],
    defines: list[str],
) -> tuple[dict, dict | None]:
    normalized = {
        "source_files": [],
        "include_dirs": [str(Path(item).resolve()) for item in include_dirs],
        "defines": list(defines),
        "unsupported_directives": [],
    }
    rejected: list[str] = []

    for item in inputs:
        path = Path(item)
        if not path.exists() or path.suffix.lower() not in SUPPORTED_INPUT_SUFFIXES:
            rejected.append(item)
            continue

        if path.suffix.lower() == ".f":
            files, file_includes, file_defines, unsupported, missing_entries = parse_command_file(path)
            normalized["source_files"].extend(files)
            normalized["include_dirs"].extend(file_includes)
            normalized["defines"].extend(file_defines)
            normalized["unsupported_directives"].extend(unsupported)
            rejected.extend(missing_entries)
            continue

        normalized["source_files"].append(str(path.resolve()))

    normalized["source_files"] = list(dict.fromkeys(normalized["source_files"]))
    normalized["include_dirs"] = list(dict.fromkeys(normalized["include_dirs"]))
    normalized["defines"] = list(dict.fromkeys(normalized["defines"]))
    normalized["unsupported_directives"] = list(dict.fromkeys(normalized["unsupported_directives"]))

    invalid_includes = [item for item in normalized["include_dirs"] if not Path(item).exists()]
    if rejected or invalid_includes or normalized["unsupported_directives"]:
        return normalized, {
            "status": "input_error",
            "category": "invalid_input",
            "message": "Inputs include missing files, unsupported directives, or invalid include paths",
            "rejected_inputs": rejected,
            "invalid_include_dirs": invalid_includes,
            "unsupported_directives": normalized["unsupported_directives"],
        }
    if not normalized["source_files"]:
        return normalized, {
            "status": "input_error",
            "category": "invalid_input",
            "message": "No source files were resolved from the provided inputs",
            "rejected_inputs": rejected,
            "invalid_include_dirs": invalid_includes,
            "unsupported_directives": normalized["unsupported_directives"],
        }
    return normalized, None


def syntax_backend_supports_verible(normalized: dict, args: argparse.Namespace) -> tuple[bool, str]:
    files = [Path(item) for item in normalized["source_files"]]
    if normalized["include_dirs"] or normalized["defines"]:
        return False, "Verible stage-1 wrapper does not currently apply include-dir or define preprocessing"
    if any(path.suffix.lower() in HEADER_SUFFIXES for path in files):
        return False, "Verible syntax stage only runs on compilation-unit source files in stage 1"
    if any(path.suffix.lower() not in COMPILATION_UNIT_SUFFIXES for path in files):
        return False, "Verible syntax stage only supports .v and .sv compilation units in stage 1"
    if args.top:
        return True, ""
    return True, ""


def build_iverilog_command(backend_path: str, normalized: dict, top: str | None) -> list[str]:
    command = [backend_path, "-g2012", "-t", "null"]
    if top:
        command.extend(["-s", top])
    for include_dir in normalized["include_dirs"]:
        command.extend(["-I", include_dir])
    for define in normalized["defines"]:
        command.append(f"-D{define}")
    command.extend(normalized["source_files"])
    return command


def build_verible_command(backend_path: str, normalized: dict) -> list[str]:
    return [backend_path, *normalized["source_files"]]


def make_input_error_payload(args: argparse.Namespace, details: dict) -> dict:
    return {
        "status": details["status"],
        "message": details["message"],
        "support_range": SUPPORT_RANGE,
        "input_files": args.inputs,
        "checks": {
            "syntax": None,
            "elaboration": None,
        },
        "details": details,
        "interpretation": "checker input is invalid or unsupported before backend execution",
    }


def make_environment_error_payload(args: argparse.Namespace, backend_result: dict) -> dict:
    stage = make_stage_result(
        backend=backend_result["backend"],
        status=backend_result["status"],
        category=backend_result["category"],
        message=backend_result["message"],
        stdout=backend_result.get("stdout", ""),
        stderr=backend_result.get("stderr", ""),
    )
    return {
        "status": backend_result["status"],
        "message": backend_result["message"],
        "support_range": SUPPORT_RANGE,
        "input_files": args.inputs,
        "checks": {
            "syntax": stage,
            "elaboration": None,
        },
        "interpretation": "backend is unavailable or not runnable in the current environment",
    }


def finalize_payload(
    *,
    args: argparse.Namespace,
    syntax_stage: dict | None,
    elaboration_stage: dict | None,
    top_message: str,
    top_status: str,
    interpretation: str,
) -> dict:
    return {
        "status": top_status,
        "message": top_message,
        "support_range": SUPPORT_RANGE,
        "input_files": args.inputs,
        "checks": {
            "syntax": syntax_stage,
            "elaboration": elaboration_stage,
        },
        "interpretation": interpretation,
    }


def run_verible_syntax(args: argparse.Namespace, normalized: dict, backend_result: dict, env: dict[str, str]) -> dict:
    command = build_verible_command(backend_result["backend_path"], normalized)
    proc = run_command(command, env)
    text = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    locations = parse_locations(text)
    if proc.returncode == 0:
        return make_stage_result(
            backend="verible",
            status="ok",
            category="syntax_ok",
            message="Verible syntax check passed",
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            locations=[],
        )

    status, category = classify_backend_failure(text)
    if status == "elaboration_error":
        status = "syntax_error"
        category = "syntax_error"
    return make_stage_result(
        backend="verible",
        status=status,
        category=category,
        message="Verible syntax check failed",
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
        locations=locations,
    )


def run_iverilog_stage(
    args: argparse.Namespace,
    normalized: dict,
    backend_result: dict,
    env: dict[str, str],
) -> tuple[dict | None, dict | None, str, str, str]:
    command = build_iverilog_command(backend_result["backend_path"], normalized, args.top)
    proc = run_command(command, env)
    locations = parse_locations(proc.stderr)

    if proc.returncode == 0:
        syntax_stage = make_stage_result(
            backend="iverilog",
            status="ok",
            category="syntax_ok",
            message="Icarus syntax check passed",
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            locations=[],
        )
        elaboration_stage = make_stage_result(
            backend="iverilog",
            status="ok",
            category="elaboration_ok",
            message="Icarus elaboration check passed",
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            locations=[],
        )
        return (
            syntax_stage,
            elaboration_stage,
            "ok",
            "Syntax and elaboration checks passed",
            "code stays inside the current stage-1 contract and passes the active backend path",
        )

    status, category = classify_backend_failure(proc.stderr)
    if status == "syntax_error":
        syntax_stage = make_stage_result(
            backend="iverilog",
            status=status,
            category=category,
            message="Icarus syntax check failed",
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            locations=locations,
        )
        return (
            syntax_stage,
            None,
            status,
            "Syntax check failed in the required Icarus backend",
            "input violates the current stage-1 contract or contains invalid syntax for the selected backend",
        )

    elaboration_stage = make_stage_result(
        backend="iverilog",
        status=status,
        category=category,
        message="Icarus elaboration check failed",
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
        locations=locations,
    )
    syntax_stage = make_stage_result(
        backend="iverilog",
        status="ok",
        category="syntax_ok",
        message="Icarus syntax phase reached elaboration",
        command=command,
        stdout="",
        stderr="",
        locations=[],
    )
    interpretation = "current stage-1 syntax passed, but elaboration or backend support failed"
    if status == "unsupported_feature":
        interpretation = "construct appears allowed by the contract or standard but unsupported by the current backend"
    elif status == "input_error":
        interpretation = "backend reached elaboration but failed on missing dependencies or invalid project inputs"
    return (
        syntax_stage,
        elaboration_stage,
        status,
        "Elaboration check failed in the required Icarus backend",
        interpretation,
    )


def main() -> int:
    args = parse_args()
    normalized, input_error = normalize_inputs(args.inputs, args.include_dir, args.define)
    if input_error is not None:
        print(json.dumps(make_input_error_payload(args, input_error), indent=2))
        return 2

    env = build_runtime_env()
    iverilog_info = probe_backend("iverilog")
    if iverilog_info["status"] != "ok":
        print(json.dumps(make_environment_error_payload(args, iverilog_info), indent=2))
        return 2

    syntax_backend = args.syntax_backend
    verible_info = None
    if syntax_backend in {"auto", "verible"}:
        verible_info = probe_backend("verible")

    use_verible = False
    verible_reason = ""
    if syntax_backend == "verible":
        if verible_info is None or verible_info["status"] != "ok":
            print(json.dumps(make_environment_error_payload(args, verible_info or {"backend": "verible", "status": "environment_error", "category": "backend_not_found", "message": "verible backend not available"}), indent=2))
            return 2
        supported, reason = syntax_backend_supports_verible(normalized, args)
        if not supported:
            syntax_stage = make_stage_result(
                backend="verible",
                status="unsupported_feature",
                category="unsupported_feature",
                message=reason,
            )
            payload = finalize_payload(
                args=args,
                syntax_stage=syntax_stage,
                elaboration_stage=None,
                top_message="Requested Verible syntax path is not supported for this input shape",
                top_status="unsupported_feature",
                interpretation="requested syntax backend cannot handle this stage-1 input shape",
            )
            print(json.dumps(payload, indent=2))
            return 1
        use_verible = True
    elif syntax_backend == "auto" and verible_info is not None and verible_info["status"] == "ok":
        use_verible, verible_reason = syntax_backend_supports_verible(normalized, args)
    elif syntax_backend == "auto":
        verible_reason = "Verible backend not available, using required Icarus-only path"

    syntax_stage = None
    elaboration_stage = None

    if use_verible and verible_info is not None:
        syntax_stage = run_verible_syntax(args, normalized, verible_info, env)
        if syntax_stage["status"] != "ok":
            payload = finalize_payload(
                args=args,
                syntax_stage=syntax_stage,
                elaboration_stage=None,
                top_message="Syntax check failed before elaboration",
                top_status=syntax_stage["status"],
                interpretation="input violates the current stage-1 contract or uses syntax unsupported by the chosen syntax backend",
            )
            print(json.dumps(payload, indent=2))
            return 1

        iverilog_syntax_stage, elaboration_stage, top_status, top_message, interpretation = run_iverilog_stage(
            args, normalized, iverilog_info, env
        )
        if elaboration_stage is None:
            # Verible passed, so a later Icarus syntax failure is treated as backend limitation.
            syntax_stage = make_stage_result(
                backend="verible",
                status="ok",
                category="syntax_ok",
                message="Verible syntax check passed",
                command=syntax_stage["command"],
                stdout=syntax_stage["stdout"],
                stderr=syntax_stage["stderr"],
                locations=syntax_stage["locations"],
            )
            elaboration_stage = make_stage_result(
                backend="iverilog",
                status="unsupported_feature",
                category="unsupported_feature",
                message="Icarus rejected input after Verible syntax passed",
                command=iverilog_syntax_stage["command"],
                stdout=iverilog_syntax_stage["stdout"],
                stderr=iverilog_syntax_stage["stderr"],
                locations=iverilog_syntax_stage["locations"],
            )
            payload = finalize_payload(
                args=args,
                syntax_stage=syntax_stage,
                elaboration_stage=elaboration_stage,
                top_message="Syntax accepted by Verible, but required Icarus path still failed",
                top_status="unsupported_feature",
                interpretation="construct appears acceptable by syntax parser but unsupported or incompatible with the required elaboration backend",
            )
            print(json.dumps(payload, indent=2))
            return 1

        payload = finalize_payload(
            args=args,
            syntax_stage=syntax_stage,
            elaboration_stage=elaboration_stage,
            top_message=top_message,
            top_status=top_status,
            interpretation=interpretation,
        )
        print(json.dumps(payload, indent=2))
        return 0 if top_status == "ok" else 1

    if syntax_backend == "auto" and verible_reason:
        syntax_stage = make_stage_result(
            backend="iverilog",
            status="ok",
            category="syntax_backend_fallback",
            message=f"Auto mode fell back to Icarus-only syntax path: {verible_reason}",
        )

    iverilog_syntax_stage, elaboration_stage, top_status, top_message, interpretation = run_iverilog_stage(
        args, normalized, iverilog_info, env
    )

    if syntax_stage is not None and iverilog_syntax_stage is not None and top_status == "ok":
        syntax_stage = make_stage_result(
            backend="iverilog",
            status="ok",
            category="syntax_backend_fallback",
            message=syntax_stage["message"],
            command=iverilog_syntax_stage["command"],
            stdout=iverilog_syntax_stage["stdout"],
            stderr=iverilog_syntax_stage["stderr"],
            locations=[],
        )
    elif syntax_stage is None:
        syntax_stage = iverilog_syntax_stage

    payload = finalize_payload(
        args=args,
        syntax_stage=syntax_stage,
        elaboration_stage=elaboration_stage,
        top_message=top_message,
        top_status=top_status,
        interpretation=interpretation,
    )
    print(json.dumps(payload, indent=2))
    return 0 if top_status == "ok" else (2 if top_status in {"environment_error", "input_error"} else 1)


if __name__ == "__main__":
    raise SystemExit(main())
