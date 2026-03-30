# verilog-skill

An open-source skill-chain project for Verilog and SystemVerilog development.

This repository is not building one isolated skill.
It is building a staged skill chain for the full development process.

The first stage is language-first:

- teach the AI how Verilog/SystemVerilog should be written
- define the required language subset and style constraints
- attach an executable syntax-check program to that language contract

## Project Position

This project is for human users working on open-source HDL projects.
It is not an internal Codex-only helper.

The project principle is:

- start from language requirements
- bind every language promise to a real checker
- expand the chain stage by stage instead of claiming full flow support upfront

## Skill-Chain Structure

This repository will be organized as a skill chain rather than a single monolithic skill.

### Stage 1

`verilog-language-and-syntax`

Responsibilities:

- teach the AI how to write the target HDL subset
- define what is required, preferred, discouraged, and forbidden
- explain the compatibility baseline
- run the matching syntax/elaboration checker

This stage is the foundation for all later stages.
If the AI does not first understand the language contract, every downstream step will drift.

Stage-1 documents live in:

- [stages/verilog-language-and-syntax](stages/verilog-language-and-syntax)

### Planned Later Stages

Examples of later chain stages:

- lint and style enforcement
- simulation workflow
- testbench construction
- debug and waveform-oriented diagnosis
- project packaging and delivery

These are not the current first target.

## First Stage Boundary

The first stage should not start from "which simulator do we have".
It should start from "what language is the AI allowed to write".

The current boundary is:

- compatibility baseline: Verilog-2005
- preferred modern subset: RTL-oriented SystemVerilog
- excluded by default: full verification-language SystemVerilog, including UVM/class-based flows

The detailed boundary is documented in [language-support-scope.md](stages/verilog-language-and-syntax/references/language-support-scope.md).

## Checker Principle

Language guidance without executable checking is incomplete.

So the first stage must contain both:

- language requirements
- a runnable syntax-check program

The initial checker direction is:

- optional syntax backend: Verible
- required baseline and elaboration backend: Icarus Verilog
- later stronger cross-check backend: Verilator

The checker exists to enforce the language contract, not to define it by itself.

## Current Next Step

The next concrete output is not a generic all-in-one skill.
It is the first stage specification:

1. language requirements for AI code generation
2. compatibility baseline and excluded constructs
3. syntax-check program contract
4. stage-1 skill definition

## Repository Layout

- [README.md](README.md): project-level entry
- [skill-chain-architecture.md](skill-chain-architecture.md): chain-level structure
- [stages/verilog-language-and-syntax](stages/verilog-language-and-syntax): first skill package
