#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

from checker_support import REPO_ROOT


def make_error(message: str, **extra: str) -> dict:
    payload = {
        "status": "input_error",
        "message": message,
    }
    payload.update(extra)
    return payload


def resolve_destination(path_text: str) -> tuple[Path | None, str | None]:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = (REPO_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    try:
        candidate.relative_to(REPO_ROOT)
    except ValueError:
        return None, f"Destination must stay inside the repository: {candidate}"
    return candidate, None


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def prepare_destination(source_root: Path, destination_root: Path, force: bool) -> tuple[bool, str]:
    source_root = source_root.resolve()
    destination_root = destination_root.resolve()

    if _is_within(source_root, destination_root) or _is_within(destination_root, source_root):
        return False, f"Source and destination must not overlap: {source_root} <-> {destination_root}"

    if destination_root.exists():
        if not force:
            return False, f"Destination already exists: {destination_root}. Use --force to replace it"
        shutil.rmtree(destination_root)

    destination_root.mkdir(parents=True, exist_ok=True)
    return True, "destination ready"


def _copy_entry(entry: Path, destination_root: Path) -> None:
    target = destination_root / entry.name
    if entry.is_dir():
        shutil.copytree(entry, target)
    else:
        shutil.copy2(entry, target)


def copy_named_entries(source_root: Path, destination_root: Path, entry_names: list[str]) -> list[str]:
    copied: list[str] = []
    for name in entry_names:
        entry = source_root / name
        if not entry.exists():
            continue
        _copy_entry(entry, destination_root)
        copied.append(name)
    return copied


def copy_globbed_entries(source_root: Path, destination_root: Path, patterns: list[str]) -> list[str]:
    selected: dict[str, Path] = {}
    for pattern in patterns:
        for entry in sorted(source_root.glob(pattern)):
            selected.setdefault(entry.name, entry)

    copied: list[str] = []
    for name, entry in selected.items():
        _copy_entry(entry, destination_root)
        copied.append(name)
    return copied
