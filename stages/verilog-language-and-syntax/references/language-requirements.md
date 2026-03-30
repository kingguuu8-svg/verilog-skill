# Language Requirements

## Goal

Define the language contract for stage 1 of the skill chain.

This document tells the AI:

- what language to write by default
- what compatibility target it must preserve
- what constructs it should prefer
- what constructs it should avoid or forbid by default

This is not a pure language summary.
It is an engineering constraint document for AI-generated Verilog/SystemVerilog.

## Main Decision

Stage 1 uses a two-layer language policy:

1. hard compatibility baseline:
   `Verilog-2005`
2. default generation target:
   `RTL-oriented SystemVerilog subset`

This is the central rule for the whole first stage.

## Why This Policy Exists

The collected evidence points to one consistent conclusion:

- the most cross-platform stable common denominator is Verilog-2005
- but pure Verilog-2005 is too restrictive as the default AI generation language for modern RTL work
- a bounded RTL-oriented SystemVerilog subset improves clarity and code quality without inheriting the whole verification-language burden

This matches the main usage scenarios:

- FPGA RTL design
- ASIC/SoC RTL design
- RTL simulation and debug
- simple module-style verification
- open-source educational and reference projects

It also matches the platform evidence:

- Icarus supports Verilog generations through `-g2012`, but documents SystemVerilog support as ongoing
- Verilator supports Verilog/SystemVerilog with explicit supported and limited regions
- Verible parses SystemVerilog and is useful as a source-level checker
- Yosys supports a large Verilog-2005 subset and only a smaller SystemVerilog subset
- Vivado and Quartus support Verilog/SystemVerilog within FPGA-flow-oriented subsets

Therefore the default contract must be narrower than the whole IEEE 1800 language.

## Default Target Language

The AI should default to:

`RTL-oriented SystemVerilog on top of a Verilog-2005 compatibility baseline`

This means:

- generate code that remains close to portable synthesizable RTL
- use modern RTL constructs when they improve clarity
- avoid verification-language-heavy constructs unless the user explicitly asks for them

## Compatibility Rule

When there is any tension between:

- cleaner modern syntax
- and broader tool compatibility

the AI should prefer the version that preserves the Verilog-2005-compatible design intent unless the user explicitly requests a more advanced SystemVerilog feature.

In practice:

- prefer a portable subset over a maximal subset
- prefer predictable synthesis/simulation behavior over expressive but fragile constructs
- prefer constructs widely accepted across FPGA, ASIC, and open-source flows

## Allowed By Default

The AI may generate these constructs by default:

- `module`
- ports with explicit direction and width
- `parameter` and `localparam`
- `generate`
- `if`, `case`, `for`, `while`, `repeat`
- `assign`
- `function`
- `task`
- `wire`
- `logic`
- `reg` only when needed for compatibility with older Verilog-style code or when editing an existing codebase that already uses it heavily
- `always_comb`
- `always_ff`
- `always_latch` only when the intended hardware is truly latch-based
- `typedef`
- `enum`
- `struct`
- packed and unpacked arrays used in ordinary RTL
- simple `package` and `import`
- simple module-style testbench constructs:
  `initial`, clocks, resets, stimulus sequencing, `$display`, `$monitor`, `$finish`, simple self-checking conditions
- standard preprocessor usage:
  `` `include `define `ifdef `ifndef `elsif `endif `timescale `default_nettype `resetall ``

## Preferred Style

The AI should prefer:

- one module per file unless the existing project uses a different established style
- explicit widths
- explicit signedness when relevant
- `logic` instead of unnecessary `wire/reg` splitting in new SystemVerilog RTL
- `always_comb` for combinational logic
- `always_ff` for edge-triggered sequential logic
- `enum` for state encoding when that improves readability
- `localparam` for internal constants
- clear reset behavior
- ASCII-safe source output unless the existing file already uses another encoding intentionally

## Allowed But Discouraged

These constructs may be legal and may even be supported by some tools, but they should not be the AI's default output unless required by the user or by the existing codebase:

- `interface`
- `modport`
- `union`
- `always @*` in new code when `always_comb` is available
- implicit nets
- heavy macro abstraction that hides RTL structure
- deeply nested preprocessor conditionals
- backend-specific pragmas when a portable form exists

## Forbidden By Default

The AI should not generate these by default in stage 1:

- `class`
- `randomize`
- `constraint`
- `covergroup`
- `mailbox`
- `semaphore`
- `program`
- `checker`
- full UVM constructs
- DPI-heavy solutions unless the user explicitly requests them
- vendor-specific HDL extensions as the default path
- mixed-language assumptions such as automatic VHDL interoperability

These are not banned forever across the entire project.
They are banned as the default language contract of stage 1.

## Synthesis-Oriented Rule

When generating design RTL, the AI must assume that the code may later be synthesized even if the immediate task is simulation.

So by default it should avoid:

- simulation-only tricks inside design modules
- timing-delay modeling in design RTL
- constructs that obscure synthesizable intent

If the user explicitly asks for testbench-only code, the AI may use simulation-only constructs there.

## Testbench Rule

Stage 1 includes simple testbench support, but not full verification-language support.

The default testbench style is:

- module-style testbench
- direct DUT instantiation
- explicit clocks and resets
- direct stimulus generation
- simple assertions/checks expressed as ordinary procedural conditions or supported assertion forms when appropriate

The AI should not jump to:

- class-based environments
- UVM agents
- constrained random frameworks

unless the user explicitly asks for that verification style.

## Error Interpretation Rule

When the checker rejects a construct, the AI must distinguish among three cases:

1. illegal by the language contract
2. legal by standard but outside stage-1 default subset
3. acceptable by contract but unsupported or limited in the current backend

These are different outcomes and must not be merged into one generic "syntax error."

## Decision Summary

The stage-1 language contract is:

- compatibility anchor:
  Verilog-2005
- default generated language:
  RTL-oriented SystemVerilog subset
- supported workflow target:
  synthesizable RTL plus simple module-style simulation/testbench work
- excluded default layer:
  full verification-language SystemVerilog

## References

- [official-syntax-sources.md](official-syntax-sources.md)
- [mainstream-platform-language-support.md](mainstream-platform-language-support.md)
- [verilog-main-usage-scenarios.md](verilog-main-usage-scenarios.md)
- [IEEE 1364-2005](https://ieeexplore.ieee.org/document/1620780)
- [IEEE 1800-2023](https://standards.ieee.org/standard/1800-2023.html)
- [Icarus iverilog command line flags](https://steveicarus.github.io/iverilog/usage/command_line_flags.html)
- [Verilator language guide](https://verilator.org/guide/latest/languages.html)
- [Verible documentation](https://chipsalliance.github.io/verible/)
- [Yosys read_verilog](https://yosyshq.readthedocs.io/projects/yosys/en/0.41/cmd/read_verilog.html)
- [Vivado UG900 Logic Simulation](https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_1/ug900-vivado-logic-simulation.pdf)
