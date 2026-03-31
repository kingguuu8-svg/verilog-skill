#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from waveform_support import build_vcd_index, vcd_index_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a sidecar index for a VCD waveform")
    parser.add_argument("wave_file", help="Path to the VCD waveform file")
    parser.add_argument(
        "--checkpoint-bytes",
        type=int,
        default=256 * 1024 * 1024,
        help="Approximate byte stride between sparse checkpoints",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild the index even if a valid sidecar index already exists",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wave_file = Path(args.wave_file).expanduser()
    if not wave_file.is_absolute():
        wave_file = (Path.cwd() / wave_file).resolve()
    else:
        wave_file = wave_file.resolve()

    index_path, error = build_vcd_index(
        wave_file,
        force=args.force,
        checkpoint_stride_bytes=max(int(args.checkpoint_bytes), 1),
    )
    if error is not None:
        print(json.dumps(error, indent=2))
        return 1

    print(
        json.dumps(
            {
                "status": "ok",
                "message": "Waveform sidecar index built",
                "wave_file": str(wave_file),
                "index_file": str(index_path or vcd_index_path(wave_file)),
                "checkpoint_stride_bytes": max(int(args.checkpoint_bytes), 1),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
