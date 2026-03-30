#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = REPO_ROOT / ".tmp" / "verilog-language-and-syntax"

LOCATION_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<message>.+)$"
)

SUPPORTED_INPUT_SUFFIXES = {".v", ".vh", ".sv", ".svh", ".f"}
SOURCE_INPUT_SUFFIXES = {".v", ".sv", ".vh", ".svh"}
COMPILATION_UNIT_SUFFIXES = {".v", ".sv"}
HEADER_SUFFIXES = {".vh", ".svh"}

SUPPORT_RANGE = {
    "baseline": "Verilog-2005",
    "default_target": "RTL-oriented SystemVerilog subset",
    "file_types": [".v", ".vh", ".sv", ".svh", ".f"],
    "clearly_supported": [
        "modules",
        "parameters and localparams",
        "continuous assignments",
        "always/always_comb/always_ff/always_latch",
        "if/case/for/while/repeat/generate",
        "tasks and functions",
        "logic/wire/reg/bit",
        "typedef/enum/struct",
        "simple package/import usage",
        "standard preprocessor directives",
    ],
    "best_effort": [
        "interfaces and modports",
        "assertions",
        "bind",
        "program",
        "checker",
        "DPI-related declarations",
    ],
    "excluded_by_default": [
        "UVM",
        "class-based verification",
        "randomize/constraint",
        "covergroups",
        "mailbox/semaphore",
        "mixed-language assumptions",
    ],
}


def ensure_temp_dir() -> str:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return str(TMP_ROOT)


def build_runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    tmp_dir = ensure_temp_dir()
    env["TMP"] = tmp_dir
    env["TEMP"] = tmp_dir
    return env


def resolve_backend_path(env_var: str, executable_name: str, local_candidates: list[str] | None = None) -> str | None:
    configured = os.environ.get(env_var)
    if configured:
        path = Path(configured)
        if path.exists():
            return str(path)
    for candidate in local_candidates or []:
        path = REPO_ROOT / candidate
        if path.exists():
            return str(path)
    found = shutil.which(executable_name)
    if found:
        return found
    return None


def parse_locations(text: str) -> list[dict]:
    locations: list[dict] = []
    for raw_line in text.splitlines():
        match = LOCATION_RE.match(raw_line.strip())
        if not match:
            continue
        entry = {
            "file": match.group("file"),
            "line": int(match.group("line")),
            "message": match.group("message").strip(),
        }
        column = match.group("column")
        if column is not None:
            entry["column"] = int(column)
        locations.append(entry)
    return locations


def classify_backend_failure(text: str) -> tuple[str, str]:
    lowered = text.lower()
    if any(token in lowered for token in ["sorry:", "not supported", "unsupported", "sorry, i don't know"]):
        return "unsupported_feature", "unsupported_feature"
    if "syntax error" in lowered or "invalid module item" in lowered:
        return "syntax_error", "syntax_error"
    if "include file" in lowered or "no such file or directory" in lowered:
        return "input_error", "missing_dependency"
    if "unable to find" in lowered or "no top level modules" in lowered:
        return "elaboration_error", "elaboration_error"
    return "input_error", "tool_error"


def make_stage_result(
    *,
    backend: str,
    status: str,
    category: str,
    message: str,
    command: list[str] | None = None,
    stdout: str = "",
    stderr: str = "",
    locations: list[dict] | None = None,
) -> dict:
    return {
        "backend": backend,
        "status": status,
        "category": category,
        "message": message,
        "command": command or [],
        "stdout": stdout,
        "stderr": stderr,
        "locations": locations or [],
    }


def run_command(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, env=env, check=False)
