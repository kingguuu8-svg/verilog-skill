#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from checker_support import build_runtime_env, ensure_temp_dir, resolve_backend_path, run_command


BACKEND_SPECS = {
    "iverilog": {
        "env_var": "IVERILOG_BIN",
        "executable": "iverilog",
        "local_candidates": [
            "tools/iverilog/current/iverilog.exe",
            "tools/iverilog/current/iverilog",
        ],
        "version_args": ["-V"],
        "language_mode_default": "1800-2012",
    },
    "verible": {
        "env_var": "VERIBLE_VERILOG_SYNTAX_BIN",
        "executable": "verible-verilog-syntax",
        "local_candidates": [
            "tools/verible/current/verible-verilog-syntax.exe",
            "tools/verible/current/verible-verilog-syntax",
        ],
        "version_args": ["--version"],
        "language_mode_default": "1800-2017 parser",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe syntax checker backends")
    parser.add_argument(
        "--backend",
        choices=["all", "iverilog", "verible"],
        default="all",
        help="Which backend to probe",
    )
    return parser.parse_args()


def probe_backend(name: str) -> dict:
    spec = BACKEND_SPECS[name]
    backend_path = resolve_backend_path(spec["env_var"], spec["executable"], spec.get("local_candidates"))
    if backend_path is None:
        return {
            "backend": name,
            "status": "environment_error",
            "category": "backend_not_found",
            "message": f"{spec['executable']} executable not found",
        }

    env = build_runtime_env()
    try:
        proc = run_command([backend_path, *spec["version_args"]], env)
    except OSError as exc:
        return {
            "backend": name,
            "backend_path": backend_path,
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": str(exc),
        }

    if proc.returncode != 0:
        return {
            "backend": name,
            "backend_path": backend_path,
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": f"{spec['executable']} returned non-zero during version probe",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    banner = (proc.stdout or proc.stderr).strip()
    summary = banner.splitlines()[0] if banner else f"{name} probe succeeded"
    return {
        "backend": name,
        "backend_path": backend_path,
        "status": "ok",
        "category": "backend_ready",
        "language_mode_default": spec["language_mode_default"],
        "tmp_dir": ensure_temp_dir(),
        "version_summary": summary,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def main() -> int:
    args = parse_args()
    if args.backend == "all":
        payload = {name: probe_backend(name) for name in BACKEND_SPECS}
    else:
        payload = probe_backend(args.backend)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
