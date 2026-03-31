#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE1_SCRIPTS = REPO_ROOT / "stages" / "verilog-language-and-syntax" / "scripts"
if str(STAGE1_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STAGE1_SCRIPTS))

from checker_support import (  # noqa: E402
    SUPPORT_RANGE as LANGUAGE_SUPPORT_RANGE,
    classify_backend_failure,
    decode_stream,
    make_stage_result,
    normalize_inputs,
    parse_locations,
    resolve_backend_path,
    run_command,
)
from probe_backend import probe_backend  # noqa: E402


TMP_ROOT = REPO_ROOT / ".tmp" / "verilog-simulation-execution"
WAVE_SUFFIXES = {".vcd", ".fst", ".lxt", ".lxt2", ".vpd"}


def ensure_temp_dir() -> str:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return str(TMP_ROOT)


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    tmp_dir = ensure_temp_dir()
    env["TMP"] = tmp_dir
    env["TEMP"] = tmp_dir
    return env


def simulation_support_range() -> dict:
    payload = dict(LANGUAGE_SUPPORT_RANGE)
    payload["execution_backend"] = "iverilog + vvp"
    payload["execution_scope"] = [
        "compile and elaborate simulation inputs with Icarus Verilog",
        "execute compiled images with vvp",
        "capture stdout and stderr",
        "report emitted waveform artifact paths without analyzing them",
    ]
    payload["execution_limitations"] = [
        "no waveform interpretation",
        "no automatic UVM orchestration",
        "no vendor-library setup automation",
        "no multi-backend scheduling in stage 2",
    ]
    return payload


def resolve_vvp_path(iverilog_info: dict | None = None) -> dict | None:
    configured = os.environ.get("VVP_BIN")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return {
                "path": str(path.resolve()),
                "origin": "environment",
            }

    if iverilog_info and iverilog_info.get("status") == "ok":
        iverilog_path = Path(iverilog_info["backend_path"]).resolve()
        for name in ("vvp.exe", "vvp"):
            sibling = iverilog_path.with_name(name)
            if sibling.exists():
                return {
                    "path": str(sibling.resolve()),
                    "origin": f"{iverilog_info.get('backend_origin', 'derived')}_sibling",
                }

    return resolve_backend_path(
        "VVP_BIN",
        "vvp",
        [
            "tools/iverilog/current/bin/vvp.exe",
            "tools/iverilog/current/bin/vvp",
        ],
    )


def probe_vvp_backend(iverilog_info: dict | None = None) -> dict:
    resolution = resolve_vvp_path(iverilog_info)
    if resolution is None:
        return {
            "backend": "vvp",
            "status": "environment_error",
            "category": "backend_not_found",
            "message": "vvp executable not found",
        }

    backend_path = resolution["path"]
    backend_origin = resolution["origin"]
    env = build_runtime_env()
    try:
        proc = run_command([backend_path, "-V"], env)
    except OSError as exc:
        return {
            "backend": "vvp",
            "backend_path": backend_path,
            "backend_origin": backend_origin,
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": str(exc),
        }

    if proc.returncode != 0:
        return {
            "backend": "vvp",
            "backend_path": backend_path,
            "backend_origin": backend_origin,
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": "vvp returned non-zero during version probe",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    banner = (proc.stdout or proc.stderr).strip()
    summary = banner.splitlines()[0] if banner else "vvp probe succeeded"
    return {
        "backend": "vvp",
        "backend_path": backend_path,
        "backend_origin": backend_origin,
        "status": "ok",
        "category": "backend_ready",
        "tmp_dir": ensure_temp_dir(),
        "version_summary": summary,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def collect_wave_files(output_dir: Path, requested_wave_file: Path | None = None) -> list[str]:
    found: list[str] = []
    if requested_wave_file is not None and requested_wave_file.exists():
        found.append(str(requested_wave_file.resolve()))

    if output_dir.exists():
        for candidate in sorted(output_dir.rglob("*")):
            if not candidate.is_file():
                continue
            if candidate.suffix.lower() not in WAVE_SUFFIXES:
                continue
            resolved = str(candidate.resolve())
            if resolved not in found:
                found.append(resolved)
    return found


def classify_run_failure(proc_stdout: str, proc_stderr: str, returncode: int) -> tuple[str, str]:
    text = "\n".join(part for part in [proc_stdout, proc_stderr] if part)
    lowered = text.lower()
    if "unsupported" in lowered or "sorry:" in lowered:
        return "unsupported_feature", "unsupported_feature"
    if returncode != 0:
        return "run_error", "simulation_failed"
    if "sim_fail" in lowered:
        return "run_error", "simulation_failed"
    return "run_error", "simulation_failed"


def run_command_in_dir(command: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        capture_output=True,
        text=False,
        env=env,
        cwd=str(cwd),
        check=False,
    )
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=decode_stream(proc.stdout),
        stderr=decode_stream(proc.stderr),
    )
