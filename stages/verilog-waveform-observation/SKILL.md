---
name: verilog-waveform-observation
description: Observe emitted Verilog/SystemVerilog waveform artifacts as structured text windows. Use when Codex needs to inspect VCD files or XSIM WDB artifacts, list signal names, render selected signal values and rise/fall events over a time window, navigate to the next edge, or keep an interactive waveform observation session without opening a GUI waveform viewer.
---

# Verilog Waveform Observation

Use this skill as the third stage of the `verilog-skill` chain.

Do not blur waveform observation with debug conclusions.
This stage reads waveform artifacts and renders text windows.
It does not explain why the waveform is wrong unless the user separately asks for diagnosis.

## Core Rule

Apply this stage only after a waveform artifact already exists, usually from stage 2.

Prefer the narrowest observation path that can answer:

1. which signals should be observed
2. what values they hold at the anchor time
3. what changes happen inside the observation window
4. where the next relevant edge occurs

## What This Skill Does

- load a VCD waveform artifact
- load an XSIM-emitted WDB artifact by reusing a companion VCD or replaying the adjacent snapshot
- list available signal names
- render one observation window as text
- mark single-bit `rise` and `fall` events
- mark vector and unknown transitions as `value_change old->new`
- keep a reusable observation session for repeated navigation
- provide an optional interactive shell for humans

## Workflow

### 1. Confirm Stage Boundary

Read [references/observation-contract.md](references/observation-contract.md) first.

Keep this stage limited to:

- waveform artifact loading
- textual window rendering
- event-oriented navigation

Do not expand into waveform diagnosis here.

### 2. Reuse Earlier Stages

Read [../verilog-simulation-execution/SKILL.md](../verilog-simulation-execution/SKILL.md) when the wave artifact still needs to be generated.

Stage 3 depends on stage 2 for:

- emitted wave artifacts
- deterministic output directories
- simulation logs that explain how the wave was produced

### 3. Prepare The Observation Environment

Read [references/environment-setup.md](references/environment-setup.md) when you need to:

- confirm supported wave formats
- locate the temp session directory
- understand why a waveform cannot be opened

### 4. Use The Observation Interface

Read [references/interaction-usage.md](references/interaction-usage.md) before running or extending the observation scripts.

Use the scripts in [scripts/](scripts/) for executable stage-3 work:

- `scripts/observe_waveform.py`
- `scripts/wave_session.py`
- `scripts/wave_shell.py`
- `scripts/validate_skill.py`

## Observation Rules

When rendering waveform windows:

- always print the anchor position even if no signal changes there
- then print later rows only when at least one selected signal changes
- treat `rise` and `fall` as single-bit concepts
- treat vectors as value observations or `value_change`
- keep the user-selected signal order stable in every row
- prefer hierarchical signal names when short names are ambiguous

## Backend Direction

The current waveform input is:

- supported file format:
  `VCD`
- conditionally supported vendor artifact:
  `WDB` from XSIM output directories

WDB support stays bounded by these rules:

- prefer a same-directory companion `*.vcd` when it already exists
- otherwise replay the adjacent `xsim.dir/<snapshot>` once to export a cached temporary VCD
- do not parse the binary WDB format directly in stage 3

Later support for FST/LXT can be added only when the repository has a portable parsing or conversion path.

## Output Expectation

When using this skill, produce conclusions in this order:

1. what waveform file was observed
2. what signal set and window were used
3. the rendered rows
4. what next edge or next action is available
