# Simulation Execution Contract

## Goal

Define the executable contract for the stage-2 simulation runner.

This document describes how the simulation execution wrapper should behave.
It does not define HDL language legality.

## Scope

Stage 2 covers:

- simulation input normalization
- compile and elaboration with `iverilog`
- simulation runtime with `vvp`
- stdout and stderr capture
- wave artifact reporting
- structured results for compile and run phases

Stage 2 does not cover:

- waveform interpretation
- debug root-cause analysis from waveforms
- UVM orchestration
- coverage closure
- vendor-library automation
- multi-backend comparison scheduling

## Backend Contract

The initial backend pair is:

1. `iverilog`
2. `vvp`

Reason:

- they are mature and widely used for open-source RTL simulation
- they align with the stage-1 compile baseline
- they are sufficient for module-style testbenches and emitted VCD-style waveforms

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
- run log path
- wave file paths that were actually emitted

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

## Dependency Rule

Stage 2 assumes the stage-1 language contract still applies.

If source legality is unclear, use the stage-1 language-and-syntax skill first.

## Minimum Validation Matrix

The current stage should validate at least:

- a passing simulation that prints a success marker
- a passing simulation that emits a wave file
- a runtime failure path that is classified separately from compile failure
