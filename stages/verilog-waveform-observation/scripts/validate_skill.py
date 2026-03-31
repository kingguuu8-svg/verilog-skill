#!/usr/bin/env python3
from __future__ import annotations

import json
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
VALIDATE_ROOT = REPO_ROOT / ".tmp" / "verilog-waveform-observation" / "validate"


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
    if not any("15000ps" in line and "rst_n: rise" in line and "en: rise" in line for line in rendered_lines):
        raise AssertionError("Expected reset and enable rise event at 15000ps was not rendered")

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

    print("validation_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
