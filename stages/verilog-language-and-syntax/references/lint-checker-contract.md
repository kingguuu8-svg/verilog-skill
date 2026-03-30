# Lint Checker Contract

## Goal

Define the executable contract for the optional next-layer lint capability in this skill.

This layer does not replace syntax and elaboration checking.
It runs after or alongside a source that is expected to be syntax-valid.

## Backend

The current lint backend is:

- `verible-verilog-lint`

This layer remains optional relative to the mandatory syntax/elaboration baseline.

## Scope

The lint layer covers:

- source-level style and structural rule checks
- rule-based diagnostics with file and line locations
- optional rule and waiver customization

The lint layer does not cover:

- elaboration
- simulation
- waveform analysis
- preprocessing-aware include or define expansion in stage 1

## Input Contract

The lint wrapper accepts:

- `.v`
- `.sv`
- `.f` files that resolve to `.v` or `.sv` compilation units

Stage-1 lint does not accept as standalone lint targets:

- `.vh`
- `.svh`
- input shapes that require include-dir or macro preprocessing

## Output Contract

The lint wrapper must return JSON with:

- top-level `status`
- top-level `message`
- `support_range`
- `input_files`
- `checks.lint`
- `interpretation`

The `checks.lint` stage must include:

- `backend`
- `status`
- `category`
- `message`
- `command`
- `stdout`
- `stderr`
- `locations`

## Status Model

The lint wrapper should normalize outcomes into:

- `ok`
- `environment_error`
- `input_error`
- `syntax_error`
- `lint_error`
- `unsupported_feature`

## Interpretation Rule

The lint wrapper must distinguish:

1. lint rule violations
2. source syntax failure before linting can be trusted
3. unsupported input shape for the current lint wrapper
4. unavailable lint backend

Lint failure must not be conflated with syntax failure.

## First Implementation Boundary

The first implementation should stay minimal:

- probe `verible-verilog-lint`
- run default ruleset unless the user overrides it
- allow optional `--rules`, `--ruleset`, and waiver file input
- return structured locations and rule-bearing diagnostics

Do not add autofix as part of the first lint wrapper.
