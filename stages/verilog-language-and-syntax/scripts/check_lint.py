#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from checker_support import (
    COMPILATION_UNIT_SUFFIXES,
    HEADER_SUFFIXES,
    SUPPORT_RANGE,
    build_runtime_env,
    classify_backend_failure,
    make_stage_result,
    normalize_inputs,
    parse_locations,
    run_command,
)
from probe_backend import probe_backend


RULE_RE = re.compile(r"\[([A-Za-z0-9_.-]+)\]\s*$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-1 Verilog/SystemVerilog lint dispatcher")
    parser.add_argument("inputs", nargs="+", help="Source files or .f file lists")
    parser.add_argument("--rules", help="Comma-separated Verible lint rules override")
    parser.add_argument(
        "--ruleset",
        choices=["default", "all", "none"],
        default="default",
        help="Verible ruleset selection",
    )
    parser.add_argument(
        "--waiver-file",
        action="append",
        default=[],
        help="Optional Verible waiver file",
    )
    return parser.parse_args()


def lint_support_range() -> dict:
    payload = dict(SUPPORT_RANGE)
    payload["lint_backend"] = "verible-verilog-lint"
    payload["lint_scope"] = [
        "source-level lint for .v and .sv compilation units",
        "style and structural rule checks only",
        "no preprocessing-aware include or define expansion in stage 1",
    ]
    payload["lint_limitations"] = [
        "headers are not linted as standalone compilation units",
        "include-dir and define driven lint preprocessing is not supported in stage 1",
        "lint is an optional next-layer check and does not replace syntax/elaboration",
    ]
    return payload


def lint_backend_supports(normalized: dict) -> tuple[bool, str]:
    files = [Path(item) for item in normalized["source_files"]]
    if normalized["include_dirs"] or normalized["defines"]:
        return False, "Stage-1 lint wrapper does not apply include-dir or define preprocessing"
    if any(path.suffix.lower() in HEADER_SUFFIXES for path in files):
        return False, "Stage-1 lint runs only on .v and .sv compilation units, not standalone headers"
    if any(path.suffix.lower() not in COMPILATION_UNIT_SUFFIXES for path in files):
        return False, "Stage-1 lint supports only .v and .sv compilation units"
    return True, ""


def build_lint_command(backend_path: str, normalized: dict, args: argparse.Namespace) -> list[str]:
    command = [backend_path, f"--ruleset={args.ruleset}"]
    if args.rules:
        command.append(f"--rules={args.rules}")
    for waiver_file in args.waiver_file:
        command.append(f"--waiver_files={Path(waiver_file).resolve()}")
    command.extend(normalized["source_files"])
    return command


def parse_lint_locations(text: str) -> list[dict]:
    locations = parse_locations(text)
    for entry in locations:
        match = RULE_RE.search(entry["message"])
        if match:
            entry["rule"] = match.group(1)
    return locations


def classify_lint_failure(text: str, locations: list[dict]) -> tuple[str, str]:
    status, category = classify_backend_failure(text)
    if status in {"unsupported_feature", "syntax_error"}:
        return status, category
    if status == "input_error":
        if locations and any("rule" in entry for entry in locations):
            return "lint_error", "lint_violation"
        return status, category
    if locations:
        return "lint_error", "lint_violation"
    return "lint_error", "lint_violation"


def make_input_error_payload(args: argparse.Namespace, details: dict, support_range: dict) -> dict:
    return {
        "status": details["status"],
        "message": details["message"],
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": {
            "lint": None,
        },
        "details": details,
        "interpretation": "lint input is invalid before backend execution",
    }


def make_environment_error_payload(args: argparse.Namespace, backend_result: dict, support_range: dict) -> dict:
    return {
        "status": backend_result["status"],
        "message": backend_result["message"],
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": {
            "lint": make_stage_result(
                backend=backend_result["backend"],
                status=backend_result["status"],
                category=backend_result["category"],
                message=backend_result["message"],
                stdout=backend_result.get("stdout", ""),
                stderr=backend_result.get("stderr", ""),
            )
        },
        "interpretation": "lint backend is unavailable or not runnable in the current environment",
    }


def finalize_payload(args: argparse.Namespace, lint_stage: dict, status: str, message: str, interpretation: str, support_range: dict) -> dict:
    return {
        "status": status,
        "message": message,
        "support_range": support_range,
        "input_files": args.inputs,
        "checks": {
            "lint": lint_stage,
        },
        "interpretation": interpretation,
    }


def main() -> int:
    args = parse_args()
    support_range = lint_support_range()
    normalized, input_error = normalize_inputs(args.inputs, [], [])
    if input_error is not None:
        print(json.dumps(make_input_error_payload(args, input_error, support_range), indent=2))
        return 2

    supported, reason = lint_backend_supports(normalized)
    if not supported:
        stage = make_stage_result(
            backend="verible-lint",
            status="unsupported_feature",
            category="unsupported_feature",
            message=reason,
        )
        payload = finalize_payload(
            args,
            stage,
            "unsupported_feature",
            "Requested lint path is not supported for this input shape",
            "lint wrapper limitation: current stage-1 lint only supports direct .v/.sv compilation units without preprocessing inputs",
            support_range,
        )
        print(json.dumps(payload, indent=2))
        return 1

    backend = probe_backend("verible-lint")
    if backend["status"] != "ok":
        print(json.dumps(make_environment_error_payload(args, backend, support_range), indent=2))
        return 2

    env = build_runtime_env()
    command = build_lint_command(backend["backend_path"], normalized, args)
    proc = run_command(command, env)
    text = "\n".join(part for part in [proc.stdout, proc.stderr] if part)
    locations = parse_lint_locations(text)

    if proc.returncode == 0:
        stage = make_stage_result(
            backend="verible-lint",
            status="ok",
            category="lint_ok",
            message="Verible lint passed",
            command=command,
            stdout=proc.stdout,
            stderr=proc.stderr,
            locations=[],
        )
        payload = finalize_payload(
            args,
            stage,
            "ok",
            "Lint checks passed",
            "source passes the current optional next-layer lint capability",
            support_range,
        )
        print(json.dumps(payload, indent=2))
        return 0

    status, category = classify_lint_failure(text, locations)
    message = "Verible lint failed"
    interpretation = "lint backend reported rule violations or parser/backend limitations"
    if status == "syntax_error":
        message = "Lint failed due to syntax errors before rule evaluation"
        interpretation = "source must pass syntax checks before lint can be trusted"
    elif status == "unsupported_feature":
        message = "Lint failed due to unsupported backend behavior"
        interpretation = "source shape or construct is unsupported by the current lint backend path"
    elif status == "input_error":
        message = "Lint failed due to invalid lint input or missing dependencies"
        interpretation = "lint input references missing data or unsupported invocation shape"
    elif status == "lint_error":
        interpretation = "source passes basic invocation but violates one or more Verible lint rules"

    stage = make_stage_result(
        backend="verible-lint",
        status=status,
        category=category,
        message=message,
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
        locations=locations,
    )
    payload = finalize_payload(args, stage, status, message, interpretation, support_range)
    print(json.dumps(payload, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
