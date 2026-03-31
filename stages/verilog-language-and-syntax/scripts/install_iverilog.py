#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from install_support import copy_named_entries, make_error, prepare_destination, resolve_destination
from probe_backend import probe_backend


EXECUTABLE_NAMES = ("iverilog.exe", "iverilog")
REQUIRED_SUBDIRECTORIES = ("bin", "lib")
OPTIONAL_SUBDIRECTORIES = ("include", "share")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install an existing Icarus Verilog tree into the repo-local tool layout")
    parser.add_argument("--source-root", help="Existing Icarus install root containing bin/ and lib/")
    parser.add_argument("--source-bin", help="Path to an existing iverilog executable inside an install root")
    parser.add_argument(
        "--destination",
        default="tools/iverilog/current",
        help="Repo-local install root, relative to the repository by default",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing repo-local install at the destination",
    )
    return parser.parse_args()


def find_root_from_candidate(candidate_text: str) -> tuple[Path | None, str | None]:
    candidate = Path(candidate_text).expanduser()
    if not candidate.exists():
        return None, f"Path does not exist: {candidate}"

    if candidate.is_file():
        if candidate.name.lower() not in EXECUTABLE_NAMES:
            return None, f"Path is not an iverilog executable: {candidate}"
        if candidate.parent.name.lower() == "bin":
            return candidate.parent.parent.resolve(), None
        return candidate.parent.resolve(), None

    direct_bin = candidate / "bin"
    if any((direct_bin / name).exists() for name in EXECUTABLE_NAMES):
        return candidate.resolve(), None
    if candidate.name.lower() == "bin" and any((candidate / name).exists() for name in EXECUTABLE_NAMES):
        return candidate.parent.resolve(), None
    if any((candidate / name).exists() for name in EXECUTABLE_NAMES):
        return candidate.resolve(), None
    return None, f"Could not find an iverilog executable under: {candidate}"


def resolve_source_root(args: argparse.Namespace) -> tuple[Path | None, str | None, str | None]:
    if args.source_root and args.source_bin:
        return None, None, "Use either --source-root or --source-bin, not both"
    if args.source_root:
        root, error = find_root_from_candidate(args.source_root)
        return root, "argument:source-root", error
    if args.source_bin:
        root, error = find_root_from_candidate(args.source_bin)
        return root, "argument:source-bin", error

    configured = os.environ.get("IVERILOG_BIN")
    if configured:
        root, error = find_root_from_candidate(configured)
        return root, "environment:IVERILOG_BIN", error
    return None, None, "Provide --source-root/--source-bin or set IVERILOG_BIN for one-time bootstrap"


def validate_source_root(root: Path) -> tuple[Path | None, str | None]:
    missing = [name for name in REQUIRED_SUBDIRECTORIES if not (root / name).exists()]
    if missing:
        return None, f"Install root is missing required directories: {', '.join(missing)}"

    for name in EXECUTABLE_NAMES:
        candidate = root / "bin" / name
        if candidate.exists():
            return candidate, None
    return None, f"Install root does not contain {' or '.join(EXECUTABLE_NAMES)} under bin/"


def main() -> int:
    args = parse_args()

    source_root, source_origin, source_error = resolve_source_root(args)
    if source_error is not None or source_root is None:
        print(json.dumps(make_error(source_error or "Unable to resolve source install"), indent=2))
        return 2

    backend_source, validation_error = validate_source_root(source_root)
    if validation_error is not None or backend_source is None:
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
    copied_entries = copy_named_entries(
        source_root,
        destination_root,
        [name for name in [*REQUIRED_SUBDIRECTORIES, *OPTIONAL_SUBDIRECTORIES] if (source_root / name).exists()],
    )

    original = os.environ.pop("IVERILOG_BIN", None)
    try:
        probe = probe_backend("iverilog")
    finally:
        if original is not None:
            os.environ["IVERILOG_BIN"] = original

    payload = {
        "status": probe["status"],
        "message": "repo-local Icarus install is ready" if probe["status"] == "ok" else "repo-local Icarus install copied but probe failed",
        "source_origin": source_origin,
        "source_root": str(source_root),
        "source_backend": str(backend_source),
        "destination_root": str(destination_root),
        "copied_subdirectories": copied_entries,
        "probe": probe,
    }
    print(json.dumps(payload, indent=2))
    return 0 if probe["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
