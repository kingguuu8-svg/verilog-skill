# Language Support Scope

## Goal

Define the language scope for the first public version of this skill.

This skill is for open-source Verilog/SystemVerilog projects and should be described in project terms rather than tool-specific terms.

The current milestone is:

- start from syntax and elaboration checking
- use simulation as the temporary execution target
- avoid claiming full SystemVerilog coverage before the open-source toolchain can actually support it

## Scope Principle

Do not define support by the language name alone.

`SystemVerilog` must be split into two different promises:

1. SystemVerilog design/RTL subset
2. SystemVerilog verification-language subset

For V0, the skill should target the first one and explicitly avoid promising the second one.

## V0 User Promise

V0 supports:

- Verilog RTL projects
- SystemVerilog RTL-style projects
- simple simulation flows built around open-source simulators
- simple self-checking testbenches that stay close to module/task/function/process style coding

V0 does not promise:

- full SystemVerilog verification-language support
- full UVM support
- parity with commercial simulators

## File-Level Scope

In scope:

- `.v`
- `.vh`
- `.sv`
- `.svh`
- file lists such as `.f`

Expected project elements:

- source files
- include files
- optional compile defines
- one or more candidate top modules
- optional testbench entry

## Language Scope

### 1. Clearly Supported In V0

These are the constructs the skill should treat as first-class targets for syntax check and simulation flow support:

- modules
- ports, parameters, localparams
- nets and variables
- continuous assignments
- procedural blocks: `initial`, `always`, `always_comb`, `always_ff`, `always_latch`
- blocking/nonblocking assignments
- `if`, `case`, `for`, `while`, `repeat`, `generate`
- tasks and functions without class-based verification dependencies
- `typedef`, `enum`, `struct`, packed arrays, unpacked arrays used in ordinary RTL/testbench code
- `logic`, `wire`, `reg`, `bit`
- package/import usage common in RTL-style code
- preprocessor flow: `` `include `define `ifdef `ifndef `elsif `endif `timescale `default_nettype `resetall ``

### 2. Best-Effort In V0

These features may be accepted for syntax checking or partial compilation depending on the selected backend, but V0 should not advertise them as guaranteed:

- interfaces and modports
- assertions and immediate/concurrent SVA
- `bind`
- `program`
- `checker`
- DPI-C related declarations
- advanced aggregate typing corner cases
- simulator-specific pragmas

Rule:

If the backend accepts them, the skill may proceed.
If the backend rejects them, the skill should report "outside guaranteed V0 support" rather than pretending the user code is necessarily wrong.

### 3. Explicitly Out Of Scope In V0

These should be declared unsupported at the skill-definition level:

- UVM
- class-based verification environments
- constrained randomization: `class`, `randomize`, `constraint`
- mailboxes, semaphores, process-level advanced verification frameworks
- covergroups and functional coverage workflows
- mixed-language projects such as Verilog + VHDL
- encrypted vendor IP flows
- proprietary simulator-only extensions as a required path
- synthesis, STA, formal verification, equivalence checking

## Standard-Level Promise

The skill should describe its promise this way:

- guaranteed baseline: Verilog-2005 style projects
- primary V0 target: common SystemVerilog RTL/testbench subset compiled in a SystemVerilog-2012 compatible flow
- later syntax-only expansion may cover a broader IEEE 1800 parser range, but that is not part of the V0 guarantee

This wording matters.

Do not say:

- "supports Verilog and SystemVerilog"

Use:

- "supports Verilog-2005 and a practical RTL-oriented SystemVerilog subset for open-source syntax check and simulation"

## Backend Mapping

### Default V0 backend

Use Icarus Verilog plus `vvp` as the first simulation backend.

Why:

- open-source
- easy to automate
- enough to validate the first closed loop:
  syntax -> elaboration -> simulation

### Planned secondary backends

- Verilator:
  stronger lint/compile path, but should be treated as a later expansion target
- Verible:
  parser/lint/format support, useful for syntax and style workflows but not the first simulation backend

## Public Positioning

The first release should be positioned as:

"A skill for open-source Verilog and RTL-oriented SystemVerilog projects, focused on syntax checking, elaboration diagnostics, and simple simulation workflows."

It should not be positioned as:

- a complete HDL IDE replacement
- a full verification methodology skill
- a full SystemVerilog/UVM simulator abstraction layer

## Decision

The V0 language support boundary is:

- support Verilog-2005
- support RTL-oriented SystemVerilog used in open-source projects
- support simple module-style testbenches
- exclude full verification-language SystemVerilog and UVM

This is the narrowest boundary that still matches the current milestone and the realistic capability of an open-source syntax/simulation toolchain.
