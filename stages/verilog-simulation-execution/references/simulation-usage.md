# Simulation Usage

## Goal

Describe the command-line interface for the stage-2 simulation runner.

## Main Command

Run a simulation:

```bash
python scripts/run_simulation.py <inputs...>
```

## Common Options

- `--top`
- `--include-dir`
- `--define`
- `--runtime-arg`
- `--wave-file`
- `--output-dir`

## Typical Examples

Compile and run a direct testbench plus DUT:

```bash
python scripts/run_simulation.py fixtures/counter_dut.sv fixtures/tb_counter_wave.sv --top tb_counter_wave --wave-file counter.vcd
```

Run through a `.f` file:

```bash
python scripts/run_simulation.py fixtures/pass_counter.f --top tb_counter_wave --wave-file counter.vcd
```

Pass runtime plusargs through `vvp`:

```bash
python scripts/run_simulation.py fixtures/pass_counter.f --top tb_counter_wave --runtime-arg +SEED=1 --wave-file counter.vcd
```

## Artifact Behavior

By default, the runner creates a dedicated output directory under:

- `.tmp/verilog-simulation-execution`

It writes:

- `sim.out`
- `compile.log`
- `run.log`
- any wave files emitted by the testbench

## Wave Request Behavior

If `--wave-file` is provided, the runner:

- passes the requested path to the simulation as runtime plusargs
- expects the testbench to emit a wave file at that path
- reports an error if the wave file was requested but not produced

This stage does not inject waveform dumping into arbitrary testbenches automatically.
If the testbench does not already support dumping, add or adapt dump logic in the testbench.

## JSON Result Shape

The runner returns JSON with:

- `checks.compile`
- `checks.run`
- `artifacts.output_dir`
- `artifacts.compiled_image`
- `artifacts.compile_log`
- `artifacts.run_log`
- `artifacts.wave_files`

Use these fields directly instead of scraping plain text logs when integrating this stage into later skills.

## Runtime Failure Detection

The runner does not trust process exit status alone.

If runtime output contains explicit failure markers such as:

- `SIM_FAIL`
- `[FAIL]`
- `FINAL RESULT: FAILED`
- `ERROR:`

the run is classified as `run_error` even when `vvp` exits with code `0`.
