from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


EVENT_PREFIX = "SKILL_EVT|"
EVENT_INDEX_FORMAT = "verilog-skill-tb-event-index-v1"


def split_escaped_fields(text: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "|":
            fields.append("".join(current))
            current = []
            continue
        current.append(char)
    if escaped:
        current.append("\\")
    fields.append("".join(current))
    return fields


def decode_field_value(text: str) -> str:
    result: list[str] = []
    escaped = False
    for char in text:
        if escaped:
            result.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        result.append(char)
    if escaped:
        result.append("\\")
    return "".join(result)


def parse_int_like(text: str) -> int | None:
    candidate = text.strip()
    if not candidate:
        return None
    sign = 1
    if candidate[0] in "+-":
        if candidate[0] == "-":
            sign = -1
        candidate = candidate[1:]
    if not candidate:
        return None
    if candidate.startswith(("0x", "0X")):
        try:
            return sign * int(candidate, 16)
        except ValueError:
            return None
    if candidate.isdigit():
        return sign * int(candidate, 10)
    return None


def parse_event_line(line: str, *, stream: str, line_number: int) -> tuple[dict | None, dict | None]:
    if EVENT_PREFIX not in line:
        return None, None
    payload = line.split(EVENT_PREFIX, 1)[1].strip()
    if not payload:
        return None, {
            "stream": stream,
            "line_number": line_number,
            "line_text": line.rstrip("\n"),
            "message": "Structured TB event line is missing key=value fields",
        }

    fields: dict[str, str] = {}
    for item in split_escaped_fields(payload):
        if not item:
            continue
        if "=" not in item:
            return None, {
                "stream": stream,
                "line_number": line_number,
                "line_text": line.rstrip("\n"),
                "message": f"Structured TB event field '{item}' is missing '='",
            }
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            return None, {
                "stream": stream,
                "line_number": line_number,
                "line_text": line.rstrip("\n"),
                "message": "Structured TB event contains an empty key",
            }
        fields[key] = decode_field_value(value.strip())

    if "kind" not in fields or not fields["kind"]:
        return None, {
            "stream": stream,
            "line_number": line_number,
            "line_text": line.rstrip("\n"),
            "message": "Structured TB event is missing the required 'kind' field",
        }

    event = {
        "stream": stream,
        "line_number": line_number,
        "kind": fields["kind"],
        "fields": fields,
        "raw_line": line.rstrip("\n"),
    }
    if "name" in fields:
        event["name"] = fields["name"]
    if "signal" in fields:
        event["signal"] = fields["signal"]
    time_ps = parse_int_like(fields.get("time_ps", ""))
    if time_ps is not None:
        event["time_ps"] = time_ps
    elif "time_ps" in fields:
        event["time_text"] = fields["time_ps"]
    return event, None


def extract_tb_events(stdout: str, stderr: str) -> tuple[list[dict], list[dict]]:
    events: list[dict] = []
    errors: list[dict] = []
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        for index, line in enumerate(text.splitlines(), start=1):
            event, error = parse_event_line(line, stream=stream, line_number=index)
            if event is not None:
                events.append(event)
            if error is not None:
                errors.append(error)
    return events, errors


def summarize_tb_events(events: list[dict], errors: list[dict]) -> dict:
    by_kind = Counter(event["kind"] for event in events)
    times = [int(event["time_ps"]) for event in events if "time_ps" in event]
    return {
        "event_count": len(events),
        "parse_error_count": len(errors),
        "kinds": dict(sorted(by_kind.items())),
        "first_time_ps": min(times) if times else None,
        "last_time_ps": max(times) if times else None,
    }


def build_tb_event_index(
    *,
    run_log: Path | None,
    stdout: str,
    stderr: str,
    output_path: Path,
) -> tuple[Path | None, dict | None]:
    events, errors = extract_tb_events(stdout, stderr)
    if not events and not errors:
        return None, None

    summary = summarize_tb_events(events, errors)
    payload = {
        "format": EVENT_INDEX_FORMAT,
        "protocol_prefix": EVENT_PREFIX,
        "run_log": str(run_log) if run_log is not None else None,
        "summary": summary,
        "events": events,
        "parse_errors": errors,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path, summary
