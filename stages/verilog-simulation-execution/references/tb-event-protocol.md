# TB Event Protocol

## Goal

Define a lightweight structured-print convention that testbenches can emit during simulation so stage 2 can build a fast event index without reading the full waveform.

This protocol is a navigation aid.
It does not replace waveforms.

## Why Use It

Use structured TB events when you want:

- cheap checkpoints for long simulations
- a searchable event timeline before opening a large wave file
- project-local protocol markers that match the verification intent
- an automation-friendly bridge from simulator output into later analysis

Keep the full wave dump for complete evidence.
Use TB events to point at the interesting moments.

## Prefix

Every structured event line should start with:

- `SKILL_EVT|`

The current extractor ignores ordinary `$display` lines and only parses lines with this prefix.

## Field Format

After the prefix, emit `key=value` fields separated by `|`.

Example:

```verilog
$display("SKILL_EVT|time_ps=%0t|kind=reset_release|signal=rst_n|value=%0b", $time, rst_n);
```

Escaping rule:

- if a value itself contains `|` or `\`, escape it as `\|` or `\\`

## Required Field

- `kind`

Without `kind`, the extractor records a parse error and ignores that line as an event.

## Recommended Fields

- `time_ps`
- `name`
- `signal`
- `value`
- `state`
- `channel`
- `note`

`time_ps` is strongly recommended because it makes later correlation with wave anchors direct.

## Practical Guidance

Prefer event kinds that match verification intent rather than low-level toggles.

Good candidates:

- reset asserted or released
- handshake accepted
- FIFO push or pop
- packet or frame boundary
- scoreboard milestone
- assertion failure context
- end-of-test summary

Avoid printing every clock edge.
The event stream should stay sparse and meaningful.

## Example

```verilog
$display("SKILL_EVT|time_ps=%0t|kind=tb_start|name=tb_sync_vector", $time);
$display("SKILL_EVT|time_ps=%0t|kind=reset_release|signal=dst_rst_n|value=%0b", $time, dst_rst_n);
$display("SKILL_EVT|time_ps=%0t|kind=handshake_accept|channel=src|value=%0h", $time, src_data);
$display("SKILL_EVT|time_ps=%0t|kind=simulation_pass|note=all_checks_complete", $time);
```

## Extraction Path

Stage 2 now includes:

- `scripts/extract_tb_events.py`

Given a stage-2 `run.log`, it emits:

- `tb-events.json`

The stage-2 runner also writes this artifact automatically when it sees at least one `SKILL_EVT|...` line.

## Current Output Shape

The extracted index includes:

- `format`
- `protocol_prefix`
- `run_log`
- `summary`
- `events`
- `parse_errors`

Use it as a cheap event catalog, then open the real wave file only when a specific anchor needs deeper inspection.
