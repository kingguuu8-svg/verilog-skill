#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from waveform_support import (
    list_signals,
    load_waveform_selection,
    make_render_payload,
    normalize_signal_tokens,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-3 waveform observation for VCD and XSIM WDB artifacts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-signals", help="List canonical signal names found in a waveform artifact")
    list_parser.add_argument("wave_file", help="Path to the VCD or WDB file")

    render_parser = subparsers.add_parser("render-window", help="Render one observation window from a waveform artifact")
    render_parser.add_argument("wave_file", help="Path to the VCD or WDB file")
    render_parser.add_argument("--signals", nargs="+", required=True, help="Signal names to observe")
    render_parser.add_argument("--window", required=True, help="Observation window length")
    render_parser.add_argument("--anchor", help="Observation anchor time")
    render_parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format",
    )

    return parser.parse_args()


def print_payload(payload: dict, output_format: str) -> None:
    if output_format == "text":
        for line in payload.get("rendered_text", []):
            print(line)
        return
    print(json.dumps(payload, indent=2))


def main() -> int:
    args = parse_args()
    if args.command == "list-signals":
        payload = list_signals(args.wave_file)
        print(json.dumps(payload, indent=2))
        return 0 if payload["status"] == "ok" else 1

    signal_tokens = normalize_signal_tokens(args.signals)
    session, error = load_waveform_selection(
        args.wave_file,
        signal_tokens,
        args.window,
        args.anchor,
        include_events=True,
        stop_after_window=True,
    )
    if error is not None:
        print(json.dumps(error, indent=2))
        return 1

    payload, render_error = make_render_payload(session, "Waveform window rendered")
    if render_error is not None:
        print(json.dumps(render_error, indent=2))
        return 1
    print_payload(payload, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
