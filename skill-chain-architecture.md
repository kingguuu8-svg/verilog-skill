# Skill Chain Architecture

## Core Decision

This project is a skill chain, not a single skill.

That means the repository should be designed as a sequence of dependent stages.
Each stage solves one bounded problem and hands a cleaner artifact to the next stage.

## Why A Skill Chain

Verilog/SystemVerilog development is not one action.
It includes at least:

- language selection
- code generation rules
- syntax checking
- linting
- simulation
- debugging
- iteration

If these are collapsed into one skill too early, the AI will mix:

- language rules
- tool limitations
- workflow steps
- project-specific conventions

The result will be unstable.

## Stage-1 Definition

The first stage is:

`verilog-language-and-syntax`

Its job is not just "introduce Verilog".
Its real job is to define the language contract the AI must obey.

Stage 1 must contain two inseparable parts:

1. language usage guidance
2. syntax-check execution

If only guidance exists, the AI can drift.
If only a checker exists, the AI does not know what style and subset it should target.

## Stage-1 Inputs

Stage 1 should accept:

- source files: `.v`, `.vh`, `.sv`, `.svh`
- optional file lists: `.f`
- optional macro definitions
- optional include directories
- optional top-module hint

## Stage-1 Outputs

Stage 1 should produce:

- chosen language mode
- chosen compatibility baseline
- syntax/elaboration result
- normalized error report
- next-action hint

## Stage-1 Language Contract

Stage 1 should answer these questions before any later workflow runs:

- what the default target language is
- what constructs are preferred
- what constructs are allowed but discouraged
- what constructs are forbidden by default
- what belongs outside the guaranteed subset

This contract should be treated as the root of the whole chain.

## Stage-1 Checker Contract

The syntax-check side of stage 1 should:

- detect tool availability
- choose the intended backend
- run syntax/elaboration checks
- report environment failures separately from HDL failures
- avoid pretending unsupported language features are always user bugs

## Dependency Rule

Later stages depend on stage 1.

Examples:

- lint stage depends on stage-1 language mode
- simulation stage depends on stage-1 compile baseline
- debug stage depends on stage-1 normalized diagnostics

Therefore stage 1 must be completed first and kept narrow.

## Immediate Build Goal

The immediate goal is to create a first-stage skill that teaches the AI:

- how to write the intended Verilog/SystemVerilog subset
- how to check that subset with a real program

Only after that is stable should the repository add stage 2.
