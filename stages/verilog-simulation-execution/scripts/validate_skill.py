#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUN_SCRIPT = SCRIPT_DIR / "run_simulation.py"
FIXTURES_DIR = SCRIPT_DIR.parent / "fixtures"
VALIDATION_ROOT = SCRIPT_DIR.parent.parent.parent / ".tmp" / "verilog-simulation-execution" / "validation"


def run_case(name: str, args: list[str], expected_status: str, expected_run_status: str | None = None) -> dict:
    proc = subprocess.run(
        [sys.executable, str(RUN_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if not proc.stdout.strip():
        raise AssertionError(f"{name}: simulation runner produced no JSON output")

    payload = json.loads(proc.stdout)
    if payload["status"] != expected_status:
        raise AssertionError(f"{name}: expected status {expected_status}, got {payload['status']}")
    run_stage = payload["checks"]["run"]
    if expected_run_status is not None:
        if run_stage is None:
            raise AssertionError(f"{name}: missing checks.run")
        if run_stage["status"] != expected_run_status:
            raise AssertionError(f"{name}: expected run status {expected_run_status}, got {run_stage['status']}")
    return payload


def main() -> int:
    if VALIDATION_ROOT.exists():
        shutil.rmtree(VALIDATION_ROOT)
    VALIDATION_ROOT.mkdir(parents=True, exist_ok=True)

    pass_dir = VALIDATION_ROOT / "pass"
    fail_dir = VALIDATION_ROOT / "fail"
    pass_payload = run_case(
        "pass_counter",
        [
            str(FIXTURES_DIR / "pass_counter.f"),
            "--top",
            "tb_counter_wave",
            "--output-dir",
            str(pass_dir),
            "--wave-file",
            "counter.vcd",
        ],
        "ok",
        "ok",
    )
    if not pass_payload["artifacts"]["wave_files"]:
        raise AssertionError("pass_counter: expected at least one wave file")
    if "SIM_PASS" not in pass_payload["checks"]["run"]["stdout"]:
        raise AssertionError("pass_counter: expected SIM_PASS marker in runtime stdout")

    fail_payload = run_case(
        "fail_runtime",
        [
            str(FIXTURES_DIR / "fail_runtime.f"),
            "--top",
            "tb_runtime_fail",
            "--output-dir",
            str(fail_dir),
            "--wave-file",
            "runtime_fail.vcd",
        ],
        "run_error",
        "run_error",
    )
    if "SIM_FAIL" not in fail_payload["checks"]["run"]["stdout"]:
        raise AssertionError("fail_runtime: expected SIM_FAIL marker in runtime stdout")

    print("validation_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
