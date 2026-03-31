# Interaction Usage

## Signal Discovery

List canonical signal names first when the exact path is unclear:

```text
python scripts/observe_waveform.py list-signals <wave_file.vcd>
```

This returns:

- waveform timescale
- canonical signal names
- widths
- ambiguous short aliases

## One-Shot Window Rendering

Render a bounded observation window without creating a session:

```text
python scripts/observe_waveform.py render-window <wave_file.vcd> --signals clk rst_n tb_top.count --window 30000ps --anchor 0ps
```

Rules:

- `--anchor` is optional
- no `--anchor` means the waveform start
- rows are printed at the anchor and then only on later selected-signal changes

## Session Workflow

Open a reusable session:

```text
python scripts/wave_session.py open <wave_file.vcd> --signals clk rst_n tb_top.count --window 30000ps --anchor 0ps
```

Render the current window again:

```text
python scripts/wave_session.py render <session_id>
```

Move to the next selected edge:

```text
python scripts/wave_session.py next-edge <session_id> --signal clk --edge rise
python scripts/wave_session.py next-edge <session_id> --signal rst_n --edge fall
python scripts/wave_session.py next-edge <session_id> --signal tb_top.count[0] --edge rise
```

Rewrite the whole observation definition:

```text
python scripts/wave_session.py set <session_id> --signals tb_top.count[0] rst_n --window 20000ps --anchor 15000ps
```

Close the session:

```text
python scripts/wave_session.py close <session_id>
```

## Interactive Shell

For human-operated terminal browsing, use:

```text
python scripts/wave_shell.py <wave_file.vcd> --signals clk rst_n tb_top.count --window 30000ps --anchor 0ps
```

Supported shell commands:

```text
show
clk rise
rst_n fall
tb_top.count[0] rise
tb_top.count change
set --signals clk tb_top.count --window 20000ps --anchor 5000ps
quit
```

The shell behavior is:

1. print the current window immediately
2. keep running after printing
3. move the anchor after navigation commands
4. re-render the window after each successful command

## Time Values

Accepted time syntax:

- raw integer ticks in the waveform timescale
- integer with suffix: `fs`, `ps`, `ns`, `us`, `ms`, `s`

Examples:

- `5000`
- `5000ps`
- `20ns`

## Output Shape

Each rendered row follows this shape:

```text
<time>  sig_a: rise  sig_b: 0  sig_c: value_change 0001->0010
```

Conventions:

- single-bit `0 -> 1` prints `rise`
- single-bit `1 -> 0` prints `fall`
- all other changes print `value_change old->new`
- unchanged signals print only their current value
