# Observation Contract

## Stage Boundary

`verilog-waveform-observation` is the stage-3 skill in the chain.

Its job is not to prove functional correctness.
Its real job is to turn waveform artifacts into bounded, queryable text observations.

This stage is responsible for:

- waveform file loading
- signal catalog discovery
- anchor-based window rendering
- next-event navigation
- session persistence for repeated queries

This stage is not responsible for:

- root-cause diagnosis
- waveform screenshots or GUI viewer automation
- assertion reasoning from waveforms
- pass/fail decisions that are not already encoded in the waveform or simulation logs

## Input Contract

The minimum input set is:

- waveform file path
- selected signal names
- observation window length

Optional input:

- anchor time

If anchor time is omitted, the observation starts at the waveform beginning.

## Supported Wave Format

The initial supported waveform format is:

- `.vcd`

This stage intentionally starts with VCD because:

- stage 2 already emits VCD naturally through common testbench `$dumpfile` flows
- VCD is text-based and portable
- stage 3 should avoid adding a new mandatory parser dependency before the contract is stable

If a caller provides `.fst`, `.lxt`, or other formats, the stage should return an explicit unsupported-format result instead of pretending the wave is unreadable for unknown reasons.

## Signal Naming Contract

Signal selection should prefer:

1. full hierarchical names
2. shorter aliases only when unambiguous

If a short signal name maps to more than one distinct waveform code, the stage should reject it and ask for a hierarchical path.

Bit-select navigation is allowed for vector signals, for example:

- `tb.count[0]`
- `u_dut.valid_pipe[2]`

Single-bit edge concepts apply only to:

- scalar signals
- bit-selected vector elements

Whole vectors should be treated as value snapshots and value changes, not as rise/fall edges.

## Window Rendering Contract

Given:

- anchor time `T0`
- window length `W`

The stage observes:

- `[T0, T0 + W]`

Rendering rules:

1. Always print one row at `T0`, even if no signal changes there.
2. Traverse the rest of the window in time order.
3. Print a new row only when at least one selected signal changes.
4. In each printed row, show every selected signal:
   - changed single-bit signals: `rise` or `fall` when applicable
   - changed vector or unknown states: `value_change old->new`
   - unchanged signals: current value

Example shape:

```text
11230ps  sig_a: rise  sig_b: fall  sig_c: 1  bus_d: 0011
```

## Navigation Contract

The stage should support repeated navigation through the current session.

Required navigation operations:

- move to the next `rise` of a selected single-bit signal
- move to the next `fall` of a selected single-bit signal
- rewrite the signal set, window length, and optional anchor
- close the session

Recommended extension:

- next `change` for vectors or any selected signal

Navigation anchor updates should be strictly after the previous anchor time.

## Validation Contract

The stage is not complete enough for use unless there is a runnable validation path.

The minimal validation path should prove:

- a real VCD can be loaded
- the signal catalog can be listed
- the anchor row is always rendered
- later change rows are rendered only on selected-signal changes
- next-edge navigation changes the anchor correctly
- the interactive shell can open and accept commands
