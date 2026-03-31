# Simulation Usage

## Goal

Describe the command-line interface for the stage-2 simulation runner.

## Main Command

Run a simulation:

```bash
python scripts/run_simulation.py <inputs...>
```

## Common Options

- `--backend`
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

Run the optional Vivado backend and request a `WDB` artifact:

```bash
python scripts/run_simulation.py fixtures/xpm_cdc_single.f --backend xsim --top tb_xpm_cdc_single --wave-file xpm_cdc_single.wdb
```

Run `xsim` on an existing DUT and testbench:

```bash
python scripts/run_simulation.py <dut>.sv <tb>.sv --backend xsim --top <tb_top> --wave-file run.wdb
```

## Artifact Behavior

By default, the runner creates a dedicated output directory under:

- `.tmp/verilog-simulation-execution`

It writes:

- `sim.out`
- `compile.log`
- `run.log`
- `elaborate.log` when the backend separates elaboration from compile
- any wave files emitted by the testbench

## Wave Request Behavior

If `--wave-file` is provided, the runner:

- passes the requested path to the simulation
- expects the testbench to emit a wave file at that path
- reports an error if the wave file was requested but not produced

Backend-specific behavior:

- `iverilog/vvp` passes the requested path as runtime plusargs such as `+WAVE_FILE=...`
- `xsim` uses `--wdb` when the requested suffix is `.wdb`
- `xsim` passes non-`.wdb` requests through `--testplusarg` and still reports any simulator-emitted `WDB`

This stage does not inject waveform dumping into arbitrary testbenches automatically.
If the testbench does not already support dumping, add or adapt dump logic in the testbench.

## JSON Result Shape

The runner returns JSON with:

- `checks.compile`
- `checks.run`
- `artifacts.output_dir`
- `artifacts.compiled_image`
- `artifacts.compile_log`
- `artifacts.elaborate_log` when present
- `artifacts.run_log`
- `artifacts.wave_files`

Use these fields directly instead of scraping plain text logs when integrating this stage into later skills.

## Runtime Failure Detection

The runner does not trust process exit status alone.

If runtime output contains explicit failure markers such as:

- `SIM_FAIL`
- `[FAIL]`
- `FAIL:`
- `FINAL RESULT: FAILED`
- `ERROR:`, including timestamp-prefixed forms

the run is classified as `run_error` even when `vvp` or `xsim` exits with code `0`.

## Backend Notes

- `--top` is optional for `iverilog`, but required for `xsim`
- `xsim` automatically compiles `glbl.v`
- `xsim` automatically attaches Vivado `XPM` sources when the resolved HDL inputs reference `xpm_*`
