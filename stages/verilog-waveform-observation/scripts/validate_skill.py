#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
STAGE3_DIR = SCRIPT_DIR.parent
REPO_ROOT = STAGE3_DIR.parents[1]
STAGE2_RUN = REPO_ROOT / "stages" / "verilog-simulation-execution" / "scripts" / "run_simulation.py"
OBSERVE_SCRIPT = SCRIPT_DIR / "observe_waveform.py"
SESSION_SCRIPT = SCRIPT_DIR / "wave_session.py"
SHELL_SCRIPT = SCRIPT_DIR / "wave_shell.py"
FIXTURE_DIR = STAGE3_DIR / "fixtures"
VALIDATE_ROOT = REPO_ROOT / ".tmp" / "verilog-waveform-observation" / "validate"
STAGE2_SCRIPTS = REPO_ROOT / "stages" / "verilog-simulation-execution" / "scripts"
if str(STAGE2_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(STAGE2_SCRIPTS))

from simulation_support import probe_xsim_backend  # noqa: E402
from waveform_support import cached_export_is_valid, resolve_companion_vcd  # noqa: E402


def run_command(command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


def run_json(command: list[str], *, input_text: str | None = None, expected_returncode: int = 0) -> dict:
    proc = run_command(command, input_text=input_text)
    if proc.returncode != expected_returncode:
        raise AssertionError(
            f"Command failed: {' '.join(command)}\n"
            f"returncode={proc.returncode}\n"
            f"stdout={proc.stdout}\n"
            f"stderr={proc.stderr}"
        )
    if not proc.stdout.strip():
        raise AssertionError(f"Command produced no JSON output: {' '.join(command)}")
    return json.loads(proc.stdout)


def main() -> int:
    if VALIDATE_ROOT.exists():
        shutil.rmtree(VALIDATE_ROOT)
    VALIDATE_ROOT.mkdir(parents=True, exist_ok=True)

    sim_output = VALIDATE_ROOT / "simulation-source"
    sim_payload = run_json(
        [
            sys.executable,
            str(STAGE2_RUN),
            "stages/verilog-simulation-execution/fixtures/pass_counter.f",
            "--output-dir",
            str(sim_output),
        ]
    )
    if sim_payload["status"] != "ok":
        raise AssertionError("Stage-2 sample simulation did not succeed")
    wave_files = sim_payload["artifacts"]["wave_files"]
    if not wave_files:
        raise AssertionError("Stage-2 sample simulation did not emit a wave file")
    wave_file = wave_files[0]

    escaped_fixture = FIXTURE_DIR / "escaped_identifier.vcd"
    escaped_catalog = run_json([sys.executable, str(OBSERVE_SCRIPT), "list-signals", str(escaped_fixture)])
    escaped_name = r"tb.\gen_row[0].gen_col[0].roi_pix"
    escaped_names = {item["canonical_name"] for item in escaped_catalog["signals"]}
    if escaped_name not in escaped_names:
        raise AssertionError("Escaped-identifier fixture is missing the expected canonical signal name")

    escaped_render = run_json(
        [
            sys.executable,
            str(OBSERVE_SCRIPT),
            "render-window",
            str(escaped_fixture),
            "--signals",
            "tb.clk",
            escaped_name,
            "--window",
            "20ps",
            "--anchor",
            "0ps",
        ]
    )
    if not any("10ps" in line and "tb.clk: rise" in line for line in escaped_render["rendered_text"]):
        raise AssertionError("Escaped-identifier fixture did not render the clk rise event")
    if not any("10ps" in line and r"tb.\gen_row[0].gen_col[0].roi_pix: value_change 00000000->00000001" in line for line in escaped_render["rendered_text"]):
        raise AssertionError("Escaped-identifier fixture did not render the vector value change")

    freshness_root = VALIDATE_ROOT / "freshness-check"
    freshness_root.mkdir(parents=True, exist_ok=True)
    wdb_path = freshness_root / "sample.wdb"
    vcd_path = freshness_root / "sample.vcd"
    wdb_path.write_text("wdb", encoding="ascii")
    vcd_path.write_text("$end", encoding="ascii")
    os.utime(wdb_path, ns=(20_000_000_000, 20_000_000_000))
    os.utime(vcd_path, ns=(10_000_000_000, 10_000_000_000))
    if resolve_companion_vcd(wdb_path) is not None:
        raise AssertionError("Stale companion VCD should not shadow a newer WDB file")
    os.utime(vcd_path, ns=(30_000_000_000, 30_000_000_000))
    if resolve_companion_vcd(wdb_path) != vcd_path.resolve():
        raise AssertionError("Fresh companion VCD should be accepted for WDB resolution")

    cache_root = VALIDATE_ROOT / "cache-check"
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_wave = cache_root / "cached.wdb"
    cache_export = cache_root / "cached.vcd"
    cache_metadata = cache_root / "metadata.json"
    cache_wave.write_text("wdb", encoding="ascii")
    cache_export.write_text("$end", encoding="ascii")
    cache_fingerprint = cache_wave.stat()
    cache_metadata.write_text(
        json.dumps(
            {
                "wave_file": str(cache_wave.resolve()),
                "wave_size": cache_fingerprint.st_size,
                "wave_mtime_ns": cache_fingerprint.st_mtime_ns,
                "snapshot_name": "tb_cached_behav",
                "exported_vcd": str(cache_export.resolve()),
                "returncode": 0,
                "success": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if cached_export_is_valid(cache_metadata, cache_wave, "tb_cached_behav", cache_export):
        raise AssertionError("Failed WDB export metadata must not validate a cached VCD")
    cache_metadata.write_text(
        json.dumps(
            {
                "wave_file": str(cache_wave.resolve()),
                "wave_size": cache_fingerprint.st_size,
                "wave_mtime_ns": cache_fingerprint.st_mtime_ns,
                "snapshot_name": "tb_cached_behav",
                "exported_vcd": str(cache_export.resolve()),
                "returncode": 0,
                "success": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if not cached_export_is_valid(cache_metadata, cache_wave, "tb_cached_behav", cache_export):
        raise AssertionError("Successful WDB export metadata should validate a matching cached VCD")

    catalog_payload = run_json([sys.executable, str(OBSERVE_SCRIPT), "list-signals", wave_file])
    canonical_names = {item["canonical_name"] for item in catalog_payload["signals"]}
    if "tb_counter_wave.count" not in canonical_names:
        raise AssertionError("Signal catalog is missing tb_counter_wave.count")

    render_payload = run_json(
        [
            sys.executable,
            str(OBSERVE_SCRIPT),
            "render-window",
            wave_file,
            "--signals",
            "clk",
            "rst_n",
            "en",
            "tb_counter_wave.count",
            "--window",
            "30000ps",
            "--anchor",
            "0ps",
        ]
    )
    rendered_lines = render_payload["rendered_text"]
    if not rendered_lines or not rendered_lines[0].startswith("0ps"):
        raise AssertionError("Anchor row was not rendered at the observation start")
    if not any("5000ps" in line and "clk: rise" in line and "tb_counter_wave.count: value_change xxxx->0000" in line for line in rendered_lines):
        raise AssertionError("Expected rise/value-change event at 5000ps was not rendered")
    if not any("20000ps" in line and "rst_n: rise" in line and "en: rise" in line for line in rendered_lines):
        raise AssertionError("Expected reset and enable rise event at 20000ps was not rendered")

    session_payload = run_json(
        [
            sys.executable,
            str(SESSION_SCRIPT),
            "open",
            wave_file,
            "--signals",
            "clk",
            "rst_n",
            "en",
            "tb_counter_wave.count",
            "--window",
            "30000ps",
            "--anchor",
            "0ps",
        ]
    )
    session_id = session_payload["session_id"]
    session_file = Path(session_payload["session_file"])
    if not session_file.exists():
        raise AssertionError("Session open did not materialize the session file")
    stored_session = json.loads(session_file.read_text(encoding="utf-8"))
    if "events_by_code" in stored_session:
        raise AssertionError("Session storage regressed to embedding waveform events")
    moved_payload = run_json(
        [
            sys.executable,
            str(SESSION_SCRIPT),
            "next-edge",
            session_id,
            "--signal",
            "clk",
            "--edge",
            "rise",
        ]
    )
    if moved_payload["render"]["anchor_time"] != "5000ps":
        raise AssertionError("Session navigation did not move to the next clk rise")

    updated_payload = run_json(
        [
            sys.executable,
            str(SESSION_SCRIPT),
            "set",
            session_id,
            "--signals",
            "tb_counter_wave.count[0]",
            "rst_n",
            "--window",
            "20000ps",
            "--anchor",
            "15000ps",
        ]
    )
    if updated_payload["selected_signals"] != ["tb_counter_wave.count[0]", "rst_n"]:
        raise AssertionError("Session update did not apply the rewritten signal set")

    bit_edge_payload = run_json(
        [
            sys.executable,
            str(SESSION_SCRIPT),
            "next-edge",
            session_id,
            "--signal",
            "tb_counter_wave.count[0]",
            "--edge",
            "rise",
        ]
    )
    if bit_edge_payload["render"]["anchor_time"] != "25000ps":
        raise AssertionError("Bit-select rise navigation did not move to the next expected event")

    close_payload = run_json([sys.executable, str(SESSION_SCRIPT), "close", session_id])
    if close_payload["status"] != "ok":
        raise AssertionError("Session close did not return success")

    shell_proc = run_command(
        [
            sys.executable,
            str(SHELL_SCRIPT),
            wave_file,
            "--signals",
            "clk",
            "tb_counter_wave.count",
            "--window",
            "20000ps",
            "--anchor",
            "0ps",
        ],
        input_text="clk rise\nquit\n",
    )
    if shell_proc.returncode != 0:
        raise AssertionError(f"Interactive shell smoke test failed:\n{shell_proc.stdout}\n{shell_proc.stderr}")
    if "5000ps" not in shell_proc.stdout:
        raise AssertionError("Interactive shell did not render the next-rise window")

    xsim_info = probe_xsim_backend()
    if xsim_info["status"] == "ok":
        xsim_output = VALIDATE_ROOT / "xsim-wdb-source"
        xsim_payload = run_json(
            [
                sys.executable,
                str(STAGE2_RUN),
                "stages/verilog-simulation-execution/fixtures/xpm_cdc_single.f",
                "--backend",
                "xsim",
                "--top",
                "tb_xpm_cdc_single",
                "--wave-file",
                "tb_xpm_cdc_single.wdb",
                "--output-dir",
                str(xsim_output),
            ]
        )
        if xsim_payload["status"] != "ok":
            raise AssertionError("Stage-2 XSIM fixture did not succeed during stage-3 WDB validation")
        wdb_wave_file = xsim_output / "tb_xpm_cdc_single.wdb"
        if not wdb_wave_file.exists():
            raise AssertionError("Stage-2 XSIM fixture did not emit the requested WDB artifact")

        wdb_catalog = run_json([sys.executable, str(OBSERVE_SCRIPT), "list-signals", str(wdb_wave_file)])
        if wdb_catalog["wave_source"]["resolution"] != "xsim_snapshot_replay":
            raise AssertionError("Stage-3 WDB catalog did not use the XSIM snapshot replay path")
        wdb_canonical_names = {item["canonical_name"] for item in wdb_catalog["signals"]}
        if "tb_xpm_cdc_single.dest_out" not in wdb_canonical_names:
            raise AssertionError("WDB signal catalog is missing tb_xpm_cdc_single.dest_out")

        wdb_render = run_json(
            [
                sys.executable,
                str(OBSERVE_SCRIPT),
                "render-window",
                str(wdb_wave_file),
                "--signals",
                "tb_xpm_cdc_single.src_in",
                "tb_xpm_cdc_single.dest_out",
                "--window",
                "120000ps",
                "--anchor",
                "0ps",
            ]
        )
        if not wdb_render["rendered_text"] or not wdb_render["rendered_text"][0].startswith("0ps"):
            raise AssertionError("WDB anchor row was not rendered")
        if not any("tb_xpm_cdc_single.src_in: rise" in line for line in wdb_render["rendered_text"]):
            raise AssertionError("WDB render did not capture the src_in rise")
        if not any("tb_xpm_cdc_single.dest_out: rise" in line for line in wdb_render["rendered_text"]):
            raise AssertionError("WDB render did not capture the dest_out rise")

    print("validation_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
