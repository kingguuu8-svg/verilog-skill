# Checker Usage

## Goal

Describe the executable interface for the stage-1 checker dispatcher.

This document is for users and agents that want to run the current skill instead of only reading its language contract.

## Current Tool Strategy

The current checker uses existing tools, not a custom parser:

- optional syntax phase:
  Verible
- required baseline and elaboration phase:
  Icarus Verilog

Default behavior:

- `--syntax-backend auto`
  tries Verible first when available and suitable
- otherwise the checker falls back to an Icarus-only path

Backend discovery order:

- explicit environment variable
- repo-local tool installation
- system `PATH`

Current environment variables:

- `IVERILOG_BIN`
- `VERIBLE_VERILOG_SYNTAX_BIN`
- `VERIBLE_VERILOG_LINT_BIN`

Current repo-local tool location:

- `tools/verible/current`

## Main Commands

Probe tool availability:

```bash
python scripts/probe_backend.py --backend all
```

Run syntax/elaboration checking:

```bash
python scripts/check_syntax.py <inputs...>
```

Run next-layer lint checking:

```bash
python scripts/check_lint.py <inputs...>
```

Run the built-in fixture validation:

```bash
python scripts/validate_skill.py
```

## Supported Inputs

- source files:
  `.v`, `.vh`, `.sv`, `.svh`
- command files:
  `.f`
- optional:
  `--include-dir`
  `--define`
  `--top`
  `--syntax-backend auto|verible|iverilog`

Lint inputs:

- `.v`
- `.sv`
- `.f` files that resolve to `.v/.sv`

Lint options:

- `--rules`
- `--ruleset`
- `--waiver-file`

## Output Model

The checker returns JSON with:

- top-level `status`
- top-level `message`
- `support_range`
- `input_files`
- `checks.syntax`
- `checks.elaboration`
- `interpretation`

Each stage result contains:

- `backend`
- `status`
- `category`
- `message`
- `command`
- `stdout`
- `stderr`
- `locations`

The lint wrapper returns the same top-level shape, but with:

- `checks.lint`

## Fallback Behavior

- if Verible is unavailable in `auto` mode, the checker falls back to Icarus and reports that fallback in `checks.syntax`
- if Verible is explicitly requested and unavailable, the result is `environment_error`
- if Verible syntax fails, the checker stops before elaboration
- if Verible passes but Icarus later fails, the failure is treated as an elaboration/backend limitation path rather than a primary syntax-parser failure

Lint behavior:

- lint uses `verible-verilog-lint`
- lint is source-level only in stage 1
- lint does not replace syntax/elaboration
- lint currently does not apply include-dir or define preprocessing

## Current Limits

- no full lint stage
- only a minimal next-layer lint wrapper
- no simulation execution
- no waveform support
- no UVM verification flow
- no automatic multi-backend comparison mode
