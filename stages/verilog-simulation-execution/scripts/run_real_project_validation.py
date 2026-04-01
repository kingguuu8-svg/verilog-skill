#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
STAGE1_SCRIPT = REPO_ROOT / "stages" / "verilog-language-and-syntax" / "scripts" / "check_syntax.py"
STAGE2_SCRIPT = REPO_ROOT / "stages" / "verilog-simulation-execution" / "scripts" / "run_simulation.py"
STAGE3_SCRIPT = REPO_ROOT / "stages" / "verilog-waveform-observation" / "scripts" / "observe_waveform.py"


@dataclass(frozen=True)
class Stage1Case:
    name: str
    inputs: tuple[str, ...]
    top: str
    expected_status: str


@dataclass(frozen=True)
class Stage2Case:
    name: str
    inputs: tuple[str, ...]
    backend: str
    top: str
    output_dir_name: str
    wave_file_name: str
    expected_status: str
    timeout_seconds: int = 600


@dataclass(frozen=True)
class Stage3Case:
    name: str
    wave_file: str
    signals: tuple[str, ...]
    window: str
    anchor: str
    expected_status: str = "ok"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run production-style validation of the 3-stage skill chain")
    parser.add_argument("--project-root", required=True, help="Path to the external PL_Project root")
    parser.add_argument(
        "--output-root",
        default=str(REPO_ROOT / ".tmp" / "production-case-validation" / "runs"),
        help="Directory for validation artifacts and reports",
    )
    return parser.parse_args()


def run_json_command(command: list[str], timeout_seconds: int, cwd: Path) -> dict:
    started = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )
    duration = time.perf_counter() - started
    stdout = proc.stdout.strip()
    payload = None
    if stdout:
        payload = json.loads(stdout)
    return {
        "command": command,
        "returncode": proc.returncode,
        "duration_seconds": round(duration, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "json": payload,
    }


def rel_input(project_root: Path, relative_path: str) -> str:
    return str((project_root / relative_path).resolve())


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def make_stage1_cases() -> tuple[Stage1Case, ...]:
    return (
        Stage1Case(
            name="template_manager_v4_stage1",
            inputs=(
                "source/template_manager/template_manager_v4.sv",
                "source/async_fifo/async_fifo_simple.sv",
                "sim/tb_template_manager/tb_manager_v4.sv",
            ),
            top="tb_manager_v4",
            expected_status="ok",
        ),
        Stage1Case(
            name="async_fifo_v2_stage1",
            inputs=(
                "source/async_fifo/async_fifo_v2.sv",
                "sim/tb_async_fifo/tb_async_fifo_v2.sv",
            ),
            top="tb_async_fifo_v2",
            expected_status="input_error",
        ),
        Stage1Case(
            name="toptest_v11_1_predictor_stage1",
            inputs=(
                "source/sensor_fifo_bridge/sensor_fifo_bridge_v6.sv",
                "source/image_pipeline/image_pipeline_v3.sv",
                "source/template_matcher/texture_matcher_v5.sv",
                "source/template_matcher/match_result_adapter_v2.sv",
                "source/async_fifo/async_fifo_simple.sv",
                "source/template_manager/template_manager_v3.sv",
                "source/template_storage/template_storage_ping_pong_no_cdc.sv",
                "source/global_timestamp/global_timestamp.sv",
                "source/retro_histroy_core/retro_history_core_v3.sv",
                "source/cdc_handshake/sync_handshake.sv",
                "source/cdc_handshake/sync_vector.sv",
                "source/tracking_fsm/tracking_fsm.sv",
                "source/unified_predictor/kalman_filter_core_v3.sv",
                "source/unified_predictor/unified_predictor_hls_v3.sv",
                "sim/tb_mt9v034_sim_model/mt9v034_sim_model_v2.sv",
                "sim/aaa_toptest/tb_toptest_v11.1_with_predictor.sv",
            ),
            top="tb_toptest_v11_1_with_predictor",
            expected_status="unsupported_feature",
        ),
    )


def make_stage2_cases() -> tuple[Stage2Case, ...]:
    return (
        Stage2Case(
            name="template_manager_v4_xsim",
            inputs=(
                "source/template_manager/template_manager_v4.sv",
                "source/async_fifo/async_fifo_simple.sv",
                "sim/tb_template_manager/tb_manager_v4.sv",
            ),
            backend="xsim",
            top="tb_manager_v4",
            output_dir_name="template-manager-v4",
            wave_file_name="template_manager_v4.wdb",
            expected_status="ok",
            timeout_seconds=600,
        ),
        Stage2Case(
            name="async_fifo_v2_iverilog",
            inputs=(
                "source/async_fifo/async_fifo_v2.sv",
                "sim/tb_async_fifo/tb_async_fifo_v2.sv",
            ),
            backend="iverilog",
            top="tb_async_fifo_v2",
            output_dir_name="async-fifo-v2-iverilog",
            wave_file_name="async_fifo_v2.vcd",
            expected_status="input_error",
            timeout_seconds=600,
        ),
        Stage2Case(
            name="async_fifo_v2_xsim",
            inputs=(
                "source/async_fifo/async_fifo_v2.sv",
                "sim/tb_async_fifo/tb_async_fifo_v2.sv",
            ),
            backend="xsim",
            top="tb_async_fifo_v2",
            output_dir_name="async-fifo-v2-xsim",
            wave_file_name="async_fifo_v2.wdb",
            expected_status="run_error",
            timeout_seconds=600,
        ),
        Stage2Case(
            name="toptest_v11_1_predictor_xsim",
            inputs=(
                "source/sensor_fifo_bridge/sensor_fifo_bridge_v6.sv",
                "source/image_pipeline/image_pipeline_v3.sv",
                "source/template_matcher/texture_matcher_v5.sv",
                "source/template_matcher/match_result_adapter_v2.sv",
                "source/async_fifo/async_fifo_simple.sv",
                "source/template_manager/template_manager_v3.sv",
                "source/template_storage/template_storage_ping_pong_no_cdc.sv",
                "source/global_timestamp/global_timestamp.sv",
                "source/retro_histroy_core/retro_history_core_v3.sv",
                "source/cdc_handshake/sync_handshake.sv",
                "source/cdc_handshake/sync_vector.sv",
                "source/tracking_fsm/tracking_fsm.sv",
                "source/unified_predictor/kalman_filter_core_v3.sv",
                "source/unified_predictor/unified_predictor_hls_v3.sv",
                "sim/tb_mt9v034_sim_model/mt9v034_sim_model_v2.sv",
                "sim/aaa_toptest/tb_toptest_v11.1_with_predictor.sv",
            ),
            backend="xsim",
            top="tb_toptest_v11_1_with_predictor",
            output_dir_name="toptest-v11-1-predictor",
            wave_file_name="toptest_v11_1_predictor.wdb",
            expected_status="ok",
            timeout_seconds=3600,
        ),
    )


def make_stage3_cases(output_root: Path, project_root: Path) -> tuple[Stage3Case, ...]:
    return (
        Stage3Case(
            name="template_manager_v4_wave_observation",
            wave_file=str((output_root / "template-manager-v4" / "template_manager_v4.wdb").resolve()),
            signals=(
                "tb_manager_v4.clk",
                "tb_manager_v4.rst_n",
                "tb_manager_v4.swap_req",
                "tb_manager_v4.ram_wr_en",
            ),
            window="200000ps",
            anchor="0ps",
        ),
        Stage3Case(
            name="toptest_v11_1_predictor_wave_observation",
            wave_file=str((output_root / "toptest-v11-1-predictor" / "toptest_v11_1_with_predictor.vcd").resolve()),
            signals=(
                "tb_toptest_v11_1_with_predictor.sys_clk",
                "tb_toptest_v11_1_with_predictor.rst_n",
                "tb_toptest_v11_1_with_predictor.fsm_state",
                "tb_toptest_v11_1_with_predictor.pred_valid",
                "tb_toptest_v11_1_with_predictor.match_done",
            ),
            window="20000ps",
            anchor="1000000000ps",
        ),
        Stage3Case(
            name="toptest_v12_5_image_export_wave_observation",
            wave_file=str((project_root / "ai_workspace" / "toptest_v12.5_sim" / "toptest_v12_5_image_export.vcd").resolve()),
            signals=(
                "tb_toptest_v12_5_image_export.sys_clk",
                "tb_toptest_v12_5_image_export.rst_n",
                "tb_toptest_v12_5_image_export.fsm_state",
                "tb_toptest_v12_5_image_export.pred_valid",
                "tb_toptest_v12_5_image_export.match_done",
            ),
            window="20000ps",
            anchor="1000000000ps",
        ),
        Stage3Case(
            name="toptest_v13_predictor_v7_wave_observation",
            wave_file=str((project_root / "ai_workspace" / "toptest_v13_predictor_v7" / "toptest_v13_predictor_v7.vcd").resolve()),
            signals=(
                "tb_toptest_v13_predictor_v7.sys_clk",
                "tb_toptest_v13_predictor_v7.rst_n",
                "tb_toptest_v13_predictor_v7.fsm_state",
                "tb_toptest_v13_predictor_v7.pred_valid",
                "tb_toptest_v13_predictor_v7.match_done",
            ),
            window="20000ps",
            anchor="1000000000ps",
        ),
    )


def run_stage1_cases(project_root: Path, output_root: Path) -> list[dict]:
    results: list[dict] = []
    for case in make_stage1_cases():
        command = [
            sys.executable,
            str(STAGE1_SCRIPT),
            *(rel_input(project_root, item) for item in case.inputs),
            "--top",
            case.top,
        ]
        result = run_json_command(command, timeout_seconds=600, cwd=REPO_ROOT)
        payload = result["json"]
        summary = {
            "name": case.name,
            "expected_status": case.expected_status,
            "ok": payload is not None and payload["status"] == case.expected_status,
            "duration_seconds": result["duration_seconds"],
            "status": payload["status"] if payload is not None else "no_json",
            "message": payload["message"] if payload is not None else "missing JSON output",
            "payload_path": str((output_root / "stage1" / f"{case.name}.json").resolve()),
        }
        write_json(Path(summary["payload_path"]), {"command_result": result, "summary": summary})
        results.append(summary)
    return results


def run_stage2_cases(project_root: Path, output_root: Path) -> list[dict]:
    results: list[dict] = []
    for case in make_stage2_cases():
        case_output_dir = output_root / case.output_dir_name
        command = [
            sys.executable,
            str(STAGE2_SCRIPT),
            *(rel_input(project_root, item) for item in case.inputs),
            "--backend",
            case.backend,
            "--top",
            case.top,
            "--output-dir",
            str(case_output_dir),
            "--wave-file",
            case.wave_file_name,
        ]
        result = run_json_command(command, timeout_seconds=case.timeout_seconds, cwd=REPO_ROOT)
        payload = result["json"]
        summary = {
            "name": case.name,
            "expected_status": case.expected_status,
            "ok": payload is not None and payload["status"] == case.expected_status,
            "duration_seconds": result["duration_seconds"],
            "status": payload["status"] if payload is not None else "no_json",
            "message": payload["message"] if payload is not None else "missing JSON output",
            "payload_path": str((output_root / "stage2" / f"{case.name}.json").resolve()),
            "output_dir": str(case_output_dir.resolve()),
            "artifacts": payload.get("artifacts") if payload is not None else None,
        }
        write_json(Path(summary["payload_path"]), {"command_result": result, "summary": summary})
        results.append(summary)
    return results


def run_stage3_cases(output_root: Path, project_root: Path) -> list[dict]:
    results: list[dict] = []
    for case in make_stage3_cases(output_root, project_root):
        command = [
            sys.executable,
            str(STAGE3_SCRIPT),
            "render-window",
            case.wave_file,
            "--signals",
            *case.signals,
            "--window",
            case.window,
            "--anchor",
            case.anchor,
        ]
        result = run_json_command(command, timeout_seconds=600, cwd=REPO_ROOT)
        payload = result["json"]
        summary = {
            "name": case.name,
            "expected_status": case.expected_status,
            "ok": payload is not None and payload["status"] == case.expected_status,
            "duration_seconds": result["duration_seconds"],
            "status": payload["status"] if payload is not None else "no_json",
            "message": payload["message"] if payload is not None else "missing JSON output",
            "payload_path": str((output_root / "stage3" / f"{case.name}.json").resolve()),
            "wave_file": case.wave_file,
        }
        write_json(Path(summary["payload_path"]), {"command_result": result, "summary": summary})
        results.append(summary)
    return results


def render_markdown_report(report: dict) -> str:
    lines = [
        "# Real Project Validation Report",
        "",
        f"- Project root: `{report['project_root']}`",
        f"- Output root: `{report['output_root']}`",
        "",
        "## Stage 1",
    ]
    for item in report["stage1"]:
        lines.append(
            f"- `{item['name']}`: `{item['status']}` in {item['duration_seconds']}s "
            f"(expected `{item['expected_status']}`)"
        )
        lines.append(f"  - {item['message']}")
    lines.append("")
    lines.append("## Stage 2")
    for item in report["stage2"]:
        lines.append(
            f"- `{item['name']}`: `{item['status']}` in {item['duration_seconds']}s "
            f"(expected `{item['expected_status']}`)"
        )
        lines.append(f"  - {item['message']}")
        artifacts = item.get("artifacts")
        if artifacts and artifacts.get("wave_files"):
            lines.append(f"  - wave files: {', '.join(artifacts['wave_files'])}")
    lines.append("")
    lines.append("## Stage 3")
    for item in report["stage3"]:
        lines.append(
            f"- `{item['name']}`: `{item['status']}` in {item['duration_seconds']}s "
            f"(expected `{item['expected_status']}`)"
        )
        lines.append(f"  - {item['wave_file']}")
    lines.append("")
    stage1_failures = [item for item in report["stage1"] if not item["ok"]]
    stage2_failures = [item for item in report["stage2"] if not item["ok"]]
    stage3_failures = [item for item in report["stage3"] if not item["ok"]]
    lines.append("## Summary")
    if not (stage1_failures or stage2_failures or stage3_failures):
        lines.append("- All selected production-style validation cases matched their expected outcomes.")
    else:
        lines.append("- Some cases deviated from their expected outcomes.")
        for item in [*stage1_failures, *stage2_failures, *stage3_failures]:
            lines.append(f"  - `{item['name']}` -> `{item['status']}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    stage1 = run_stage1_cases(project_root, output_root)
    stage2 = run_stage2_cases(project_root, output_root)
    stage3 = run_stage3_cases(output_root, project_root)

    report = {
        "project_root": str(project_root),
        "output_root": str(output_root),
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
    }
    report_json = output_root / "real-project-validation-report.json"
    report_md = output_root / "real-project-validation-report.md"
    write_json(report_json, report)
    report_md.write_text(render_markdown_report(report), encoding="utf-8")

    print(json.dumps({"status": "ok", "report_json": str(report_json), "report_md": str(report_md)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
