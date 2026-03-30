#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from probe_backend import probe_backend


SCRIPT_DIR = Path(__file__).resolve().parent
CHECK_SCRIPT = SCRIPT_DIR / "check_syntax.py"
LINT_SCRIPT = SCRIPT_DIR / "check_lint.py"
FIXTURES_DIR = SCRIPT_DIR.parent / "fixtures"


def run_case(name: str, args: list[str], expected_status: str, expected_category: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(CHECK_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if not proc.stdout.strip():
        raise AssertionError(f"{name}: checker produced no JSON output")

    payload = json.loads(proc.stdout)
    if payload["status"] != expected_status:
        raise AssertionError(f"{name}: expected status {expected_status}, got {payload['status']}")

    syntax = payload["checks"]["syntax"]
    elaboration = payload["checks"]["elaboration"]
    observed_category = None
    if elaboration and elaboration["status"] != "ok":
        observed_category = elaboration["category"]
    elif syntax:
        observed_category = syntax["category"]
    if observed_category != expected_category:
        raise AssertionError(f"{name}: expected category {expected_category}, got {observed_category}")

    if "support_range" not in payload:
        raise AssertionError(f"{name}: missing support_range")
    if "checks" not in payload or "syntax" not in payload["checks"]:
        raise AssertionError(f"{name}: missing checks.syntax")
    if syntax is not None and "locations" not in syntax:
        raise AssertionError(f"{name}: missing syntax locations field")
    if elaboration is not None and "locations" not in elaboration:
        raise AssertionError(f"{name}: missing elaboration locations field")


def run_lint_case(name: str, args: list[str], expected_status: str, expected_category: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(LINT_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if not proc.stdout.strip():
        raise AssertionError(f"{name}: lint checker produced no JSON output")

    payload = json.loads(proc.stdout)
    if payload["status"] != expected_status:
        raise AssertionError(f"{name}: expected status {expected_status}, got {payload['status']}")

    lint = payload["checks"]["lint"]
    if lint is None:
        raise AssertionError(f"{name}: missing checks.lint")
    if lint["category"] != expected_category:
        raise AssertionError(f"{name}: expected category {expected_category}, got {lint['category']}")
    if "locations" not in lint:
        raise AssertionError(f"{name}: missing lint locations field")
    if "support_range" not in payload:
        raise AssertionError(f"{name}: missing support_range")


def main() -> int:
    verible_available = probe_backend("verible")["status"] == "ok"
    verible_lint_available = probe_backend("verible-lint")["status"] == "ok"

    run_case(
        "pass_verilog_2005",
        [str(FIXTURES_DIR / "pass_verilog_2005.v"), "--syntax-backend", "iverilog"],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_sv_subset",
        [str(FIXTURES_DIR / "pass_simple.sv"), "--syntax-backend", "iverilog"],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_command_file",
        [str(FIXTURES_DIR / "pass_simple.f"), "--syntax-backend", "iverilog"],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_with_include",
        [
            str(FIXTURES_DIR / "pass_with_include.sv"),
            "--include-dir",
            str(FIXTURES_DIR / "includes"),
            "--syntax-backend",
            "iverilog",
        ],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_with_define",
        [
            str(FIXTURES_DIR / "pass_with_define.sv"),
            "--define",
            "ENABLE_PASS_WITH_DEFINE",
            "--syntax-backend",
            "iverilog",
        ],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_with_top",
        [
            str(FIXTURES_DIR / "pass_with_top.sv"),
            "--top",
            "chosen_top",
            "--syntax-backend",
            "iverilog",
        ],
        "ok",
        "syntax_ok",
    )
    run_case(
        "pass_with_include_command_file",
        [str(FIXTURES_DIR / "pass_with_include.f"), "--syntax-backend", "iverilog"],
        "ok",
        "syntax_ok",
    )
    run_case(
        "fail_syntax",
        [str(FIXTURES_DIR / "fail_syntax.sv"), "--syntax-backend", "iverilog"],
        "syntax_error",
        "syntax_error",
    )
    run_case(
        "fail_no_top",
        [str(FIXTURES_DIR / "fail_no_top_pkg.sv"), "--syntax-backend", "iverilog"],
        "elaboration_error",
        "elaboration_error",
    )
    run_case(
        "fail_missing_include",
        [str(FIXTURES_DIR / "fail_missing_include.sv"), "--syntax-backend", "iverilog"],
        "input_error",
        "missing_dependency",
    )
    if verible_available:
        run_case(
            "auto_prefers_verible_when_available",
            [str(FIXTURES_DIR / "pass_simple.sv"), "--syntax-backend", "auto"],
            "ok",
            "syntax_ok",
        )
        run_case(
            "explicit_verible_path",
            [str(FIXTURES_DIR / "pass_simple.sv"), "--syntax-backend", "verible"],
            "ok",
            "syntax_ok",
        )
    else:
        run_case(
            "auto_fallback_without_verible",
            [str(FIXTURES_DIR / "pass_simple.sv"), "--syntax-backend", "auto"],
            "ok",
            "syntax_backend_fallback",
        )

    if verible_lint_available:
        run_lint_case(
            "lint_pass_sv_subset",
            [str(FIXTURES_DIR / "pass_simple.sv")],
            "ok",
            "lint_ok",
        )
        run_lint_case(
            "lint_pass_command_file",
            [str(FIXTURES_DIR / "pass_simple.f")],
            "ok",
            "lint_ok",
        )
        run_lint_case(
            "lint_fail_rule_violation",
            [str(FIXTURES_DIR / "lint_fail_always_ff.sv")],
            "lint_error",
            "lint_violation",
        )
        run_lint_case(
            "lint_fail_syntax",
            [str(FIXTURES_DIR / "fail_syntax.sv")],
            "syntax_error",
            "syntax_error",
        )
        run_lint_case(
            "lint_unsupported_include_shape",
            [str(FIXTURES_DIR / "pass_with_include.f")],
            "unsupported_feature",
            "unsupported_feature",
        )
    print("validation_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
