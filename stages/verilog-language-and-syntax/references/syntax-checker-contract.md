# Syntax Checker Contract

## Goal

Define the executable contract for the stage-1 checker dispatcher.

This document does not define the language subset itself.
It defines how the thin wrapper around existing tools must behave when enforcing that subset.

## Scope

Stage 1 checker covers:

- tool discovery
- backend selection
- language mode selection
- syntax checking
- elaboration checking
- normalized reporting

Stage 1 checker does not yet cover:

- full lint rule enforcement
- waveform analysis
- multi-backend orchestration
- UVM or class-based verification flows

## Checker Chain

Stage 1 uses existing tools in this order:

1. optional syntax phase:
   `verible-verilog-syntax`
2. required baseline and elaboration phase:
   `iverilog -g2012 -t null`

Reason:

- Verible is useful as a parser-first syntax stage when available
- Icarus provides the required always-available syntax/elaboration baseline for this skill
- the wrapper must orchestrate these tools; it must not re-implement parsing or elaboration itself

## Input Contract

The checker should accept:

- one or more source files:
  `.v`, `.vh`, `.sv`, `.svh`
- optional file lists:
  `.f`
- optional include directories
- optional macro definitions
- optional top-module hint
- optional syntax backend selection:
  `auto|verible|iverilog`

## Environment Contract

The checker must treat environment failures as first-class outcomes.

In particular:

- backend not found
- backend found but not runnable
- temp directory path problems
- file path problems

must be reported separately from HDL language errors.

For the current Windows environment, the checker should support overriding `TMP` and `TEMP` to an ASCII-safe directory when needed.
Backend discovery may use:

- explicit environment variables
- repo-local tool installs
- system `PATH`

## Output Contract

The checker must produce structured results with these fields in spirit, even if the exact JSON shape evolves:

- `status`
- `category`
- `message`
- `support_range`
- `input_files`
- `checks.syntax`
- `checks.elaboration`

Each stage result should include at minimum:

- `backend`
- `status`
- `category`
- `message`
- `command`
- `stdout`
- `stderr`
- `locations`

## Status Model

The checker should normalize outcomes into these categories:

- `ok`
- `environment_error`
- `input_error`
- `syntax_error`
- `elaboration_error`
- `unsupported_feature`

## Support Range Reporting

The checker must report its supported range explicitly.

At minimum that report should include:

- compatibility baseline
- default target language
- accepted input file types
- clearly supported language areas
- best-effort language areas
- excluded-by-default language areas

This prevents the checker from behaving like a black box.

## Interpretation Rule

The checker must help the caller distinguish:

1. invalid under the stage-1 contract
2. valid by standard but outside the stage-1 default subset
3. allowed by contract but unsupported by the current backend
4. plain syntax/elaboration failure inside the intended subset

The checker is not the language definition.
It is an enforcement tool with backend limitations.

## Error Location Reporting

When the backend emits file and line information, the checker must return structured location entries instead of leaving location data only inside raw stderr.

At minimum each location entry should contain:

- `file`
- `line`
- optional `column`
- diagnostic message

## File Selection Rule

The checker should support two usage styles:

1. explicit file list from the caller
2. command-file driven input through `.f`

Command-file relative paths must be resolved relative to the `.f` file itself.
It should not silently guess unrelated files outside the user-provided scope.

## First Implementation Boundary

The first implementation should stay minimal:

- probe `iverilog`
- probe `verible-verilog-syntax` when requested or when `auto` mode may use it
- run Verible only as a syntax phase
- run Icarus as the required elaboration baseline
- return normalized diagnostics and locations

Do not add simulation execution in this first checker contract.
Simulation belongs to the next bounded layer unless explicitly requested later.

## Script Layout

The first scripts should be:

- `scripts/probe_backend.py`
- `scripts/check_syntax.py`
- `scripts/validate_skill.py`

Optional later additions:

- `scripts/check_backend_matrix.py`

## Minimum Validation Matrix

The current stage should validate at least:

- passing Verilog-2005
- passing SystemVerilog RTL subset
- passing `.f` command-file input
- passing `--include-dir`
- passing `--define`
- passing `--top`
- syntax failure with location
- elaboration failure
- missing dependency or include failure
- auto fallback when Verible is unavailable
