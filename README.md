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

### Stage 2

`verilog-simulation-execution`

Responsibilities:

- compile and elaborate module-style simulations
- run testbenches with an existing mature backend
- capture simulator print output
- collect emitted waveform file paths, including `VCD` and `WDB`

This stage intentionally stops before waveform analysis.

Stage-2 documents live in:

- [stages/verilog-simulation-execution](stages/verilog-simulation-execution)

### Stage 3

`verilog-waveform-observation`

Responsibilities:

- load emitted VCD waveform artifacts
- list canonical signal names
- render anchor-based observation windows as text
- navigate to the next selected edge or value change
- keep an optional interactive observation session alive in the terminal

This stage intentionally stops before waveform diagnosis.

Stage-3 documents live in:

- [stages/verilog-waveform-observation](stages/verilog-waveform-observation)

### Planned Later Stages

Examples of later chain stages:

- lint and style enforcement
- testbench construction
- waveform-oriented diagnosis
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

## Current Chain State

The current concrete outputs are:

1. stage-1 language and syntax enforcement
2. stage-2 simulation execution
3. stage-3 waveform observation

Current stage-2 backend split:

- default portable path: `iverilog` + `vvp`
- optional vendor path: Vivado `xvlog` + `xelab` + `xsim`

The next likely bounded stage after this is waveform-oriented diagnosis, not a larger simulation monolith.

## Repository Layout

- [README.md](README.md): project-level entry
- [skill-chain-architecture.md](skill-chain-architecture.md): chain-level structure
- [stages/verilog-language-and-syntax](stages/verilog-language-and-syntax): first skill package
- [stages/verilog-simulation-execution](stages/verilog-simulation-execution): second skill package
- [stages/verilog-waveform-observation](stages/verilog-waveform-observation): third skill package
