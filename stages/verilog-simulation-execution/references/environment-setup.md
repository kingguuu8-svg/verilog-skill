# Environment Setup

## Goal

Describe the minimum environment required to run the stage-2 simulation execution flow.

## Minimum Requirements

The stage-2 execution path assumes:

- Python can run the scripts under `scripts/`
- the repository can write temporary files under `.tmp/verilog-simulation-execution`
- `iverilog` and `vvp` are available for the default backend
- Vivado `xsim` is available when the optional vendor backend is needed

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

Optional Vivado repo-local layout:

- `tools/vivado/current/bin/xvlog.bat`
- `tools/vivado/current/bin/xelab.bat`
- `tools/vivado/current/bin/xsim.bat`
- `tools/vivado/current/data/`

Use that layout when you want `xsim` without relying on shell `PATH`.

## Environment Variables

Supported runtime overrides:

- `IVERILOG_BIN`
- `VVP_BIN`
- `XVLOG_BIN`
- `XELAB_BIN`
- `XSIM_BIN`
- `VIVADO_BIN_DIR`
- `VIVADO_ROOT`
- `VIVADO_BIN`
- `RDI_BINROOT`

Use them for one-off diagnosis or bootstrap situations.

Prefer repo-local tools for steady-state usage.

## Temporary Directory Behavior

The stage-2 scripts override `TMP` and `TEMP` to:

- `.tmp/verilog-simulation-execution`

Reason:

- keep runtime artifacts inside the repository workspace
- avoid host temp-directory encoding problems on Windows

When `xsim` is used, the scripts also redirect these user-profile-sensitive variables into an ASCII-safe repo-local area:

- `APPDATA`
- `LOCALAPPDATA`
- `HOME`
- `USERPROFILE`

Reason:

- older Vivado releases can fail when their profile or temp paths contain non-ASCII characters
- stage 2 should not depend on one machine's user-profile encoding behavior

The redirected root is under:

- `.tmp/verilog-simulation-execution/vivado-user`

## XSIM Notes

Stage 2 automatically prepares these dependencies for `xsim`:

- `glbl.v` from the resolved Vivado install
- Vivado `XPM` source files when the HDL inputs reference `xpm_*`

This is enough for bounded module-style Xilinx and XPM simulation cases.
It is not a general Vivado project-management layer.

## Failure Diagnosis

### Compile Backend Missing

Typical symptom:

- `environment_error`
- compile backend not found

Check:

1. repo-local `iverilog` path
2. `IVERILOG_BIN`
3. system `PATH` fallback
4. reinstall the repo-local Icarus toolchain if the binary exists but does not launch

### Runtime Backend Missing

Typical symptom:

- `environment_error`
- runtime backend not found

Check:

1. repo-local `vvp` path
2. `VVP_BIN`
3. sibling `vvp` next to `iverilog`
4. system `PATH` fallback

### XSIM Backend Missing

Typical symptom:

- `environment_error`
- compile backend not found or not runnable for `xsim`

Check:

1. repo-local `tools/vivado/current/bin`
2. `XVLOG_BIN`, `XELAB_BIN`, `XSIM_BIN`
3. `VIVADO_BIN_DIR` or `VIVADO_ROOT`
4. system `PATH` fallback
5. Windows common-install fallback under `Xilinx/Vivado` if no explicit configuration was provided

If the tools exist but the probe still fails on Windows, inspect whether the active user-profile path contains non-ASCII characters and confirm the stage-2 wrapper is allowed to write under `.tmp/verilog-simulation-execution/vivado-user`.

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
3. if using `xsim`, the Vivado toolchain is runnable
4. the testbench actually contains dump logic or understands the wave plusargs you pass when you request non-`.wdb` artifacts
