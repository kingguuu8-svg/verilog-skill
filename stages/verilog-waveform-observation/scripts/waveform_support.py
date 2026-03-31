#!/usr/bin/env python3
from __future__ import annotations

import bisect
import difflib
import hashlib
import json
import re
import secrets
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE1_SCRIPTS = REPO_ROOT / "stages" / "verilog-language-and-syntax" / "scripts"
STAGE2_SCRIPTS = REPO_ROOT / "stages" / "verilog-simulation-execution" / "scripts"
for script_dir in (STAGE1_SCRIPTS, STAGE2_SCRIPTS):
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

from checker_support import decode_stream  # noqa: E402
from simulation_support import build_vivado_runtime_env, probe_xsim_backend  # noqa: E402


TMP_ROOT = REPO_ROOT / ".tmp" / "verilog-waveform-observation"
SESSION_ROOT = TMP_ROOT / "sessions"
EXPORT_ROOT = TMP_ROOT / "exports"
SUPPORTED_WAVE_SUFFIXES = {".vcd", ".wdb"}
VCD_INDEX_FORMAT = "verilog-skill-vcd-index-v1"
DEFAULT_VCD_INDEX_STRIDE_BYTES = 256 * 1024 * 1024
VCD_INDEX_AUTO_MIN_BYTES = 64 * 1024 * 1024
TIME_UNIT_TO_FS = {
    "fs": 1,
    "ps": 1_000,
    "ns": 1_000_000,
    "us": 1_000_000_000,
    "ms": 1_000_000_000_000,
    "s": 1_000_000_000_000_000,
}
BIT_SELECT_RE = re.compile(r"^(?P<base>.+)\[(?P<index>-?\d+)\]$")
TIME_RE = re.compile(r"^(?P<value>\d+)(?P<unit>fs|ps|ns|us|ms|s)?$")
TIMESCALE_RE = re.compile(r"^(?P<value>\d+)\s*(?P<unit>fs|ps|ns|us|ms|s)$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
RANGE_SUFFIX_RE = re.compile(r"\[(?P<msb>-?\d+)(?::(?P<lsb>-?\d+))?\]$")


@dataclass
class ResolvedWaveSource:
    requested_wave_file: str
    requested_format: str
    resolved_wave_file: str
    resolved_format: str
    resolution: str
    conversion_log: str | None = None


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


def ensure_export_dir() -> Path:
    ensure_temp_dir()
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    return EXPORT_ROOT


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


def safe_name(text: str) -> str:
    sanitized = SAFE_NAME_RE.sub("-", text.strip())
    sanitized = sanitized.strip(".-_")
    return sanitized or "wave"


def build_wave_source_payload(source: ResolvedWaveSource) -> dict:
    payload = asdict(source)
    if payload["conversion_log"] is None:
        payload.pop("conversion_log")
    return payload


def normalize_signal_tokens(raw_tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    for token in raw_tokens:
        for part in token.split(","):
            stripped = part.strip()
            if stripped:
                normalized.append(stripped)
    return normalized


def resolve_input_wave_path(path_text: str) -> tuple[Path | None, dict | None]:
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
            message="Stage-3 waveform observation supports VCD files and XSIM WDB artifacts only",
            details={
                "wave_file": str(candidate),
                "supported_suffixes": sorted(SUPPORTED_WAVE_SUFFIXES),
            },
        )
    return candidate, None


def resolve_companion_vcd(wave_file: Path) -> Path | None:
    companion = wave_file.with_suffix(".vcd")
    if not companion.exists():
        return None
    try:
        wave_stat = wave_file.stat()
        companion_stat = companion.stat()
    except OSError:
        return None
    if companion_stat.st_size <= 0:
        return None
    if companion_stat.st_mtime_ns < wave_stat.st_mtime_ns:
        return None
    return companion.resolve()

def load_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_wave_fingerprint(wave_file: Path) -> dict[str, int | str]:
    stat = wave_file.stat()
    return {
        "wave_file": str(wave_file.resolve()),
        "wave_size": stat.st_size,
        "wave_mtime_ns": stat.st_mtime_ns,
    }


def cached_export_is_valid(
    metadata_path: Path,
    wave_file: Path,
    snapshot_name: str,
    exported_vcd: Path,
) -> bool:
    try:
        exported_stat = exported_vcd.stat()
        fingerprint = build_wave_fingerprint(wave_file)
    except OSError:
        return False
    if exported_stat.st_size <= 0:
        return False

    metadata = load_json_file(metadata_path)
    if metadata is None:
        return False
    if not metadata.get("success"):
        return False
    if metadata.get("returncode") != 0:
        return False
    if metadata.get("snapshot_name") != snapshot_name:
        return False
    if metadata.get("wave_file") != fingerprint["wave_file"]:
        return False
    if metadata.get("wave_size") != fingerprint["wave_size"]:
        return False
    if metadata.get("wave_mtime_ns") != fingerprint["wave_mtime_ns"]:
        return False
    return metadata.get("exported_vcd") == str(exported_vcd.resolve())


def wave_cache_dir(wave_file: Path) -> Path:
    stat = wave_file.stat()
    digest = hashlib.sha1(
        f"{wave_file.resolve()}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
    ).hexdigest()[:12]
    cache_dir = ensure_export_dir() / f"{safe_name(wave_file.stem)}-{digest}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def vcd_index_path(wave_file: Path) -> Path:
    return wave_file.with_name(f"{wave_file.name}idx")


def parse_value_change_bytes(line: bytes) -> tuple[bytes, bytes] | None:
    if not line:
        return None
    head = line[:1]
    if head in {b"0", b"1", b"x", b"X", b"z", b"Z"}:
        return line[1:].strip(), head.lower()
    if head in {b"b", b"B"}:
        parts = line[1:].split()
        if len(parts) != 2:
            return None
        return parts[1], parts[0].lower()
    return None


def normalize_vector_value_bytes(raw_value: bytes, width: int) -> str:
    lowered = raw_value.lower().decode("ascii", errors="ignore")
    if width <= 1:
        return lowered[0]
    if len(lowered) >= width:
        return lowered[-width:]
    pad_char = lowered[0] if lowered and lowered[0] in {"x", "z"} else "0"
    return (pad_char * (width - len(lowered))) + lowered


def load_vcd_index(wave_file: Path) -> dict | None:
    if wave_file.suffix.lower() != ".vcd":
        return None
    index_path = vcd_index_path(wave_file)
    payload = load_json_file(index_path)
    if payload is None:
        return None
    fingerprint = build_wave_fingerprint(wave_file)
    if payload.get("format") != VCD_INDEX_FORMAT:
        return None
    if payload.get("wave_file") != fingerprint["wave_file"]:
        return None
    if payload.get("wave_size") != fingerprint["wave_size"]:
        return None
    if payload.get("wave_mtime_ns") != fingerprint["wave_mtime_ns"]:
        return None
    codes = payload.get("codes")
    widths = payload.get("widths")
    checkpoints = payload.get("checkpoints")
    if not isinstance(codes, list) or not isinstance(widths, list) or len(codes) != len(widths):
        return None
    if not isinstance(checkpoints, list) or not checkpoints:
        return None
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict):
            return None
        values = checkpoint.get("values")
        if not isinstance(values, list) or len(values) != len(codes):
            return None
    payload["index_file"] = str(index_path.resolve())
    return payload


def build_vcd_index(
    wave_file: Path,
    *,
    force: bool = False,
    checkpoint_stride_bytes: int = DEFAULT_VCD_INDEX_STRIDE_BYTES,
) -> tuple[Path | None, dict | None]:
    wave_file = wave_file.resolve()
    if wave_file.suffix.lower() != ".vcd":
        return None, make_error_payload(
            status="unsupported_feature",
            category="unsupported_wave_format",
            message="Wave index generation currently supports VCD files only",
            details={"wave_file": str(wave_file)},
        )

    existing = load_vcd_index(wave_file)
    index_path = vcd_index_path(wave_file)
    if existing is not None and not force:
        return index_path, None

    header, header_error = load_vcd_header(wave_file)
    if header_error is not None:
        return None, header_error

    declarations = header["declarations"]
    codes = [str(decl["code"]) for decl in declarations]
    widths = [int(decl["width"]) for decl in declarations]
    code_positions = {code: index for index, code in enumerate(codes)}
    current_values = [unknown_value(width) for width in widths]
    checkpoints: list[dict] = []
    current_time = 0
    header_done = False
    header_end_offset: int | None = None
    next_checkpoint_offset = max(checkpoint_stride_bytes, 1)

    try:
        with wave_file.open("rb") as handle:
            while True:
                raw_line = handle.readline()
                if not raw_line:
                    break
                line = raw_line.strip()
                current_offset = handle.tell()
                if not line:
                    continue
                if not header_done:
                    if line.startswith(b"$enddefinitions"):
                        header_done = True
                        header_end_offset = current_offset
                        checkpoints.append(
                            {
                                "time_tick": current_time,
                                "file_offset": header_end_offset,
                                "values": list(current_values),
                            }
                        )
                        while next_checkpoint_offset <= header_end_offset:
                            next_checkpoint_offset += checkpoint_stride_bytes
                    continue

                if line.startswith(b"#"):
                    current_time = int(line[1:])
                elif not line.startswith(b"$"):
                    parsed = parse_value_change_bytes(line)
                    if parsed is not None:
                        code_bytes, raw_value = parsed
                        code = code_bytes.decode("ascii", errors="ignore")
                        position = code_positions.get(code)
                        if position is not None:
                            current_values[position] = normalize_vector_value_bytes(raw_value, widths[position])

                if current_offset >= next_checkpoint_offset:
                    checkpoints.append(
                        {
                            "time_tick": current_time,
                            "file_offset": current_offset,
                            "values": list(current_values),
                        }
                    )
                    while next_checkpoint_offset <= current_offset:
                        next_checkpoint_offset += checkpoint_stride_bytes
    except OSError as exc:
        return None, make_error_payload(
            status="input_error",
            category="wave_file_read_failed",
            message="Waveform file could not be indexed",
            details={"wave_file": str(wave_file), "reason": str(exc)},
        )

    if header_end_offset is None:
        return None, make_error_payload(
            status="input_error",
            category="invalid_wave_file",
            message="VCD header ended unexpectedly before $enddefinitions",
            details={"wave_file": str(wave_file)},
        )

    final_offset = wave_file.stat().st_size
    if checkpoints[-1]["file_offset"] != final_offset:
        checkpoints.append(
            {
                "time_tick": current_time,
                "file_offset": final_offset,
                "values": list(current_values),
            }
        )

    fingerprint = build_wave_fingerprint(wave_file)
    payload = {
        "format": VCD_INDEX_FORMAT,
        **fingerprint,
        "timescale_text": header["timescale_text"],
        "timescale_fs": int(header["timescale_fs"]),
        "header_end_offset": header_end_offset,
        "checkpoint_stride_bytes": checkpoint_stride_bytes,
        "codes": codes,
        "widths": widths,
        "checkpoints": checkpoints,
    }

    temp_path = index_path.with_name(f"{index_path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        temp_path.replace(index_path)
    except OSError as exc:
        try:
            if temp_path.exists():
                temp_path.unlink()
        except OSError:
            pass
        return None, make_error_payload(
            status="run_error",
            category="wave_index_write_failed",
            message="Waveform index could not be written",
            details={"wave_file": str(wave_file), "index_file": str(index_path), "reason": str(exc)},
        )

    return index_path.resolve(), None


def maybe_build_vcd_index(
    wave_file: Path,
    *,
    mode: str,
    checkpoint_stride_bytes: int = DEFAULT_VCD_INDEX_STRIDE_BYTES,
) -> tuple[Path | None, dict | None]:
    if wave_file.suffix.lower() != ".vcd":
        return None, None
    if mode == "never":
        return None, None
    if mode == "auto":
        try:
            if wave_file.stat().st_size < VCD_INDEX_AUTO_MIN_BYTES:
                return None, None
        except OSError as exc:
            return None, make_error_payload(
                status="input_error",
                category="wave_file_read_failed",
                message="Waveform file could not be inspected for index generation",
                details={"wave_file": str(wave_file), "reason": str(exc)},
            )
    return build_vcd_index(wave_file, force=False, checkpoint_stride_bytes=checkpoint_stride_bytes)


def resolve_index_checkpoint(index_payload: dict, anchor_ticks: int) -> dict:
    checkpoints = index_payload["checkpoints"]
    times = [int(checkpoint["time_tick"]) for checkpoint in checkpoints]
    checkpoint_index = bisect.bisect_right(times, anchor_ticks) - 1
    if checkpoint_index < 0:
        checkpoint_index = 0
    return checkpoints[checkpoint_index]


def iter_snapshot_dirs(output_dir: Path) -> list[Path]:
    xsim_dir = output_dir / "xsim.dir"
    if not xsim_dir.exists():
        return []

    snapshot_dirs: list[Path] = []
    for candidate in sorted(xsim_dir.iterdir()):
        if not candidate.is_dir():
            continue
        has_image = (candidate / "xsimk.exe").exists() or (candidate / "xsimk").exists()
        if not has_image:
            continue
        snapshot_dirs.append(candidate.resolve())
    return snapshot_dirs


def snapshot_script_matches_wdb(snapshot_dir: Path, wave_file: Path) -> bool:
    script_path = snapshot_dir / "xsim_script.tcl"
    if not script_path.exists():
        return False
    try:
        script_text = script_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False

    normalized_wdb = wave_file.resolve().as_posix()
    return normalized_wdb in script_text or wave_file.name in script_text


def resolve_snapshot_name_for_wdb(wave_file: Path) -> tuple[str | None, dict | None]:
    snapshot_dirs = iter_snapshot_dirs(wave_file.parent)
    if not snapshot_dirs:
        return None, make_error_payload(
            status="input_error",
            category="missing_simulation_context",
            message="WDB observation requires an adjacent xsim.dir snapshot directory or a companion VCD",
            details={"wave_file": str(wave_file)},
        )

    matched = [directory.name for directory in snapshot_dirs if snapshot_script_matches_wdb(directory, wave_file)]
    if len(matched) == 1:
        return matched[0], None
    if len(matched) > 1:
        return None, make_error_payload(
            status="input_error",
            category="ambiguous_snapshot_context",
            message="More than one XSIM snapshot matched the requested WDB artifact",
            details={
                "wave_file": str(wave_file),
                "snapshot_candidates": matched,
            },
        )

    preferred = f"{wave_file.stem}_behav"
    snapshot_names = [directory.name for directory in snapshot_dirs]
    if preferred in snapshot_names:
        return preferred, None
    if len(snapshot_names) == 1:
        return snapshot_names[0], None

    return None, make_error_payload(
        status="input_error",
        category="missing_simulation_context",
        message="Could not determine which XSIM snapshot should be replayed for the requested WDB artifact",
        details={
            "wave_file": str(wave_file),
            "snapshot_candidates": snapshot_names,
        },
    )


def build_wdb_export_tcl(exported_vcd: Path) -> str:
    return "\n".join(
        [
            "if {[catch {close_vcd} close_error]} {",
            '    puts "stage3_notice: close_vcd skipped"',
            "}",
            f"open_vcd {{{exported_vcd.as_posix()}}}",
            "log_vcd -level 0 /",
            "run all",
            "close_vcd",
            "quit",
            "",
        ]
    )


def export_wdb_to_vcd(wave_file: Path) -> tuple[ResolvedWaveSource | None, dict | None]:
    xsim_info = probe_xsim_backend()
    if xsim_info["status"] != "ok":
        return None, make_error_payload(
            status="environment_error",
            category="xsim_backend_unavailable",
            message="WDB observation requires a runnable Vivado XSIM toolchain",
            details={
                "wave_file": str(wave_file),
                "backend_probe": xsim_info,
            },
        )

    snapshot_name, snapshot_error = resolve_snapshot_name_for_wdb(wave_file)
    if snapshot_error is not None:
        return None, snapshot_error

    cache_dir = wave_cache_dir(wave_file)
    exported_vcd = cache_dir / f"{wave_file.stem}.vcd"
    export_log = cache_dir / "xsim-export.log"
    export_tcl = cache_dir / "export_from_wdb.tcl"
    metadata_path = cache_dir / "metadata.json"
    if cached_export_is_valid(metadata_path, wave_file, snapshot_name, exported_vcd):
        return ResolvedWaveSource(
            requested_wave_file=str(wave_file),
            requested_format=wave_file.suffix.lower(),
            resolved_wave_file=str(exported_vcd.resolve()),
            resolved_format=".vcd",
            resolution="xsim_snapshot_replay",
            conversion_log=str(export_log.resolve()) if export_log.exists() else None,
        ), None

    export_tcl.write_text(build_wdb_export_tcl(exported_vcd), encoding="ascii")
    command = [
        xsim_info["backend_path"],
        snapshot_name,
        "--tclbatch",
        export_tcl.as_posix(),
        "--log",
        str(export_log),
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=False,
        env=build_vivado_runtime_env(),
        cwd=str(wave_file.parent.resolve()),
        check=False,
    )
    stdout = decode_stream(proc.stdout)
    stderr = decode_stream(proc.stderr)
    success = proc.returncode == 0 and exported_vcd.exists() and exported_vcd.stat().st_size > 0
    if not success and exported_vcd.exists():
        try:
            exported_vcd.unlink()
        except OSError:
            pass
    fingerprint = build_wave_fingerprint(wave_file)
    metadata_path.write_text(
        json.dumps(
            {
                **fingerprint,
                "snapshot_name": snapshot_name,
                "exported_vcd": str(exported_vcd.resolve()),
                "command": command,
                "returncode": proc.returncode,
                "success": success,
                "stdout": stdout,
                "stderr": stderr,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if not success:
        return None, make_error_payload(
            status="run_error",
            category="wdb_export_failed",
            message="XSIM snapshot replay did not produce a temporary VCD for the requested WDB artifact",
            details={
                "wave_file": str(wave_file),
                "snapshot_name": snapshot_name,
                "exported_vcd": str(exported_vcd),
                "conversion_log": str(export_log),
                "metadata_file": str(metadata_path),
                "returncode": proc.returncode,
            },
        )

    return ResolvedWaveSource(
        requested_wave_file=str(wave_file),
        requested_format=wave_file.suffix.lower(),
        resolved_wave_file=str(exported_vcd.resolve()),
        resolved_format=".vcd",
        resolution="xsim_snapshot_replay",
        conversion_log=str(export_log.resolve()),
    ), None


def resolve_wave_source(path_text: str) -> tuple[ResolvedWaveSource | None, dict | None]:
    wave_file, wave_error = resolve_input_wave_path(path_text)
    if wave_error is not None:
        return None, wave_error

    if wave_file.suffix.lower() == ".vcd":
        return ResolvedWaveSource(
            requested_wave_file=str(wave_file),
            requested_format=".vcd",
            resolved_wave_file=str(wave_file),
            resolved_format=".vcd",
            resolution="direct",
        ), None

    companion_vcd = resolve_companion_vcd(wave_file)
    if companion_vcd is not None:
        return ResolvedWaveSource(
            requested_wave_file=str(wave_file),
            requested_format=".wdb",
            resolved_wave_file=str(companion_vcd),
            resolved_format=".vcd",
            resolution="companion_vcd",
        ), None

    return export_wdb_to_vcd(wave_file)


def parse_timescale_text(text: str) -> tuple[str, int]:
    normalized = " ".join(text.split()).lower()
    match = TIMESCALE_RE.match(normalized)
    if not match:
        raise ValueError(f"Unsupported VCD timescale: {text}")
    value = int(match.group("value"))
    unit = match.group("unit")
    return f"{value}{unit}", value * TIME_UNIT_TO_FS[unit]


def parse_reference_text(ref_text: str) -> tuple[str, int | None, int | None]:
    candidate = ref_text.strip()
    if not candidate:
        raise ValueError(f"Unsupported VCD reference syntax: {ref_text}")

    match = RANGE_SUFFIX_RE.search(candidate)
    if match is None:
        return candidate, None, None

    name = candidate[: match.start()].rstrip()
    if not name:
        raise ValueError(f"Unsupported VCD reference syntax: {ref_text}")

    msb = int(match.group("msb"))
    lsb_text = match.group("lsb")
    if lsb_text is None:
        value = msb
        return name, value, value
    return name, msb, int(lsb_text)


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


def load_vcd_header(wave_file: Path) -> tuple[dict | None, dict | None]:
    try:
        return parse_vcd_header(wave_file), None
    except ValueError as exc:
        return None, make_error_payload(
            status="unsupported_feature",
            category="unsupported_vcd_header",
            message="Waveform header contains unsupported VCD syntax",
            details={
                "wave_file": str(wave_file),
                "reason": str(exc),
            },
        )
    except OSError as exc:
        return None, make_error_payload(
            status="input_error",
            category="wave_file_read_failed",
            message="Waveform file could not be read",
            details={
                "wave_file": str(wave_file),
                "reason": str(exc),
            },
        )


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


def parse_selected_events(
    wave_file: Path,
    selected_codes: set[str],
    code_to_decl: dict[str, dict],
    *,
    start_offset: int = 0,
    initial_time: int = 0,
    initial_values: dict[str, str] | None = None,
    skip_header: bool = False,
    stop_after_ticks: int | None = None,
) -> dict[str, list[list[int | str]]]:
    events_by_code: dict[str, list[list[int | str]]] = {code: [] for code in selected_codes}
    last_values: dict[str, str] = {}
    header_done = skip_header
    current_time = initial_time

    if initial_values is not None:
        for code, value in initial_values.items():
            if code not in selected_codes:
                continue
            normalized = normalize_vector_value(value, int(code_to_decl[code]["width"]))
            last_values[code] = normalized
            events_by_code[code].append([current_time, normalized])

    with wave_file.open("r", encoding="utf-8", errors="replace") as handle:
        if start_offset:
            handle.seek(start_offset)
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
                if stop_after_ticks is not None and current_time > stop_after_ticks:
                    break
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


def load_events_for_session(
    session: dict,
    *,
    stop_after_window: bool,
    selected_codes: set[str] | None = None,
) -> tuple[dict[str, list[list[int | str]]] | None, dict | None, dict]:
    if selected_codes is None:
        selected_codes = {item["code"] for item in session["selected_signals"]}

    resolved_wave_file = Path(session.get("resolved_wave_file", session["wave_file"]))
    stop_after_ticks = None
    if stop_after_window:
        stop_after_ticks = int(session["anchor_ticks"]) + int(session["window_ticks"])
    code_to_decl = {
        item["code"]: {"width": int(item["base_width"])}
        for item in session["selected_signals"]
        if item["code"] in selected_codes
    }

    start_offset = 0
    initial_time = 0
    initial_values: dict[str, str] | None = None
    skip_header = False
    wave_index_info = {
        "status": "absent",
        "index_file": None,
        "checkpoint_time": None,
        "checkpoint_offset": None,
    }

    index_payload = load_vcd_index(resolved_wave_file)
    if index_payload is not None:
        checkpoint = resolve_index_checkpoint(index_payload, int(session["anchor_ticks"]))
        code_positions = {code: index for index, code in enumerate(index_payload["codes"])}
        initial_values = {
            code: str(checkpoint["values"][code_positions[code]])
            for code in selected_codes
            if code in code_positions
        }
        start_offset = int(checkpoint["file_offset"])
        initial_time = int(checkpoint["time_tick"])
        skip_header = True
        wave_index_info = {
            "status": "used",
            "index_file": index_payload["index_file"],
            "checkpoint_time": initial_time,
            "checkpoint_offset": start_offset,
        }

    try:
        events_by_code = parse_selected_events(
            resolved_wave_file,
            selected_codes,
            code_to_decl,
            start_offset=start_offset,
            initial_time=initial_time,
            initial_values=initial_values,
            skip_header=skip_header,
            stop_after_ticks=stop_after_ticks,
        )
    except OSError as exc:
        return None, make_error_payload(
            status="input_error",
            category="wave_file_read_failed",
            message="Waveform events could not be read",
            details={
                "wave_file": str(resolved_wave_file),
                "reason": str(exc),
            },
        ), wave_index_info
    return events_by_code, None, wave_index_info


def list_signals(wave_file_text: str) -> dict:
    wave_source, wave_error = resolve_wave_source(wave_file_text)
    if wave_error is not None:
        return wave_error

    resolved_wave_file = Path(wave_source.resolved_wave_file)
    header, header_error = load_vcd_header(resolved_wave_file)
    if header_error is not None:
        return header_error
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
        "wave_file": wave_source.requested_wave_file,
        "resolved_wave_file": wave_source.resolved_wave_file,
        "wave_source": build_wave_source_payload(wave_source),
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


def anchor_state_for_events(
    events: list[list[int | str]],
    anchor_ticks: int,
    default_value: str,
) -> tuple[str, int]:
    current = default_value
    next_index = len(events)
    for index, (time_tick, value) in enumerate(events):
        if int(time_tick) > anchor_ticks:
            next_index = index
            break
        current = str(value)
    return current, next_index


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

    selected_codes: list[str] = []
    current_raw_by_code: dict[str, str] = {}
    next_index_by_code: dict[str, int] = {}
    for selected in selected_signals:
        code = selected["code"]
        if code in current_raw_by_code:
            continue
        default_value = unknown_value(int(selected["base_width"]))
        current_raw, next_index = anchor_state_for_events(events_by_code[code], anchor_ticks, default_value)
        current_raw_by_code[code] = current_raw
        next_index_by_code[code] = next_index
        selected_codes.append(code)

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

    while True:
        next_time: int | None = None
        for code in selected_codes:
            events = events_by_code[code]
            next_index = next_index_by_code[code]
            if next_index >= len(events):
                continue
            candidate_time = int(events[next_index][0])
            if candidate_time > end_ticks:
                continue
            if next_time is None or candidate_time < next_time:
                next_time = candidate_time
        if next_time is None:
            break

        for code in selected_codes:
            events = events_by_code[code]
            next_index = next_index_by_code[code]
            while next_index < len(events) and int(events[next_index][0]) == next_time:
                current_raw_by_code[code] = str(events[next_index][1])
                next_index += 1
            next_index_by_code[code] = next_index

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
                    "time_ticks": next_time,
                    "time_text": format_time_ticks(next_time, timescale_fs),
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
    *,
    include_events: bool = True,
    stop_after_window: bool = False,
) -> tuple[dict | None, dict | None]:
    wave_source, wave_error = resolve_wave_source(wave_file_text)
    if wave_error is not None:
        return None, wave_error

    resolved_wave_file = Path(wave_source.resolved_wave_file)
    header, header_error = load_vcd_header(resolved_wave_file)
    if header_error is not None:
        return None, header_error
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
    session = {
        "wave_file": wave_source.requested_wave_file,
        "resolved_wave_file": wave_source.resolved_wave_file,
        "wave_source": build_wave_source_payload(wave_source),
        "timescale_text": header["timescale_text"],
        "timescale_fs": int(header["timescale_fs"]),
        "selected_signals": selected_dicts,
        "anchor_ticks": anchor_ticks,
        "window_ticks": int(window_ticks),
        "session_storage": "metadata_only",
    }
    if not include_events:
        return session, None

    events_by_code, event_error, wave_index_info = load_events_for_session(
        session,
        stop_after_window=stop_after_window,
        selected_codes={item["code"] for item in selected_dicts},
    )
    if event_error is not None:
        return None, event_error
    session["events_by_code"] = events_by_code
    session["session_storage"] = "embedded_events"
    session["wave_index"] = wave_index_info
    return session, None


def hydrate_session_events(
    session: dict,
    *,
    stop_after_window: bool,
    selected_codes: set[str] | None = None,
) -> tuple[dict | None, dict | None]:
    if "events_by_code" in session and selected_codes is None:
        return session, None

    events_by_code, event_error, wave_index_info = load_events_for_session(
        session,
        stop_after_window=stop_after_window,
        selected_codes=selected_codes,
    )
    if event_error is not None:
        return None, event_error

    hydrated = dict(session)
    hydrated["events_by_code"] = events_by_code
    hydrated["wave_index"] = wave_index_info
    return hydrated, None


def make_render_payload(session: dict, message: str) -> tuple[dict | None, dict | None]:
    render_session, render_error = hydrate_session_events(session, stop_after_window=True)
    if render_error is not None:
        return None, render_error
    rendered = render_window(render_session)
    rows = rendered["rows"]
    return {
        "status": "ok",
        "message": message,
        "wave_file": render_session["wave_file"],
        "resolved_wave_file": render_session.get("resolved_wave_file", render_session["wave_file"]),
        "wave_source": render_session.get(
            "wave_source",
            {
                "requested_wave_file": render_session["wave_file"],
                "requested_format": Path(render_session["wave_file"]).suffix.lower(),
                "resolved_wave_file": render_session.get("resolved_wave_file", render_session["wave_file"]),
                "resolved_format": Path(render_session.get("resolved_wave_file", render_session["wave_file"])).suffix.lower(),
                "resolution": "direct",
            },
        ),
        "timescale": render_session["timescale_text"],
        "selected_signals": [item["display_name"] for item in render_session["selected_signals"]],
        "wave_index": render_session.get(
            "wave_index",
            {
                "status": "absent",
                "index_file": None,
                "checkpoint_time": None,
                "checkpoint_offset": None,
            },
        ),
        "render": rendered,
        "rendered_text": render_rows_as_text(rows),
    }, None


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
    if "events_by_code" in session:
        default_value = unknown_value(int(target["base_width"]))
        current_raw, start_index = anchor_state_for_events(
            session["events_by_code"][target["code"]],
            anchor_ticks,
            default_value,
        )
        current_value = observed_value(current_raw, target)

        for time_tick, raw_value in session["events_by_code"][target["code"]][start_index:]:
            time_tick = int(time_tick)
            next_value = observed_value(str(raw_value), target)
            transition = classify_transition(current_value, next_value, int(target["width"]))
            if edge == "change" and next_value != current_value:
                return time_tick, None
            if transition == edge:
                return time_tick, None
            current_value = next_value
    else:
        resolved_wave_file = Path(session.get("resolved_wave_file", session["wave_file"]))
        default_value = unknown_value(int(target["base_width"]))
        current_raw = default_value
        header_done = False
        current_time = 0
        start_offset = 0
        index_payload = load_vcd_index(resolved_wave_file)
        if index_payload is not None:
            checkpoint = resolve_index_checkpoint(index_payload, anchor_ticks)
            code_positions = {code: index for index, code in enumerate(index_payload["codes"])}
            code_position = code_positions.get(target["code"])
            if code_position is not None:
                current_raw = str(checkpoint["values"][code_position])
                current_time = int(checkpoint["time_tick"])
                start_offset = int(checkpoint["file_offset"])
                header_done = True

        try:
            with resolved_wave_file.open("r", encoding="utf-8", errors="replace") as handle:
                if start_offset:
                    handle.seek(start_offset)
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
                    if code != target["code"]:
                        continue
                    normalized = normalize_vector_value(raw_value, int(target["base_width"]))
                    if normalized == current_raw:
                        continue
                    if current_time <= anchor_ticks:
                        current_raw = normalized
                        continue
                    current_value = observed_value(current_raw, target)
                    next_value = observed_value(normalized, target)
                    transition = classify_transition(current_value, next_value, int(target["width"]))
                    if edge == "change" and next_value != current_value:
                        return current_time, None
                    if transition == edge:
                        return current_time, None
                    current_raw = normalized
        except OSError as exc:
            return None, make_error_payload(
                status="input_error",
                category="wave_file_read_failed",
                message="Waveform events could not be read",
                details={
                    "wave_file": str(resolved_wave_file),
                    "reason": str(exc),
                },
            )

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
    payload.pop("events_by_code", None)
    payload["session_storage"] = "metadata_only"
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
