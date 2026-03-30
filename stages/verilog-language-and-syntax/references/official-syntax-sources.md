# Official Syntax Sources

## Goal

Define the official and primary sources that stage 1 should use when specifying Verilog/SystemVerilog syntax requirements.

This document does not restate the whole language.
It defines the source hierarchy for deciding what the language contract is.

## Source Hierarchy

The first skill in the chain must separate:

1. language definition
2. tool implementation
3. project policy

These are not the same thing.

### Level 1: Language Standard

These are the primary sources for syntax and semantics.

- IEEE 1364-2005
  `IEEE Standard for Verilog Hardware Description Language`
- IEEE 1800-2023
  `IEEE Standard for SystemVerilog--Unified Hardware Design, Specification, and Verification Language`

Interpretation rule:

- Verilog syntax baseline comes from IEEE 1364-2005
- modern SystemVerilog syntax reference comes from IEEE 1800-2023
- if a construct is legal in the standard but not accepted by the chosen open-source toolchain, that is a tool-support limitation, not an automatic language error

## Why Both Standards Matter

There is an easy mistake here:

- treating `SystemVerilog` as if it completely replaces the need to think about `Verilog`
- or treating `Verilog-2005` as if it is enough for modern open-source RTL work

For this project, both are needed:

- `IEEE 1364-2005` is the compatibility baseline
- `IEEE 1800-2023` is the full language reference for modern syntax

But the first stage of the skill will not expose the entire 1800 language.
It will define a bounded subset on top of the standards.

## Level 2: Official Tool Documentation

These documents do not define the language.
They define what a real backend claims to support and how it is invoked.

### Icarus Verilog

Primary role:

- first syntax/elaboration/simulation backend

Official references:

- Icarus Verilog usage index
- `iverilog` command line flags
- command file format
- `vvp` command line flags

Important implication:

- Icarus officially exposes language generation flags including `-g2005`, `-g2009`, and `-g2012`
- its documentation explicitly says SystemVerilog support exists under those modes, but support is ongoing

This means:

- Icarus can be used as a stage-1 checker
- Icarus must not be treated as the definition of legal SystemVerilog syntax

### Verilator

Primary role:

- later stronger compile/lint-oriented backend

Official reference:

- Verilator language support documentation
- Verilator executable reference

Important implication:

- Verilator documents supported and limited language areas explicitly
- this makes it useful later for narrowing the practical subset, but it still remains an implementation reference, not the language standard itself

### Verible

Primary role:

- parser/lint/format reference implementation for source-level tooling

Official reference:

- Verible project documentation
- `verible-verilog-syntax`

Important implication:

- Verible states that its parser targets SystemVerilog based on IEEE 1800-2017
- this is strong evidence for parser-oriented workflows
- it is still not the normative definition of syntax

## Level 3: Skill Policy

The first skill must add one more layer above the standards and tool docs:

- what the AI is allowed to generate by default
- what the AI should prefer
- what the AI should avoid even if technically legal

This is project policy, not language law.

Examples:

- a construct may be legal in IEEE 1800-2023
- a tool may partially support it
- the skill may still forbid default generation because it hurts open-source portability

## Immediate Decision

Stage 1 should use this rule:

- syntax legality is anchored to IEEE language standards
- practical checking is anchored to official tool documentation
- default AI generation rules are defined by project policy on top of both

## Immediate Working Baseline

Until a narrower project subset is written, use this temporary reading:

- normative Verilog baseline:
  IEEE 1364-2005
- normative modern language reference:
  IEEE 1800-2023
- first practical checker:
  Icarus Verilog in `-g2012` mode
- future parser/lint reference:
  Verible
- future stronger compile/lint cross-check:
  Verilator

## What To Do Next

The next document should not be another list of sources.
It should convert these sources into a stage-1 language contract:

1. default target language
2. required subset
3. discouraged constructs
4. forbidden default constructs
5. checker behavior when syntax is legal but unsupported by the backend

## Official References

- [IEEE 1364-2005](https://ieeexplore.ieee.org/document/1620780)
- [IEEE 1800-2023](https://standards.ieee.org/standard/1800-2023.html)
- [Icarus Verilog documentation](https://steveicarus.github.io/iverilog/)
- [iverilog command line flags](https://steveicarus.github.io/iverilog/usage/command_line_flags.html)
- [Icarus command file format](https://steveicarus.github.io/iverilog/usage/command_files.html)
- [vvp command line flags](https://steveicarus.github.io/iverilog/usage/vvp_flags.html)
- [Verilator language guide](https://verilator.org/guide/latest/languages.html)
- [Verilator executable reference](https://verilator.org/guide/latest/exe_verilator.html)
- [Verible project documentation](https://chipsalliance.github.io/verible/)
- [verible-verilog-syntax](https://chipsalliance.github.io/verible/verilog_syntax.html)
