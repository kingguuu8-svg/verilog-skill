#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from waveform_support import (
    allocate_session_id,
    delete_session,
    find_next_event,
    load_session,
    load_waveform_selection,
    make_render_payload,
    normalize_signal_tokens,
    save_session,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage-3 waveform observation session manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="Open a waveform observation session")
    open_parser.add_argument("wave_file", help="Path to the VCD file")
    open_parser.add_argument("--signals", nargs="+", required=True, help="Signal names to observe")
    open_parser.add_argument("--window", required=True, help="Observation window length")
    open_parser.add_argument("--anchor", help="Observation anchor time")
    open_parser.add_argument("--format", choices=["json", "text"], default="json")

    render_parser = subparsers.add_parser("render", help="Render the current window for a session")
    render_parser.add_argument("session_id", help="Session identifier")
    render_parser.add_argument("--format", choices=["json", "text"], default="json")

    edge_parser = subparsers.add_parser("next-edge", help="Move the anchor to the next matching edge")
    edge_parser.add_argument("session_id", help="Session identifier")
    edge_parser.add_argument("--signal", required=True, help="Observed signal name in the session")
    edge_parser.add_argument(
        "--edge",
        choices=["rise", "fall", "change"],
        required=True,
        help="Edge or change selector",
    )
    edge_parser.add_argument("--format", choices=["json", "text"], default="json")

    set_parser = subparsers.add_parser("set", help="Rewrite the active signal set and window configuration")
    set_parser.add_argument("session_id", help="Session identifier")
    set_parser.add_argument("--signals", nargs="+", required=True, help="Signal names to observe")
    set_parser.add_argument("--window", required=True, help="Observation window length")
    set_parser.add_argument("--anchor", help="Optional new anchor time")
    set_parser.add_argument("--format", choices=["json", "text"], default="json")

    close_parser = subparsers.add_parser("close", help="Close a waveform observation session")
    close_parser.add_argument("session_id", help="Session identifier")

    return parser.parse_args()


def print_payload(payload: dict, output_format: str) -> None:
    if output_format == "text":
        for line in payload.get("rendered_text", []):
            print(line)
        return
    print(json.dumps(payload, indent=2))


def main() -> int:
    args = parse_args()

    if args.command == "open":
        signal_tokens = normalize_signal_tokens(args.signals)
        session, error = load_waveform_selection(args.wave_file, signal_tokens, args.window, args.anchor)
        if error is not None:
            print(json.dumps(error, indent=2))
            return 1
        session_id = allocate_session_id()
        path = save_session(session_id, session)
        payload = make_render_payload(session, "Waveform observation session opened")
        payload["session_id"] = session_id
        payload["session_file"] = str(path)
        print_payload(payload, args.format)
        return 0

    if args.command == "close":
        print(json.dumps(delete_session(args.session_id), indent=2))
        return 0

    session, error = load_session(args.session_id)
    if error is not None:
        print(json.dumps(error, indent=2))
        return 1

    if args.command == "render":
        payload = make_render_payload(session, "Waveform window rendered")
        payload["session_id"] = args.session_id
        print_payload(payload, args.format)
        return 0

    if args.command == "next-edge":
        next_anchor, next_error = find_next_event(session, args.signal, args.edge)
        if next_error is not None:
            print(json.dumps(next_error, indent=2))
            return 1
        session["anchor_ticks"] = int(next_anchor)
        save_session(args.session_id, session)
        payload = make_render_payload(session, "Waveform anchor moved to the next requested event")
        payload["session_id"] = args.session_id
        print_payload(payload, args.format)
        return 0

    signal_tokens = normalize_signal_tokens(args.signals)
    anchor_text = args.anchor
    if anchor_text is None:
        anchor_text = str(session["anchor_ticks"])
    refreshed, refresh_error = load_waveform_selection(session["wave_file"], signal_tokens, args.window, anchor_text)
    if refresh_error is not None:
        print(json.dumps(refresh_error, indent=2))
        return 1
    save_session(args.session_id, refreshed)
    payload = make_render_payload(refreshed, "Waveform observation session updated")
    payload["session_id"] = args.session_id
    print_payload(payload, args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
