---
name: verilog-language-and-syntax
description: Define and enforce the stage-1 language contract for Verilog and SystemVerilog development. Use when Codex needs to write, review, normalize, or syntax-check Verilog/SystemVerilog for open-source RTL projects, especially to choose a portable language subset, apply project language requirements, distinguish standard legality from backend support, or prepare code for syntax/elaboration checking.
---

# Verilog Language And Syntax

Use this skill as the first stage of the `verilog-skill` chain.

Do not start from tool commands alone.
Start from the language contract, then attach checking.

## Core Rule

Apply this two-layer policy unless the user explicitly requires something else:

1. compatibility baseline:
   `Verilog-2005`
2. default generation target:
   `RTL-oriented SystemVerilog subset`

Do not default to full verification-language SystemVerilog.

## What This Skill Does

- choose the default language mode for the task
- constrain AI code generation to the approved subset
- explain whether a construct is:
  contract-allowed,
  discouraged,
  forbidden by default,
  or outside backend support
- prepare the task for syntax/elaboration checking

## Workflow

### 1. Read The Language Contract

Read [references/language-requirements.md](references/language-requirements.md) first.

Use it as the controlling document for:

- default target language
- preferred constructs
- discouraged constructs
- forbidden-by-default constructs
- error interpretation rules

### 2. Confirm Public Scope

Read [references/language-support-scope.md](references/language-support-scope.md) when you need the outward-facing support boundary.

Use it to avoid over-claiming support.

### 3. Check Source Authority

Read [references/official-syntax-sources.md](references/official-syntax-sources.md) when you need to separate:

- language standard
- tool implementation
- skill policy

Never treat one backend as the definition of the language.

### 4. Check Scenario And Platform Context

Read these when task context matters:

- [references/verilog-main-usage-scenarios.md](references/verilog-main-usage-scenarios.md)
- [references/mainstream-platform-language-support.md](references/mainstream-platform-language-support.md)

Use them to decide whether the task is primarily:

- FPGA RTL
- ASIC/SoC RTL
- simulation-oriented RTL
- simple module-style verification

### 5. Attach Executable Checking

Read [references/syntax-checker-contract.md](references/syntax-checker-contract.md) before changing checker behavior or interpreting checker output.
Read [references/checker-usage.md](references/checker-usage.md) for the supported command-line surface and output model.
Read [references/lint-checker-contract.md](references/lint-checker-contract.md) when extending or interpreting the optional lint layer.

Use the scripts in [scripts/](scripts/) for executable stage-1 checking:

- `scripts/install_verible.py`
- `scripts/install_iverilog.py`
- `scripts/probe_backend.py`
- `scripts/check_syntax.py`
- `scripts/check_lint.py`
- `scripts/validate_skill.py`

## Generation Rules

By default:

- prefer portable synthesizable RTL
- allow simple module-style testbench code
- use modern RTL SystemVerilog constructs only when they improve clarity and stay inside the approved subset
- avoid class/UVM/randomization/coverage-heavy verification constructs unless explicitly requested

If the existing codebase already uses an established style, preserve that style unless it conflicts with explicit user requirements.

## Checking Rules

When attaching syntax checking:

- treat checker output as an implementation result, not as the language definition
- distinguish among:
  illegal by contract,
  legal by standard but outside the default subset,
  contract-allowed but unsupported by the current backend
- prefer reporting that distinction explicitly instead of collapsing everything into "syntax error"

## Initial Backend Direction

The first practical checker path is fixed as:

- optional syntax backend:
  Verible
- required baseline and elaboration backend:
  Icarus Verilog

Default behavior:

- `auto`: use Verible first when available and input shape is supported
- otherwise fall back to Icarus-only syntax plus elaboration

Tool installation preference:

- prefer repo-local tools under `tools/<backend>/current`
- treat `PATH` only as a compatibility fallback, not as the primary dependency path

Optional next layer:

- `verible-verilog-lint` for source-level lint diagnostics
- use it after syntax/elaboration when you need style or structural rule checks

Do not silently widen the language contract just because one stronger backend accepts a construct.

## Resource Layout

Keep this skill organized as:

- `SKILL.md`: trigger conditions and execution workflow
- `references/`: longer supporting documents loaded only when needed
- `scripts/`: executable checker dispatcher, lint wrapper, probes, and validation
- `fixtures/`: minimal input cases for checker validation

## Output Expectation

When using this skill, produce conclusions in this order:

1. chosen language mode
2. relevant subset or restriction
3. whether the code/request stays inside the stage-1 contract
4. what checker/backend consequence follows
5. support-range note and error location details when failures occur
6. per-stage results for `checks.syntax` and `checks.elaboration`
7. lint-stage result when the optional next layer is used
