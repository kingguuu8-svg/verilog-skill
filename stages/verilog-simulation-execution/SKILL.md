---
name: verilog-simulation-execution
description: Execute stage-2 Verilog/SystemVerilog simulations with mature existing tools, capture simulator print output, and collect generated waveform files without analyzing them. Use when a workflow needs to compile and run module-style testbenches with `iverilog/vvp` or optional Vivado `xsim`, gather stdout/stderr, or verify that a simulation emitted expected `VCD` or `WDB` artifacts.
---

# Verilog Simulation Execution

Use this skill as the second stage of the `verilog-skill` chain.

Do not blur simulation execution with waveform analysis.
This skill runs simulations and reports artifacts.
It does not interpret waveforms.

## Core Rule

Apply this stage only after the source is already inside the stage-1 language contract, or when simulation execution itself is the next blocking step.

Prefer the narrowest execution path that can answer:

1. does the testbench compile
2. does the simulation run
3. what did the simulator print
4. which waveform files were emitted

## What This Skill Does

- compile and elaborate simulation inputs with `iverilog`
- execute the compiled simulation with `vvp`
- optionally compile, elaborate, and run with Vivado `xvlog/xelab/xsim`
- capture stdout and stderr
- record compiled image, log files, and waveform file paths
- distinguish compile failures from runtime failures

## Workflow

### 1. Confirm Stage Boundary

Read [references/execution-contract.md](references/execution-contract.md) first.

Use it to keep the skill limited to:

- simulation execution
- print capture
- artifact capture

Do not expand into waveform analysis here.

### 2. Reuse Stage-1 Assumptions

Read [../verilog-language-and-syntax/SKILL.md](../verilog-language-and-syntax/SKILL.md) when the HDL language mode or backend support boundary is unclear.

Stage 2 depends on stage 1 for:

- accepted HDL subset
- input normalization shape
- repo-local backend discovery policy

### 3. Prepare The Runtime Environment

Read [references/environment-setup.md](references/environment-setup.md) when you need to:

- prepare `iverilog` and `vvp`
- prepare optional Vivado `xsim`
- bootstrap repo-local Icarus tools
- bootstrap repo-local Vivado tools
- diagnose missing runtime backends

### 4. Use The Execution Interface

Read [references/simulation-usage.md](references/simulation-usage.md) before running or extending the execution scripts.

Read [references/tb-event-protocol.md](references/tb-event-protocol.md) when you want to:

- add structured milestone prints to a testbench
- extract a lightweight event index from simulator output
- navigate large-wave simulations through sparse project-defined checkpoints

Use the scripts in [scripts/](scripts/) for executable stage-2 work:

- `scripts/run_simulation.py`
- `scripts/extract_tb_events.py`
- `scripts/validate_skill.py`

## Execution Rules

When running simulations:

- prefer repo-local toolchains first
- keep output artifacts in a deterministic output directory
- capture both compile and run logs
- treat missing wave output as a real failure when a wave file was explicitly requested
- report artifact paths instead of paraphrasing them away
- when the testbench has meaningful milestones, prefer structured `SKILL_EVT|...` prints so stage 2 can emit a lightweight event index alongside the normal logs and wave files

## Backend Direction

The stage currently supports:

- default open-source path:
  `iverilog` + `vvp`
- optional vendor path:
  `xvlog` + `xelab` + `xsim`

Use the narrowest mature backend that can answer the question.

Prefer:

- `iverilog/vvp` for portable module-style testbenches
- `xsim` when the design or testbench depends on Xilinx/XPM simulation support

## Output Expectation

When using this skill, produce conclusions in this order:

1. whether compile/elaboration passed
2. whether runtime execution passed
3. what the simulator printed
4. where the compiled image, logs, and wave files were written
5. what the next action should be if compile or runtime failed
