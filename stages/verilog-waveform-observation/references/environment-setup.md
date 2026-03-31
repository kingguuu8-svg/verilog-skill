# Environment Setup

## Environment Goal

Stage 3 should add as little new environment dependency as possible.

The baseline setup is:

- Python available for the observation scripts
- an existing waveform artifact, preferably from stage 2

This stage does not require a new simulator backend when the input is already VCD.
It consumes the wave artifact that stage 2 already produced.

## Recommended Upstream Path

Prefer generating the waveform through stage 2:

```text
stages/verilog-simulation-execution/scripts/run_simulation.py
```

That path already standardizes:

- output directory placement
- log capture
- reported wave file paths

## Supported Input

Currently supported:

- `.vcd`
- `.wdb` from XSIM output directories

WDB support is conditional:

- a same-directory companion `.vcd` is enough by itself
- otherwise the host needs a runnable Vivado `xsim` toolchain
- the `.wdb` file must stay next to its `xsim.dir/<snapshot>` directory so stage 3 can replay it

Currently not supported by default:

- `.fst`
- `.lxt`
- `.lxt2`
- GUI-specific save files

If the project wants FST/LXT support later, add a portable parsing or conversion path first.

## Temporary State

Stage-3 temporary files live under:

```text
.tmp/verilog-waveform-observation/
```

Session files are stored in:

```text
.tmp/verilog-waveform-observation/sessions/
```

Cached WDB exports are stored in:

```text
.tmp/verilog-waveform-observation/exports/
```

These session files are disposable runtime state.

## Common Failure Cases

### 1. Wave File Missing

Symptoms:

- the observation script reports `wave_file_missing`

Check:

- the simulation actually ran
- the requested output directory exists
- the wave file path is the stage-2 reported artifact path

### 2. Unsupported Wave Format

Symptoms:

- the observation script reports `unsupported_wave_format`

Root cause:

- the file is not a supported VCD or XSIM WDB artifact

Fix:

- emit VCD from the testbench
- or add a real portable conversion path before trying to use the stage-3 scripts on that format

### 3. Missing WDB Context

Symptoms:

- the observation script reports `missing_simulation_context`

Root cause:

- the input is `.wdb`, but neither a same-directory companion `.vcd` nor an adjacent `xsim.dir` snapshot is available

Fix:

- keep the full stage-2 XSIM output directory together
- or pass the companion `.vcd` instead
- or rerun stage 2 with `xsim` so the snapshot and wave artifact are regenerated together

### 4. XSIM Replay Unavailable

Symptoms:

- the observation script reports `xsim_backend_unavailable`

Root cause:

- the input is `.wdb`, no companion VCD exists, and the local machine cannot run XSIM

Fix:

- install or expose the Vivado XSIM toolchain
- or reuse the WDB on a machine that already has XSIM
- or keep the companion VCD alongside the WDB so no replay is needed

### 5. Ambiguous Signal Name

Symptoms:

- the observation script reports `ambiguous_signal_name`

Root cause:

- a short alias maps to more than one distinct waveform code

Fix:

- rerun with a hierarchical path such as `tb_top.u_dut.valid`

### 6. Edge On A Vector

Symptoms:

- the observation script reports `edge_requires_single_bit_signal`

Root cause:

- `rise` or `fall` was requested on a multi-bit vector

Fix:

- use a scalar signal
- or bit-select a vector element such as `bus[0]`
- or use `change` when the real requirement is vector-value navigation

## Validation Command

Run the stage-3 validation path with:

```text
python stages/verilog-waveform-observation/scripts/validate_skill.py
```

This validation path reuses stage-2 fixtures to generate a real VCD and, when XSIM is available, a real WDB before reading them.
