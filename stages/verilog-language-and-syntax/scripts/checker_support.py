#!/usr/bin/env python3
from __future__ import annotations

import os
import locale
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


def resolve_backend_path(
    env_var: str,
    executable_name: str,
    local_candidates: list[str] | None = None,
    allow_path: bool = True,
) -> dict[str, str] | None:
    configured = os.environ.get(env_var)
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return {
                "path": str(path.resolve()),
                "origin": "environment",
            }
    for candidate in local_candidates or []:
        path = (REPO_ROOT / candidate).resolve()
        if path.exists():
            return {
                "path": str(path),
                "origin": "repo_local",
            }
    if allow_path:
        found = shutil.which(executable_name)
        if found:
            return {
                "path": str(Path(found).resolve()),
                "origin": "path",
            }
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


def decode_stream(raw: bytes | None) -> str:
    if not raw:
        return ""

    encodings: list[str] = []
    for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk", "cp936"):
        if encoding and encoding not in encodings:
            encodings.append(encoding)

    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue

    return raw.decode("utf-8", errors="replace")


def run_command(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(command, capture_output=True, text=False, env=env, check=False)
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=decode_stream(proc.stdout),
        stderr=decode_stream(proc.stderr),
    )


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
