#!/usr/bin/env python3
from __future__ import annotations

import difflib
import json
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TMP_ROOT = REPO_ROOT / ".tmp" / "verilog-waveform-observation"
SESSION_ROOT = TMP_ROOT / "sessions"
SUPPORTED_WAVE_SUFFIXES = {".vcd"}
TIME_UNIT_TO_FS = {
    "fs": 1,
    "ps": 1_000,
    "ns": 1_000_000,
    "us": 1_000_000_000,
    "ms": 1_000_000_000_000,
    "s": 1_000_000_000_000_000,
}
REFERENCE_RE = re.compile(
    r"^(?P<name>[^\[]+?)(?:\s*\[(?P<msb>-?\d+)(?::(?P<lsb>-?\d+))?\])?$"
)
BIT_SELECT_RE = re.compile(r"^(?P<base>.+)\[(?P<index>-?\d+)\]$")
TIME_RE = re.compile(r"^(?P<value>\d+)(?P<unit>fs|ps|ns|us|ms|s)?$")
TIMESCALE_RE = re.compile(r"^(?P<value>\d+)\s*(?P<unit>fs|ps|ns|us|ms|s)$")


@dataclass
class SignalDecl:
    code: str
    canonical_name: str
    scope_path: list[str]
    base_name: str
    ref_text: str
    width: int
    msb: int | None
    lsb: int | None


@dataclass
class SelectedSignal:
    request_name: str
    display_name: str
    canonical_name: str
    code: str
    width: int
    base_width: int
    msb: int | None
    lsb: int | None
    bit_index: int | None = None


def ensure_temp_dir() -> Path:
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    return TMP_ROOT


def ensure_session_dir() -> Path:
    ensure_temp_dir()
    SESSION_ROOT.mkdir(parents=True, exist_ok=True)
    return SESSION_ROOT


def make_error_payload(
    *,
    status: str,
    category: str,
    message: str,
    details: dict | None = None,
) -> dict:
    payload = {
        "status": status,
        "category": category,
        "message": message,
    }
    if details:
        payload["details"] = details
    return payload


def normalize_signal_tokens(raw_tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in raw_tokens:
        for part in token.split(","):
            stripped = part.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


def resolve_wave_file(path_text: str) -> tuple[Path | None, dict | None]:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = (Path.cwd() / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if not candidate.exists():
        return None, make_error_payload(
            status="input_error",
            category="wave_file_missing",
            message="Waveform file does not exist",
            details={"wave_file": str(candidate)},
        )
    if candidate.suffix.lower() not in SUPPORTED_WAVE_SUFFIXES:
        return None, make_error_payload(
            status="unsupported_feature",
            category="unsupported_wave_format",
            message="Stage-3 waveform observation currently supports VCD files only",
            details={
                "wave_file": str(candidate),
                "supported_suffixes": sorted(SUPPORTED_WAVE_SUFFIXES),
            },
        )
    return candidate, None


def parse_timescale_text(text: str) -> tuple[str, int]:
    normalized = " ".join(text.split()).lower()
    match = TIMESCALE_RE.match(normalized)
    if not match:
        raise ValueError(f"Unsupported VCD timescale: {text}")
    value = int(match.group("value"))
    unit = match.group("unit")
    return f"{value}{unit}", value * TIME_UNIT_TO_FS[unit]


def parse_reference_text(ref_text: str) -> tuple[str, int | None, int | None]:
    match = REFERENCE_RE.match(ref_text.strip())
    if not match:
        raise ValueError(f"Unsupported VCD reference syntax: {ref_text}")
    name = match.group("name").strip()
    msb = match.group("msb")
    lsb = match.group("lsb")
    if msb is None:
        return name, None, None
    if lsb is None:
        value = int(msb)
        return name, value, value
    return name, int(msb), int(lsb)


def build_alias_candidates(scope_path: list[str], base_name: str) -> list[str]:
    full_parts = [*scope_path, base_name]
    aliases: list[str] = []
    for index in range(len(full_parts)):
        alias = ".".join(full_parts[index:])
        if alias not in aliases:
            aliases.append(alias)
    return aliases


def parse_vcd_header(wave_file: Path) -> dict:
    scope_stack: list[str] = []
    declarations: list[SignalDecl] = []
    alias_candidates: dict[str, list[SignalDecl]] = {}
    code_to_decl: dict[str, SignalDecl] = {}
    timescale_chunks: list[str] = []
    collecting_timescale = False
    timescale_text = "1ps"
    timescale_fs = TIME_UNIT_TO_FS["ps"]

    with wave_file.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue

            if collecting_timescale:
                if "$end" in line:
                    timescale_chunks.append(line.split("$end", maxsplit=1)[0].strip())
                    timescale_text, timescale_fs = parse_timescale_text(" ".join(timescale_chunks))
                    timescale_chunks = []
                    collecting_timescale = False
                else:
                    timescale_chunks.append(line)
                continue

            if line.startswith("$enddefinitions"):
                break
            if line.startswith("$timescale"):
                remainder = line[len("$timescale") :].strip()
                if "$end" in remainder:
                    inline_text = remainder.split("$end", maxsplit=1)[0].strip()
                    timescale_text, timescale_fs = parse_timescale_text(inline_text)
                else:
                    collecting_timescale = True
                    if remainder:
                        timescale_chunks.append(remainder)
                continue
            if line.startswith("$scope"):
                parts = line.split()
                if len(parts) >= 3:
                    scope_stack.append(parts[2])
                continue
            if line.startswith("$upscope"):
                if scope_stack:
                    scope_stack.pop()
                continue
            if line.startswith("$var"):
                parts = line.split()
                if len(parts) < 5:
                    continue
                width = int(parts[2])
                code = parts[3]
                ref_text = " ".join(parts[4:-1])
                base_name, msb, lsb = parse_reference_text(ref_text)
                decl = SignalDecl(
                    code=code,
                    canonical_name=".".join([*scope_stack, base_name]),
                    scope_path=list(scope_stack),
                    base_name=base_name,
                    ref_text=ref_text,
                    width=width,
                    msb=msb,
                    lsb=lsb,
                )
                declarations.append(decl)
                code_to_decl.setdefault(code, decl)
                for alias in build_alias_candidates(scope_stack, base_name):
                    alias_candidates.setdefault(alias, []).append(decl)

    alias_map: dict[str, str] = {}
    ambiguous_aliases: dict[str, list[str]] = {}
    for alias, decls in alias_candidates.items():
        unique_codes = {decl.code for decl in decls}
        if len(unique_codes) == 1:
            alias_map[alias] = next(iter(unique_codes))
        else:
            ambiguous_aliases[alias] = sorted({decl.canonical_name for decl in decls})

    return {
        "wave_file": str(wave_file),
        "timescale_text": timescale_text,
        "timescale_fs": timescale_fs,
        "declarations": [asdict(item) for item in declarations],
        "alias_map": alias_map,
        "ambiguous_aliases": ambiguous_aliases,
        "code_to_decl": {code: asdict(decl) for code, decl in code_to_decl.items()},
        "known_aliases": sorted(alias_candidates),
    }


def unknown_value(width: int) -> str:
    return "x" if width == 1 else ("x" * width)


def normalize_vector_value(raw_value: str, width: int) -> str:
    lowered = raw_value.lower()
    if width <= 1:
        return lowered[0]
    if len(lowered) >= width:
        return lowered[-width:]
    pad_char = lowered[0] if lowered and lowered[0] in {"x", "z"} else "0"
    return (pad_char * (width - len(lowered))) + lowered


def parse_value_change_line(line: str) -> tuple[str, str] | None:
    if not line:
        return None
    if line[0] in {"0", "1", "x", "X", "z", "Z"}:
        return line[1:].strip(), line[0].lower()
    if line[0] in {"b", "B"}:
        parts = line[1:].split()
        if len(parts) != 2:
            return None
        return parts[1], parts[0].lower()
    return None


def parse_selected_events(wave_file: Path, selected_codes: set[str], code_to_decl: dict[str, dict]) -> dict[str, list[list[int | str]]]:
    events_by_code: dict[str, list[list[int | str]]] = {code: [] for code in selected_codes}
    last_values: dict[str, str] = {}
    header_done = False
    current_time = 0

    with wave_file.open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if not header_done:
                if line.startswith("$enddefinitions"):
                    header_done = True
                continue
            if line.startswith("#"):
                current_time = int(line[1:])
                continue
            if line.startswith("$"):
                continue
            parsed = parse_value_change_line(line)
            if parsed is None:
                continue
            code, raw_value = parsed
            if code not in selected_codes:
                continue
            decl = code_to_decl[code]
            normalized = normalize_vector_value(raw_value, int(decl["width"]))
            if last_values.get(code) == normalized:
                continue
            events_by_code[code].append([current_time, normalized])
            last_values[code] = normalized

    return events_by_code


def list_signals(wave_file_text: str) -> dict:
    wave_file, wave_error = resolve_wave_file(wave_file_text)
    if wave_error is not None:
        return wave_error

    header = parse_vcd_header(wave_file)
    signals: list[dict] = []
    for decl in header["declarations"]:
        signals.append(
            {
                "canonical_name": decl["canonical_name"],
                "width": decl["width"],
                "ref_text": decl["ref_text"],
                "code": decl["code"],
            }
        )
    return {
        "status": "ok",
        "message": "Waveform signal catalog loaded",
        "wave_file": str(wave_file),
        "timescale": header["timescale_text"],
        "signals": signals,
        "ambiguous_aliases": header["ambiguous_aliases"],
    }


def resolve_selected_signals(header: dict, signal_tokens: list[str]) -> tuple[list[SelectedSignal] | None, dict | None]:
    selected: list[SelectedSignal] = []
    alias_map = header["alias_map"]
    ambiguous = header["ambiguous_aliases"]
    code_to_decl = header["code_to_decl"]
    known_aliases = header["known_aliases"]

    for token in signal_tokens:
        requested = token.strip()
        if not requested:
            continue

        bit_index: int | None = None
        base_token = requested
        bit_match = BIT_SELECT_RE.match(requested)
        if bit_match:
            base_token = bit_match.group("base").strip()
            bit_index = int(bit_match.group("index"))

        if base_token in ambiguous:
            return None, make_error_payload(
                status="input_error",
                category="ambiguous_signal_name",
                message="Signal name is ambiguous; use a hierarchical path",
                details={
                    "signal": requested,
                    "candidate_signals": ambiguous[base_token],
                },
            )

        code = alias_map.get(base_token)
        if code is None:
            suggestions = difflib.get_close_matches(base_token, known_aliases, n=5)
            return None, make_error_payload(
                status="input_error",
                category="signal_not_found",
                message="Requested signal was not found in the waveform",
                details={
                    "signal": requested,
                    "suggestions": suggestions,
                },
            )

        decl = code_to_decl[code]
        msb = decl["msb"]
        lsb = decl["lsb"]
        width = int(decl["width"])
        display_name = requested
        selected_width = width

        if bit_index is not None:
            if msb is None or lsb is None:
                return None, make_error_payload(
                    status="input_error",
                    category="invalid_bit_select",
                    message="Bit-select navigation is only available on vector signals",
                    details={
                        "signal": requested,
                        "canonical_name": decl["canonical_name"],
                    },
                )
            low = min(msb, lsb)
            high = max(msb, lsb)
            if bit_index < low or bit_index > high:
                return None, make_error_payload(
                    status="input_error",
                    category="bit_index_out_of_range",
                    message="Bit index is outside the declared vector range",
                    details={
                        "signal": requested,
                        "declared_range": f"[{msb}:{lsb}]",
                    },
                )
            selected_width = 1

        selected.append(
            SelectedSignal(
                request_name=requested,
                display_name=display_name,
                canonical_name=decl["canonical_name"],
                code=code,
                width=selected_width,
                base_width=width,
                msb=msb,
                lsb=lsb,
                bit_index=bit_index,
            )
        )

    if not selected:
        return None, make_error_payload(
            status="input_error",
            category="no_signals_selected",
            message="At least one signal must be selected for waveform observation",
        )
    return selected, None


def parse_time_value(text: str, timescale_fs: int) -> tuple[int | None, dict | None]:
    candidate = text.strip().lower().replace(" ", "")
    match = TIME_RE.match(candidate)
    if not match:
        return None, make_error_payload(
            status="input_error",
            category="invalid_time_value",
            message="Time values must be integers with optional fs/ps/ns/us/ms/s suffixes",
            details={"time_text": text},
        )
    value = int(match.group("value"))
    unit = match.group("unit")
    if unit is None:
        return value, None

    total_fs = value * TIME_UNIT_TO_FS[unit]
    if total_fs % timescale_fs != 0:
        return None, make_error_payload(
            status="input_error",
            category="time_precision_mismatch",
            message="Requested time is not aligned to the waveform timescale precision",
            details={
                "time_text": text,
                "timescale_fs": timescale_fs,
            },
        )
    return total_fs // timescale_fs, None


def format_time_ticks(ticks: int, timescale_fs: int) -> str:
    total_fs = ticks * timescale_fs
    if total_fs % TIME_UNIT_TO_FS["ps"] == 0:
        return f"{total_fs // TIME_UNIT_TO_FS['ps']}ps"
    return f"{total_fs}fs"


def observed_value(raw_value: str, selected: dict) -> str:
    bit_index = selected.get("bit_index")
    if bit_index is None:
        return raw_value
    msb = selected["msb"]
    lsb = selected["lsb"]
    if msb is None or lsb is None:
        return raw_value
    if msb >= lsb:
        position = msb - bit_index
    else:
        position = bit_index - msb
    return raw_value[position]


def value_at_anchor(events: list[list[int | str]], anchor_ticks: int, default_value: str) -> str:
    current = default_value
    for time_tick, value in events:
        if int(time_tick) > anchor_ticks:
            break
        current = str(value)
    return current


def classify_transition(old_value: str, new_value: str, width: int) -> str:
    if width == 1 and old_value == "0" and new_value == "1":
        return "rise"
    if width == 1 and old_value == "1" and new_value == "0":
        return "fall"
    if old_value == new_value:
        return new_value
    return f"value_change {old_value}->{new_value}"


def render_window(session: dict) -> dict:
    selected_signals = session["selected_signals"]
    events_by_code = session["events_by_code"]
    anchor_ticks = int(session["anchor_ticks"])
    window_ticks = int(session["window_ticks"])
    timescale_fs = int(session["timescale_fs"])
    end_ticks = anchor_ticks + window_ticks

    current_raw_by_code: dict[str, str] = {}
    for selected in selected_signals:
        code = selected["code"]
        if code in current_raw_by_code:
            continue
        default_value = unknown_value(int(selected["base_width"]))
        current_raw_by_code[code] = value_at_anchor(events_by_code[code], anchor_ticks, default_value)

    previous_values = [observed_value(current_raw_by_code[selected["code"]], selected) for selected in selected_signals]

    rows: list[dict] = []
    anchor_row = {
        "time_ticks": anchor_ticks,
        "time_text": format_time_ticks(anchor_ticks, timescale_fs),
        "kind": "anchor",
        "signals": [
            {
                "name": selected["display_name"],
                "kind": "value",
                "text": previous_values[index],
                "value": previous_values[index],
            }
            for index, selected in enumerate(selected_signals)
        ],
    }
    rows.append(anchor_row)

    times_in_window = sorted(
        {
            int(time_tick)
            for events in events_by_code.values()
            for time_tick, _value in events
            if anchor_ticks < int(time_tick) <= end_ticks
        }
    )

    for time_tick in times_in_window:
        for code, events in events_by_code.items():
            for event_time, raw_value in events:
                if int(event_time) != time_tick:
                    continue
                current_raw_by_code[code] = str(raw_value)

        row_entries: list[dict] = []
        changed = False
        next_values: list[str] = []
        for index, selected in enumerate(selected_signals):
            new_value = observed_value(current_raw_by_code[selected["code"]], selected)
            old_value = previous_values[index]
            if new_value != old_value:
                changed = True
                row_entries.append(
                    {
                        "name": selected["display_name"],
                        "kind": "event",
                        "text": classify_transition(old_value, new_value, int(selected["width"])),
                        "value": new_value,
                        "old_value": old_value,
                    }
                )
            else:
                row_entries.append(
                    {
                        "name": selected["display_name"],
                        "kind": "value",
                        "text": new_value,
                        "value": new_value,
                    }
                )
            next_values.append(new_value)

        if changed:
            rows.append(
                {
                    "time_ticks": time_tick,
                    "time_text": format_time_ticks(time_tick, timescale_fs),
                    "kind": "event",
                    "signals": row_entries,
                }
            )
        previous_values = next_values

    return {
        "anchor_ticks": anchor_ticks,
        "anchor_time": format_time_ticks(anchor_ticks, timescale_fs),
        "window_ticks": window_ticks,
        "window_length": format_time_ticks(window_ticks, timescale_fs),
        "end_ticks": end_ticks,
        "end_time": format_time_ticks(end_ticks, timescale_fs),
        "rows": rows,
    }


def render_rows_as_text(rows: list[dict]) -> list[str]:
    lines: list[str] = []
    for row in rows:
        parts = [row["time_text"]]
        for signal in row["signals"]:
            parts.append(f"{signal['name']}: {signal['text']}")
        lines.append("  ".join(parts))
    return lines


def load_waveform_selection(
    wave_file_text: str,
    signal_tokens: list[str],
    window_text: str,
    anchor_text: str | None,
) -> tuple[dict | None, dict | None]:
    wave_file, wave_error = resolve_wave_file(wave_file_text)
    if wave_error is not None:
        return None, wave_error

    header = parse_vcd_header(wave_file)
    selected_signals, signal_error = resolve_selected_signals(header, signal_tokens)
    if signal_error is not None:
        return None, signal_error

    window_ticks, window_error = parse_time_value(window_text, int(header["timescale_fs"]))
    if window_error is not None:
        return None, window_error
    if window_ticks is None or window_ticks <= 0:
        return None, make_error_payload(
            status="input_error",
            category="invalid_window_length",
            message="Window length must be a positive time value",
            details={"window_text": window_text},
        )

    anchor_ticks = 0
    if anchor_text is not None:
        parsed_anchor, anchor_error = parse_time_value(anchor_text, int(header["timescale_fs"]))
        if anchor_error is not None:
            return None, anchor_error
        anchor_ticks = int(parsed_anchor)

    selected_dicts = [asdict(item) for item in selected_signals]
    selected_codes = {item["code"] for item in selected_dicts}
    events_by_code = parse_selected_events(wave_file, selected_codes, header["code_to_decl"])

    session = {
        "wave_file": str(wave_file),
        "timescale_text": header["timescale_text"],
        "timescale_fs": int(header["timescale_fs"]),
        "selected_signals": selected_dicts,
        "events_by_code": events_by_code,
        "anchor_ticks": anchor_ticks,
        "window_ticks": int(window_ticks),
    }
    return session, None


def make_render_payload(session: dict, message: str) -> dict:
    rendered = render_window(session)
    rows = rendered["rows"]
    return {
        "status": "ok",
        "message": message,
        "wave_file": session["wave_file"],
        "timescale": session["timescale_text"],
        "selected_signals": [item["display_name"] for item in session["selected_signals"]],
        "render": rendered,
        "rendered_text": render_rows_as_text(rows),
    }


def find_next_event(session: dict, signal_name: str, edge: str) -> tuple[int | None, dict | None]:
    target = None
    for selected in session["selected_signals"]:
        if selected["display_name"] == signal_name:
            target = selected
            break
    if target is None:
        return None, make_error_payload(
            status="input_error",
            category="signal_not_selected",
            message="Navigation signal must be part of the current observation set",
            details={"signal": signal_name},
        )

    if edge in {"rise", "fall"} and int(target["width"]) != 1:
        return None, make_error_payload(
            status="input_error",
            category="edge_requires_single_bit_signal",
            message="Rise/fall navigation is only available on single-bit or bit-selected signals",
            details={"signal": signal_name},
        )

    anchor_ticks = int(session["anchor_ticks"])
    default_value = unknown_value(int(target["base_width"]))
    current_raw = value_at_anchor(session["events_by_code"][target["code"]], anchor_ticks, default_value)
    current_value = observed_value(current_raw, target)

    for time_tick, raw_value in session["events_by_code"][target["code"]]:
        time_tick = int(time_tick)
        if time_tick <= anchor_ticks:
            continue
        next_value = observed_value(str(raw_value), target)
        transition = classify_transition(current_value, next_value, int(target["width"]))
        if edge == "change" and next_value != current_value:
            return time_tick, None
        if transition == edge:
            return time_tick, None
        current_value = next_value

    return None, make_error_payload(
        status="input_error",
        category="edge_not_found",
        message="No matching edge was found after the current anchor position",
        details={
            "signal": signal_name,
            "edge": edge,
            "anchor_time": format_time_ticks(anchor_ticks, int(session["timescale_fs"])),
        },
    )


def allocate_session_id() -> str:
    return f"wave-{secrets.token_hex(4)}"


def session_path(session_id: str) -> Path:
    return ensure_session_dir() / f"{session_id}.json"


def save_session(session_id: str, session: dict) -> Path:
    path = session_path(session_id)
    payload = dict(session)
    payload["session_id"] = session_id
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_session(session_id: str) -> tuple[dict | None, dict | None]:
    path = session_path(session_id)
    if not path.exists():
        return None, make_error_payload(
            status="input_error",
            category="session_not_found",
            message="Waveform observation session was not found",
            details={"session_id": session_id},
        )
    return json.loads(path.read_text(encoding="utf-8")), None


def delete_session(session_id: str) -> dict:
    path = session_path(session_id)
    if path.exists():
        path.unlink()
    return {
        "status": "ok",
        "message": "Waveform observation session closed",
        "session_id": session_id,
    }
