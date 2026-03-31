#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
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
WAVE_SUFFIXES = {".vcd", ".fst", ".lxt", ".lxt2", ".vpd", ".wdb"}
RUNTIME_FAILURE_MARKERS = (
    "sim_fail",
    "[fail]",
    "final result: failed",
    "test failed",
    "tests failed",
)
VIVADO_TOOL_ENV_VARS = {
    "xvlog": "XVLOG_BIN",
    "xelab": "XELAB_BIN",
    "xsim": "XSIM_BIN",
}
VIVADO_TOOL_FILENAMES = {
    "xvlog": ("xvlog.bat", "xvlog"),
    "xelab": ("xelab.bat", "xelab"),
    "xsim": ("xsim.bat", "xsim"),
}
VIVADO_BIN_DIR_ENV_VARS = ("VIVADO_BIN_DIR", "RDI_BINROOT")
VIVADO_ROOT_ENV_VARS = ("VIVADO_ROOT", "VIVADO_HOME")
VIVADO_BIN_ENV_VAR = "VIVADO_BIN"
XPM_SOURCE_RELATIVE_PATHS = (
    "data/ip/xpm/xpm_cdc/hdl/xpm_cdc.sv",
    "data/ip/xpm/xpm_memory/hdl/xpm_memory.sv",
    "data/ip/xpm/xpm_fifo/hdl/xpm_fifo.sv",
)
XPM_TOKEN_RE = re.compile(r"\bxpm_[a-zA-Z0-9_]+\b")
HDL_LOCATION_SUFFIXES = {".v", ".vh", ".sv", ".svh", ".f"}


def ensure_temp_dir() -> str:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return str(TMP_ROOT)


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    tmp_dir = ensure_temp_dir()
    env["TMP"] = tmp_dir
    env["TEMP"] = tmp_dir
    return env


def build_vivado_runtime_env() -> dict[str, str]:
    env = build_runtime_env()
    user_root = TMP_ROOT / "vivado-user"
    roaming_dir = user_root / "Roaming"
    local_dir = user_root / "Local"
    temp_dir = user_root / "Temp"
    home_dir = user_root / "Home"
    for directory in (roaming_dir, local_dir, temp_dir, home_dir):
        directory.mkdir(parents=True, exist_ok=True)
    env["APPDATA"] = str(roaming_dir.resolve())
    env["LOCALAPPDATA"] = str(local_dir.resolve())
    env["TMP"] = str(temp_dir.resolve())
    env["TEMP"] = str(temp_dir.resolve())
    env["HOME"] = str(home_dir.resolve())
    env["USERPROFILE"] = str(home_dir.resolve())
    env["XILINX_LOCAL_USER_DATA"] = str(local_dir.resolve())
    if os.name == "nt":
        home_path = home_dir.resolve()
        env["HOMEDRIVE"] = home_path.drive
        relative_home = "\\" + str(home_path).replace(home_path.drive, "", 1).replace("/", "\\").lstrip("\\")
        env["HOMEPATH"] = relative_home
    return env


def simulation_support_range() -> dict:
    payload = dict(LANGUAGE_SUPPORT_RANGE)
    payload["execution_backend"] = [
        "iverilog + vvp (default)",
        "xvlog + xelab + xsim (optional)",
    ]
    payload["execution_scope"] = [
        "compile and elaborate simulation inputs with Icarus Verilog",
        "execute compiled images with vvp",
        "optionally compile, elaborate, and run with Vivado xsim",
        "capture stdout and stderr",
        "report emitted waveform artifact paths without analyzing them",
    ]
    payload["execution_limitations"] = [
        "no waveform interpretation",
        "no automatic UVM orchestration",
        "no GUI-driven waveform inspection",
        "no multi-backend comparison scheduling in stage 2",
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


def iter_existing_drive_roots() -> list[Path]:
    roots: list[Path] = []
    if os.name != "nt":
        return roots
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:/")
        try:
            if root.exists():
                roots.append(root)
        except OSError:
            continue
    return roots


def version_sort_key(path: Path) -> tuple:
    text = path.name
    parts: list[int | str] = []
    for chunk in re.split(r"(\d+)", text):
        if not chunk:
            continue
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk.lower())
    return tuple(parts)


def iter_vivado_bin_dir_candidates() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []

    for env_var in VIVADO_BIN_DIR_ENV_VARS:
        configured = os.environ.get(env_var)
        if configured:
            candidates.append((Path(configured).expanduser(), f"environment:{env_var}"))

    for env_var in VIVADO_ROOT_ENV_VARS:
        configured = os.environ.get(env_var)
        if configured:
            candidates.append((Path(configured).expanduser() / "bin", f"environment:{env_var}"))

    configured_vivado_bin = os.environ.get(VIVADO_BIN_ENV_VAR)
    if configured_vivado_bin:
        candidates.append((Path(configured_vivado_bin).expanduser().parent, f"environment:{VIVADO_BIN_ENV_VAR}"))

    for env_var in VIVADO_TOOL_ENV_VARS.values():
        configured = os.environ.get(env_var)
        if configured:
            candidates.append((Path(configured).expanduser().parent, f"environment:{env_var}_sibling"))

    repo_local = REPO_ROOT / "tools" / "vivado" / "current" / "bin"
    candidates.append((repo_local, "repo_local"))

    for executable_name in VIVADO_TOOL_FILENAMES["xsim"]:
        found = shutil.which(executable_name)
        if found:
            candidates.append((Path(found).resolve().parent, "path"))
            break

    if os.name == "nt":
        for root in iter_existing_drive_roots():
            for vendor_dir_name in ("Xilinx", "XILINX"):
                vivado_parent = root / vendor_dir_name / "Vivado"
                if not vivado_parent.exists():
                    continue
                try:
                    version_dirs = sorted(
                        [path for path in vivado_parent.iterdir() if path.is_dir()],
                        key=version_sort_key,
                        reverse=True,
                    )
                except OSError:
                    continue
                for version_dir in version_dirs:
                    candidates.append((version_dir / "bin", "common_install"))

    deduped: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for directory, origin in candidates:
        try:
            resolved = directory.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((resolved, origin))
    return deduped


def resolve_xsim_toolchain() -> dict | None:
    resolved_tools: dict[str, str] = {}
    tool_origins: dict[str, str] = {}

    for tool_name, env_var in VIVADO_TOOL_ENV_VARS.items():
        configured = os.environ.get(env_var)
        if not configured:
            continue
        candidate = Path(configured).expanduser()
        if candidate.exists():
            resolved_tools[tool_name] = str(candidate.resolve())
            tool_origins[tool_name] = "environment"

    for bin_dir, origin in iter_vivado_bin_dir_candidates():
        for tool_name, filenames in VIVADO_TOOL_FILENAMES.items():
            if tool_name in resolved_tools:
                continue
            for filename in filenames:
                candidate = bin_dir / filename
                if not candidate.exists():
                    continue
                resolved_tools[tool_name] = str(candidate.resolve())
                tool_origins[tool_name] = origin
                break

    missing_tools = [tool_name for tool_name in VIVADO_TOOL_FILENAMES if tool_name not in resolved_tools]
    if missing_tools:
        return {
            "backend": "xsim",
            "status": "environment_error",
            "category": "backend_not_found",
            "message": f"Vivado xsim toolchain is incomplete: missing {', '.join(missing_tools)}",
            "missing_tools": missing_tools,
        }

    reference_tool = Path(resolved_tools["xsim"]).resolve()
    vivado_root = reference_tool.parent.parent
    glbl_path = resolve_vivado_glbl_path(vivado_root)
    if glbl_path is None:
        return {
            "backend": "xsim",
            "status": "environment_error",
            "category": "missing_dependency",
            "message": "Vivado glbl.v was not found relative to the resolved xsim toolchain",
            "backend_tools": resolved_tools,
            "tool_origins": tool_origins,
            "vivado_root": str(vivado_root),
        }

    return {
        "backend": "xsim",
        "status": "ok",
        "category": "backend_ready",
        "backend_path": resolved_tools["xsim"],
        "backend_origin": tool_origins["xsim"],
        "backend_tools": resolved_tools,
        "tool_origins": tool_origins,
        "vivado_root": str(vivado_root),
        "glbl_path": str(glbl_path),
    }


def probe_xsim_backend() -> dict:
    resolution = resolve_xsim_toolchain()
    if resolution is None or resolution["status"] != "ok":
        return resolution or {
            "backend": "xsim",
            "status": "environment_error",
            "category": "backend_not_found",
            "message": "Vivado xsim toolchain could not be resolved",
        }

    env = build_vivado_runtime_env()
    try:
        proc = run_command([resolution["backend_path"], "--version"], env)
    except OSError as exc:
        return {
            "backend": "xsim",
            "backend_path": resolution["backend_path"],
            "backend_origin": resolution["backend_origin"],
            "backend_tools": resolution["backend_tools"],
            "tool_origins": resolution["tool_origins"],
            "vivado_root": resolution["vivado_root"],
            "glbl_path": resolution["glbl_path"],
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": str(exc),
        }

    banner = (proc.stdout or proc.stderr).strip()
    if proc.returncode != 0 and "vivado simulator" not in banner.lower():
        return {
            "backend": "xsim",
            "backend_path": resolution["backend_path"],
            "backend_origin": resolution["backend_origin"],
            "backend_tools": resolution["backend_tools"],
            "tool_origins": resolution["tool_origins"],
            "vivado_root": resolution["vivado_root"],
            "glbl_path": resolution["glbl_path"],
            "status": "environment_error",
            "category": "backend_not_runnable",
            "message": "xsim returned non-zero during version probe",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    summary = banner.splitlines()[0] if banner else "xsim probe succeeded"
    payload = dict(resolution)
    payload.update(
        {
            "tmp_dir": ensure_temp_dir(),
            "version_summary": summary,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    )
    return payload


def resolve_vivado_glbl_path(vivado_root: str | Path) -> Path | None:
    candidate = Path(vivado_root) / "data" / "verilog" / "src" / "glbl.v"
    if candidate.exists():
        return candidate.resolve()
    return None


def resolve_vivado_xpm_sources(vivado_root: str | Path) -> list[str]:
    resolved: list[str] = []
    for relative_path in XPM_SOURCE_RELATIVE_PATHS:
        candidate = Path(vivado_root) / relative_path
        if candidate.exists():
            resolved.append(str(candidate.resolve()))
    return resolved


def detect_xpm_usage(source_files: list[str]) -> bool:
    for source_file in source_files:
        path = Path(source_file)
        if path.suffix.lower() not in {".v", ".sv", ".vh", ".svh"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if XPM_TOKEN_RE.search(text):
            return True
    return False


def filter_hdl_locations(locations: list[dict]) -> list[dict]:
    filtered: list[dict] = []
    for location in locations:
        file_text = location.get("file", "")
        if Path(file_text).suffix.lower() not in HDL_LOCATION_SUFFIXES:
            continue
        filtered.append(location)
    return filtered


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
    if detect_runtime_failure_markers(proc_stdout, proc_stderr):
        return "run_error", "testbench_failure"
    return "run_error", "simulation_failed"


def detect_runtime_failure_markers(proc_stdout: str, proc_stderr: str) -> list[str]:
    matches: list[str] = []
    for raw_line in "\n".join(part for part in [proc_stdout, proc_stderr] if part).splitlines():
        line = raw_line.strip()
        lowered = line.lower()
        if not lowered:
            continue
        if any(marker in lowered for marker in RUNTIME_FAILURE_MARKERS):
            matches.append(line)
            continue
        if lowered.startswith("error:"):
            matches.append(line)
            continue
        if " error:" in lowered:
            matches.append(line)
            continue
        if lowered.startswith("fail:") or " fail:" in lowered:
            matches.append(line)
            continue
    return matches


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
