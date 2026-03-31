#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tb_event_support import build_tb_event_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract structured TB event lines into an index file")
    parser.add_argument("run_log", help="Path to a stage-2 run.log file")
    parser.add_argument("--output", help="Optional output path for the extracted event index JSON")
    return parser.parse_args()


def split_run_log_sections(text: str) -> tuple[str, str]:
    stdout_marker = "=== STDOUT ===\n"
    stderr_marker = "\n=== STDERR ===\n"
    if text.startswith(stdout_marker) and stderr_marker in text:
        middle = text[len(stdout_marker) :]
        stdout, stderr = middle.split(stderr_marker, 1)
        return stdout, stderr
    return text, ""


def main() -> int:
    args = parse_args()
    run_log = Path(args.run_log).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else run_log.with_name("tb-events.json")
    text = run_log.read_text(encoding="utf-8")
    stdout, stderr = split_run_log_sections(text)
    index_path, summary = build_tb_event_index(
        run_log=run_log,
        stdout=stdout,
        stderr=stderr,
        output_path=output_path,
    )
    payload = {
        "status": "ok" if index_path is not None else "no_events",
        "run_log": str(run_log),
        "tb_event_index": str(index_path) if index_path is not None else None,
        "summary": summary,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
