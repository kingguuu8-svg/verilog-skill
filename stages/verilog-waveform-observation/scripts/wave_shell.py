#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex

from waveform_support import (
    allocate_session_id,
    delete_session,
    find_next_event,
    load_waveform_selection,
    make_render_payload,
    normalize_signal_tokens,
    save_session,
)


HELP_TEXT = """Commands:
  show
  <signal> rise
  <signal> fall
  <signal> change
  set --signals sigA sigB sigC --window 20000ps [--anchor 5000ps]
  quit
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive shell for stage-3 waveform observation")
    parser.add_argument("wave_file", help="Path to the VCD or WDB file")
    parser.add_argument("--signals", nargs="+", required=True, help="Signal names to observe")
    parser.add_argument("--window", required=True, help="Observation window length")
    parser.add_argument("--anchor", help="Observation anchor time")
    return parser.parse_args()


def print_render(payload: dict) -> None:
    print()
    print(f"session: {payload['session_id']}")
    print(f"wave_file: {payload['wave_file']}")
    print(f"window: {payload['render']['anchor_time']} -> {payload['render']['end_time']}")
    for line in payload["rendered_text"]:
        print(line)
    print()


def parse_set_command(command_text: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--signals", nargs="+", required=True)
    parser.add_argument("--window", required=True)
    parser.add_argument("--anchor")
    tokens = shlex.split(command_text)
    if tokens and tokens[0] == "set":
        tokens = tokens[1:]
    return parser.parse_args(tokens)


def main() -> int:
    args = parse_args()
    signal_tokens = normalize_signal_tokens(args.signals)
    session, error = load_waveform_selection(args.wave_file, signal_tokens, args.window, args.anchor)
    if error is not None:
        print(error["message"])
        return 1

    session_id = allocate_session_id()
    save_session(session_id, session)
    payload = make_render_payload(session, "Waveform observation session opened")
    payload["session_id"] = session_id
    print_render(payload)
    print(HELP_TEXT)

    while True:
        try:
            raw_command = input("wave> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            delete_session(session_id)
            return 0

        if not raw_command:
            continue
        if raw_command in {"quit", "exit"}:
            delete_session(session_id)
            return 0
        if raw_command == "help":
            print(HELP_TEXT)
            continue
        if raw_command == "show":
            payload = make_render_payload(session, "Waveform window rendered")
            payload["session_id"] = session_id
            print_render(payload)
            continue
        if raw_command.startswith("set "):
            try:
                parsed = parse_set_command(raw_command)
            except SystemExit:
                print("Invalid set command. Use: set --signals sigA sigB --window 20000ps [--anchor 5000ps]")
                continue
            refreshed, refresh_error = load_waveform_selection(
                session["wave_file"],
                normalize_signal_tokens(parsed.signals),
                parsed.window,
                parsed.anchor,
            )
            if refresh_error is not None:
                print(refresh_error["message"])
                continue
            session = refreshed
            save_session(session_id, session)
            payload = make_render_payload(session, "Waveform observation session updated")
            payload["session_id"] = session_id
            print_render(payload)
            continue

        pieces = shlex.split(raw_command)
        if len(pieces) != 2:
            print("Unsupported command. Type help for the supported command set.")
            continue

        signal_name, edge = pieces
        if edge not in {"rise", "fall", "change"}:
            print("Edge selector must be rise, fall, or change.")
            continue

        next_anchor, next_error = find_next_event(session, signal_name, edge)
        if next_error is not None:
            print(next_error["message"])
            continue
        session["anchor_ticks"] = int(next_anchor)
        save_session(session_id, session)
        payload = make_render_payload(session, "Waveform anchor moved to the next requested event")
        payload["session_id"] = session_id
        print_render(payload)


if __name__ == "__main__":
    raise SystemExit(main())
