# Simulation Execution Contract

## Goal

Define the executable contract for the stage-2 simulation runner.

This document describes how the simulation execution wrapper should behave.
It does not define HDL language legality.

## Scope

Stage 2 covers:

- simulation input normalization
- compile and elaboration with `iverilog` or optional Vivado `xvlog/xelab`
- simulation runtime with `vvp` or optional Vivado `xsim`
- stdout and stderr capture
- optional structured TB event extraction from simulator prints
- wave artifact reporting
- structured results for compile and run phases

Stage 2 does not cover:

- waveform interpretation
- debug root-cause analysis from waveforms
- UVM orchestration
- coverage closure
- multi-backend comparison scheduling

## Backend Contract

The current backends are:

1. default:
   `iverilog` + `vvp`
2. optional:
   `xvlog` + `xelab` + `xsim`

Reason:

- `iverilog/vvp` is mature, portable, and aligned with the stage-1 open baseline
- `xsim` covers vendor-backed Xilinx and XPM simulation scenarios that the open baseline cannot execute reliably
- both paths preserve the same stage boundary: execute simulation, capture output, report artifacts

## Input Contract

The runner should accept:

- one or more source files:
  `.v`, `.vh`, `.sv`, `.svh`
- optional `.f` command files
- optional include directories
- optional macro definitions
- optional top-module hint
- optional runtime plusargs
- optional explicit wave file request

`xsim` requires an explicit `--top` because `xelab` must build a named snapshot.

## Output Contract

The runner should return structured results with:

- `status`
- `message`
- `support_range`
- `input_files`
- `checks.compile`
- `checks.run`
- `artifacts`
- `interpretation`

Artifacts should include at minimum:

- output directory
- compiled simulation image path
- compile log path
- elaborate log path when the backend has a distinct elaboration step
- run log path
- wave file paths that were actually emitted

When structured TB event prints are present, artifacts should also include:

- TB event index path
- TB event summary

Runtime classification should not rely only on process exit status.

If the simulator exits zero but the testbench prints explicit failure markers such as:

- `SIM_FAIL`
- `[FAIL]`
- `FAIL:`
- `FINAL RESULT: FAILED`
- runtime `ERROR:` lines, including timestamp-prefixed forms like `[123] ERROR: ...`

the stage should still classify the run as `run_error`.

## Status Model

Normalize outcomes into:

- `ok`
- `environment_error`
- `input_error`
- `syntax_error`
- `elaboration_error`
- `unsupported_feature`
- `run_error`

## Wave Artifact Rule

This stage reports wave files.
It does not analyze them.

If the caller explicitly requests a wave file path, the stage should verify that a wave file was actually emitted.

If no wave file was requested, the stage should still report any waveform artifacts it finds in the output directory.

The current artifact set includes at least:

- `VCD`
- `WDB`

The optional structured-print artifact is:

- `tb-events.json`

## Dependency Rule

Stage 2 assumes the stage-1 language contract still applies.

If source legality is unclear, use the stage-1 language-and-syntax skill first.

## Minimum Validation Matrix

The current stage should validate at least:

- a passing simulation that prints a success marker
- a passing simulation that emits a wave file
- a runtime failure path that is classified separately from compile failure
- a runtime failure path where the simulator exits zero but the testbench logs explicit failure markers
- an optional `xsim` path that proves `WDB` capture when Vivado is available
- an optional `xsim` path that proves auto-attached XPM sources when Vivado is available
