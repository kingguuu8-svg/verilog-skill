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

## Stage-2 Definition

The second stage is:

`verilog-simulation-execution`

Its job is not waveform analysis.
Its real job is to execute bounded simulations and preserve the resulting artifacts.

Stage 2 must contain these inseparable parts:

1. simulation compile and runtime execution
2. structured reporting for stdout, stderr, and emitted wave artifacts

## Stage-2 Inputs

Stage 2 should accept:

- source files: `.v`, `.vh`, `.sv`, `.svh`
- optional `.f` file lists
- optional macro definitions
- optional include directories
- optional top-module hint
- optional runtime plusargs
- optional requested wave-file path

## Stage-2 Outputs

Stage 2 should produce:

- compile/elaboration result
- runtime result
- simulator print output
- compiled image path
- log file paths
- wave file paths, including simulator-native artifacts such as `WDB`
- next-action hint

## Stage-2 Execution Contract

The simulation side of stage 2 should:

- reuse the stage-1 compile baseline where practical
- prefer mature external backends over custom simulation engines
- keep a default portable backend and allow optional vendor backends when the design requires them
- keep artifact paths explicit
- distinguish compile failures from runtime failures
- report wave files without analyzing them

## Stage-3 Definition

The third stage is:

`verilog-waveform-observation`

Its job is not debug diagnosis.
Its real job is to make emitted waveform artifacts queryable in bounded text windows.

Stage 3 must contain these inseparable parts:

1. waveform signal selection and window rendering
2. session-style navigation to the next relevant event

## Stage-3 Inputs

Stage 3 should accept:

- waveform file path
- selected signal names
- window length
- optional anchor time

## Stage-3 Outputs

Stage 3 should produce:

- signal catalog when needed
- rendered anchor row
- rendered change rows inside the selected window
- updated anchor time after navigation
- next-action hint when a signal is ambiguous or an edge does not exist

## Stage-3 Observation Contract

The waveform side of stage 3 should:

- reuse stage-2 emitted artifacts instead of re-running simulation by default
- accept VCD directly and treat XSIM WDB as a bounded conversion input, not a new binary parsing project
- print the anchor time even when no signal changes there
- treat rise/fall as single-bit concepts only
- treat vectors as values or value changes
- preserve signal order across every rendered row
- keep navigation state explicit instead of hiding it in a GUI

## Dependency Rule

Later stages depend on stage 1.

Examples:

- lint stage depends on stage-1 language mode
- simulation stage depends on stage-1 compile baseline
- waveform observation stage depends on stage-2 emitted artifacts
- waveform diagnosis stage depends on stage-3 rendered observations or the same raw artifacts
- debug stage depends on stage-1 normalized diagnostics

Therefore stage 1 must be completed first and kept narrow, stage 2 must remain execution-focused, and stage 3 must remain observation-focused.

## Current Build Goal

The current goal is to build the chain in bounded steps:

1. teach the AI the intended Verilog/SystemVerilog subset
2. execute simulations with a real backend
3. observe waveform artifacts without a GUI dependency
4. only later add waveform-oriented diagnosis or richer verification flows

Do not collapse those stages prematurely.
