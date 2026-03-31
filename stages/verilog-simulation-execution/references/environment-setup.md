# Environment Setup

## Goal

Describe the minimum environment required to run the stage-2 simulation execution flow.

## Minimum Requirements

The stage-2 execution path assumes:

- Python can run the scripts under `scripts/`
- the repository can write temporary files under `.tmp/verilog-simulation-execution`
- `iverilog` is available
- `vvp` is available

## Preferred Setup

Prefer the repo-local Icarus install already used by stage 1:

- `tools/iverilog/current/bin/iverilog.exe`
- `tools/iverilog/current/bin/vvp.exe`
- `tools/iverilog/current/lib/`
- `tools/iverilog/current/include/`

Use the stage-1 bootstrap script to create that layout:

- [../../verilog-language-and-syntax/scripts/install_iverilog.py](../../verilog-language-and-syntax/scripts/install_iverilog.py)

Example:

```bash
python ../verilog-language-and-syntax/scripts/install_iverilog.py --source-root <existing-icarus-root>
```

## Environment Variables

Supported runtime overrides:

- `IVERILOG_BIN`
- `VVP_BIN`

Use them for one-off diagnosis or bootstrap situations.

Prefer repo-local tools for steady-state usage.

## Temporary Directory Behavior

The stage-2 scripts override `TMP` and `TEMP` to:

- `.tmp/verilog-simulation-execution`

Reason:

- keep runtime artifacts inside the repository workspace
- avoid host temp-directory encoding problems on Windows

## Failure Diagnosis

### Compile Backend Missing

Typical symptom:

- `environment_error`
- compile backend not found

Check:

1. repo-local `iverilog` path
2. `IVERILOG_BIN`
3. system `PATH` fallback

### Runtime Backend Missing

Typical symptom:

- `environment_error`
- runtime backend not found

Check:

1. repo-local `vvp` path
2. `VVP_BIN`
3. sibling `vvp` next to `iverilog`
4. system `PATH` fallback

### Wave File Missing

Typical symptom:

- compile and run succeeded
- requested wave file was not emitted

Interpretation:

- the simulation executed
- but the active testbench did not honor the requested dump path
- stage 2 should report this as a wave-generation problem, not as waveform-analysis work

## Practical Rule

Before blaming HDL behavior, first verify:

1. `iverilog` is runnable
2. `vvp` is runnable
3. the testbench actually contains dump logic or understands the wave plusargs you pass
