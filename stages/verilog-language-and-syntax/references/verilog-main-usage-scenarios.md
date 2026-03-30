# Verilog Main Usage Scenarios

## Goal

Look at Verilog and SystemVerilog from the viewpoint of real usage scenarios instead of only from the viewpoint of platforms.

This matters because the first skill in the chain should not start from:

- one simulator
- one synthesis tool
- one vendor flow

It should start from:

- what people actually use Verilog/SystemVerilog for
- which language subset each scenario really needs

## Main Conclusion

Verilog is not used in one single way.
Its mainstream usage today is spread across several different scenarios:

1. FPGA RTL design
2. ASIC/SoC RTL design
3. RTL simulation and debug
4. verification-oriented testbench work
5. synthesis handoff and implementation-oriented coding
6. IP integration and mixed project assembly
7. education, examples, and open-source reference projects

For this project, the first skill should target the intersection of the first four scenarios, but only the RTL-oriented part of verification.

That means:

- include FPGA
- include ASIC-style RTL coding
- include simulation-oriented testbenches
- exclude full UVM/class-based verification as a default requirement

## Scenario Matrix

| Scenario | Why Verilog/SystemVerilog Is Used | Typical Tool Class | Language Need | Relevance To Stage 1 |
| --- | --- | --- | --- | --- |
| FPGA RTL design | describe synthesizable hardware for FPGA compilation, fitting, timing closure, and board bring-up | Vivado, Quartus, vendor simulators, open-source simulators | synthesizable Verilog/SystemVerilog subset | very high |
| ASIC/SoC RTL design | describe synthesizable RTL for standard-cell synthesis, simulation, and signoff flows | Design Compiler class tools, commercial simulators | synthesizable Verilog plus common RTL SystemVerilog | very high |
| RTL simulation and debug | validate module behavior before or alongside synthesis | Icarus, Verilator, Questa, VCS, Xcelium, xsim | Verilog/SystemVerilog RTL + simple testbench constructs | very high |
| verification-oriented testbench work | drive DUT, check results, build reusable verification environments | Questa, VCS, Xcelium | ranges from simple module testbench to full SystemVerilog verification language | medium, but bounded |
| synthesis-oriented implementation handoff | ensure source code maps predictably into hardware | Vivado, Quartus, Synopsys synthesis flows, Yosys | strict synthesizable subset and tool-friendly coding style | very high |
| IP integration and project assembly | connect RTL, generated IP, simulation libraries, and wrappers | Vivado IP Integrator, Quartus IP flows, mixed-language simulators | portable module/package/interface usage with backend constraints | high |
| education and open-source reference work | teach RTL concepts and publish reusable example projects | Icarus, Verilator, Verible, Yosys, vendor free editions | simple, portable, readable Verilog/SystemVerilog | high |

## Scenario Details

### 1. FPGA RTL Design

This is one of the main modern use cases.

Official vendor material supports this directly:

- AMD Vivado says it supports design entry in traditional HDL such as Verilog and provides synthesis and implementation for FPGA and adaptive SoC devices
- Altera Quartus support pages say the integrated synthesis tool supports Verilog and SystemVerilog

What this means:

- FPGA is not a side case
- it is one of the central reasons Verilog remains widely used

Language implication:

- stage 1 must support synthesizable RTL coding patterns
- stage 1 should favor portable RTL constructs over aggressive language features

### 2. ASIC/SoC RTL Design

This is the other central use case.

Official Synopsys material positions Design Compiler as the core of RTL synthesis.
That tells us the language is used not only for simulation, but as the primary hardware design input to implementation flows.

Language implication:

- synthesizable coding style matters as much as parser legality
- the skill must teach constructs that are predictable under synthesis

### 3. RTL Simulation And Debug

Verilog is also a simulation language in everyday practice.

Intel documentation explicitly describes RTL simulation in Verilog HDL or SystemVerilog and instructs users to compile design files and simulation models in a simulator.
AMD Vivado documentation and UG900 also place simulation directly in the design flow.

Language implication:

- stage 1 must not stop at "synthesis-safe RTL"
- it must also define a simple simulation-friendly subset
- syntax checking should reach at least elaboration, not just token parsing

### 4. Verification-Oriented Testbench Work

This is where confusion usually starts.

SystemVerilog is heavily used for verification, but that use spans a very wide range:

- simple module-style testbenches
- self-checking benches
- assertions
- constrained random
- class/UVM environments

Commercial simulator pages emphasize this broad side of the language.
But this does not mean the first skill in this chain should inherit all of it.

Language implication:

- stage 1 should include simple testbench and checking patterns
- stage 1 should not default to full verification-language SystemVerilog

### 5. Synthesis Handoff And Implementation-Oriented Coding

Many real projects use Verilog not just as "code that compiles", but as code that must map correctly into hardware.

Vendor documentation repeatedly exposes HDL templates, synthesis recommendations, and supported construct lists.

Language implication:

- "standard legal" is not enough
- stage 1 needs coding rules that prefer tool-stable synthesis behavior

### 6. IP Integration And Project Assembly

Real projects often combine:

- handwritten RTL
- vendor IP
- generated wrappers
- simulation libraries
- file lists and include trees

This is especially visible in Vivado and Quartus flows.

Language implication:

- stage 1 should include rules for file extensions, packages, include usage, top-module selection, and project assembly hygiene

### 7. Education And Open-Source Reference Projects

This is especially relevant to this repository.

Open-source projects and teaching flows often prefer:

- readable RTL
- portable syntax
- minimal backend assumptions
- examples that run on open-source tools

Language implication:

- the default generated subset should be smaller and cleaner than the whole standard
- readability and portability should be first-class constraints

## What This Means For The Skill Chain

The skill chain should not be optimized around one extreme.

It should not start from:

- pure FPGA vendor syntax habits only
- pure UVM verification flows only
- pure ASIC enterprise flows only

It should start from the common core shared by the main usage scenarios:

- synthesizable RTL
- portable modern Verilog/SystemVerilog subset
- simple simulation-oriented testbench support

## Stage-1 Decision

So for stage 1, the most defensible scope is:

- primary target scenarios:
  FPGA RTL design,
  ASIC/SoC RTL design,
  RTL simulation and debug,
  simple verification-oriented testbench work
- non-primary scenarios:
  full UVM/class-based verification,
  AMS,
  mixed-language enterprise verification,
  advanced vendor-specific flows

## Why This Is Better Than A Platform-Only View

A platform-only view can mislead us into asking:

- "Should Vivado define the language?"
- "Should Icarus define the language?"

But the real question is:

- "What language subset survives across the main real usage scenarios?"

That answer is stronger:

- Verilog-2005 compatibility baseline
- modern RTL-oriented SystemVerilog subset
- simple testbench support
- explicit exclusion of the heavy verification-language layer by default

## References

- [AMD Vivado Design Entry & Implementation](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/implementation.html)
- [Vivado Logic Simulation User Guide UG900](https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_1/ug900-vivado-logic-simulation.pdf)
- [Altera Quartus Design Software Support Center](https://www.altera.com/design/guidance/software/quartus-support)
- [Intel Quartus HDL Support](https://www.intel.com/content/www/us/en/docs/programmable/683080/22-1/hdl-support.html)
- [Synopsys Design Compiler](https://www.synopsys.com/Tools/Implementation/RTLSynthesis/DesignCompiler/Pages/default.aspx)
- [Questa Altera FPGA Edition](https://www.altera.com/products/development-tools/quartus-prime/questa)
