# Environment Setup

## Environment Goal

Stage 3 should add as little new environment dependency as possible.

The baseline setup is:

- Python available for the observation scripts
- an existing `.vcd` waveform artifact

This stage does not require a new simulator backend.
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

- the file is not a VCD

Fix:

- emit VCD from the testbench
- or add a real portable conversion path before trying to use the stage-3 scripts on that format

### 3. Ambiguous Signal Name

Symptoms:

- the observation script reports `ambiguous_signal_name`

Root cause:

- a short alias maps to more than one distinct waveform code

Fix:

- rerun with a hierarchical path such as `tb_top.u_dut.valid`

### 4. Edge On A Vector

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

This validation path reuses stage-2 fixtures to generate a real VCD before reading it.
