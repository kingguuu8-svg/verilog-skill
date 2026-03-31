#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from install_support import copy_globbed_entries, make_error, prepare_destination, resolve_destination
from probe_backend import probe_backend


REQUIRED_EXECUTABLE_BASES = (
    "verible-verilog-syntax",
    "verible-verilog-lint",
)
COPY_PATTERNS = [
    "verible-*",
    "*.dll",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install an existing Verible binary bundle into the repo-local tool layout")
    parser.add_argument("--source-root", help="Existing Verible directory containing verible-* executables")
    parser.add_argument("--source-bin", help="Path to one existing verible-* executable inside the source directory")
    parser.add_argument(
        "--destination",
        default="tools/verible/current",
        help="Repo-local install root, relative to the repository by default",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing repo-local install at the destination",
    )
    return parser.parse_args()


def _find_executable(root: Path, executable_base: str) -> Path | None:
    for name in (f"{executable_base}.exe", executable_base):
        candidate = root / name
        if candidate.exists():
            return candidate.resolve()
    return None


def find_root_from_candidate(candidate_text: str) -> tuple[Path | None, str | None]:
    candidate = Path(candidate_text).expanduser()
    if not candidate.exists():
        return None, f"Path does not exist: {candidate}"

    if candidate.is_file():
        if not candidate.name.lower().startswith("verible-"):
            return None, f"Path is not a Verible executable: {candidate}"
        return candidate.parent.resolve(), None

    if any(_find_executable(candidate, executable_base) for executable_base in REQUIRED_EXECUTABLE_BASES):
        return candidate.resolve(), None
    return None, f"Could not find required Verible executables under: {candidate}"


def resolve_source_root(args: argparse.Namespace) -> tuple[Path | None, str | None, str | None]:
    if args.source_root and args.source_bin:
        return None, None, "Use either --source-root or --source-bin, not both"
    if args.source_root:
        root, error = find_root_from_candidate(args.source_root)
        return root, "argument:source-root", error
    if args.source_bin:
        root, error = find_root_from_candidate(args.source_bin)
        return root, "argument:source-bin", error

    for env_var in ("VERIBLE_VERILOG_SYNTAX_BIN", "VERIBLE_VERILOG_LINT_BIN"):
        configured = os.environ.get(env_var)
        if not configured:
            continue
        root, error = find_root_from_candidate(configured)
        return root, f"environment:{env_var}", error
    return None, None, "Provide --source-root/--source-bin or set VERIBLE_VERILOG_SYNTAX_BIN/VERIBLE_VERILOG_LINT_BIN for one-time bootstrap"


def validate_source_root(root: Path) -> tuple[dict[str, str] | None, str | None]:
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for executable_base in REQUIRED_EXECUTABLE_BASES:
        candidate = _find_executable(root, executable_base)
        if candidate is None:
            missing.append(executable_base)
            continue
        resolved[executable_base] = str(candidate)
    if missing:
        return None, f"Source directory is missing required Verible executables: {', '.join(missing)}"
    return resolved, None


def main() -> int:
    args = parse_args()

    source_root, source_origin, source_error = resolve_source_root(args)
    if source_error is not None or source_root is None:
        print(json.dumps(make_error(source_error or "Unable to resolve source install"), indent=2))
        return 2

    resolved_binaries, validation_error = validate_source_root(source_root)
    if validation_error is not None or resolved_binaries is None:
        print(json.dumps(make_error(validation_error or "Source install is invalid", source_root=str(source_root)), indent=2))
        return 2

    destination_root, destination_error = resolve_destination(args.destination)
    if destination_error is not None or destination_root is None:
        print(json.dumps(make_error(destination_error or "Destination is invalid", source_root=str(source_root)), indent=2))
        return 2

    ready, ready_message = prepare_destination(source_root, destination_root, args.force)
    if not ready:
        print(
            json.dumps(
                make_error(
                    ready_message,
                    source_root=str(source_root),
                    destination_root=str(destination_root),
                ),
                indent=2,
            )
        )
        return 2

    copied_entries = copy_globbed_entries(source_root, destination_root, COPY_PATTERNS)

    syntax_original = os.environ.pop("VERIBLE_VERILOG_SYNTAX_BIN", None)
    lint_original = os.environ.pop("VERIBLE_VERILOG_LINT_BIN", None)
    try:
        syntax_probe = probe_backend("verible")
        lint_probe = probe_backend("verible-lint")
    finally:
        if syntax_original is not None:
            os.environ["VERIBLE_VERILOG_SYNTAX_BIN"] = syntax_original
        if lint_original is not None:
            os.environ["VERIBLE_VERILOG_LINT_BIN"] = lint_original

    status = "ok" if syntax_probe["status"] == "ok" and lint_probe["status"] == "ok" else "environment_error"
    payload = {
        "status": status,
        "message": "repo-local Verible install is ready" if status == "ok" else "repo-local Verible install copied but probe failed",
        "source_origin": source_origin,
        "source_root": str(source_root),
        "resolved_binaries": resolved_binaries,
        "destination_root": str(destination_root),
        "copied_entries": copied_entries,
        "probe": {
            "verible": syntax_probe,
            "verible-lint": lint_probe,
        },
    }
    print(json.dumps(payload, indent=2))
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
