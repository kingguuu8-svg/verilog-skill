# Mainstream Platform Language Support

## Goal

Organize the language support situation of mainstream Verilog/SystemVerilog platforms from the viewpoint of this project.

This document is not trying to rank tools.
It is trying to answer:

- which language each platform officially claims to handle
- how strong that support is
- whether the platform is suitable for stage 1 of the skill chain

## Reading Rule

Do not read "supports SystemVerilog" as one undifferentiated statement.

For this project, each platform must be interpreted on three separate axes:

1. is it a language parser or a real compile/sim backend
2. does it target Verilog baseline, RTL-style SystemVerilog, or full verification-oriented SystemVerilog
3. is the support broad, partial, or explicitly subset-based

## Summary Matrix

| Platform | Platform Type | Official Language Position | Project Interpretation | Stage-1 Role |
| --- | --- | --- | --- | --- |
| Icarus Verilog | compiler + simulator | supports `-g1995`, `-g2001`, `-g2005`, `-g2009`, `-g2012`; docs say 2009/2012 include SystemVerilog and support is ongoing | practical open-source compile/sim baseline; good for Verilog and bounded RTL-style SystemVerilog; not a promise of full SystemVerilog verification-language coverage | primary first backend |
| Verilator | compiler/lint/simulation code generator | reads Verilog and SystemVerilog; docs are organized around supported, limited, and unsupported language areas | stronger compile/lint reference than Icarus for many projects, but still not full-language parity with commercial simulators | secondary cross-check backend |
| Verible | parser/lint/format toolchain | parser targets SystemVerilog based on IEEE 1800-2017 | strong parser/lint/format reference, but not a simulator and not a compile backend | source-level syntax/style stage |
| Yosys | synthesis/formal frontend | docs say `read_verilog` supports a large subset of Verilog-2005 and `-sv` enables only a small subset of SystemVerilog | useful for synthesis-oriented subset checking, not a general simulation-language authority | later synthesis-oriented stage, not stage 1 baseline |
| AMD Vivado / xsim | FPGA vendor design suite + simulator | UG900 says Vivado simulator supports a subset of SystemVerilog; `.v` defaults to Verilog-2001, `.sv` to SystemVerilog; `xvlog -sv` enables SystemVerilog parsing, and UG900 includes a table for the synthesizable set of SystemVerilog 1800-2012 plus supported testbench features | important mainstream FPGA-platform reference; stronger than pure synthesis-only tools for vendor flows, but still subset-based and vendor-oriented rather than a neutral language baseline | vendor compatibility target; later practical backend for FPGA users |
| Siemens Questa | commercial simulator | product materials describe broad SystemVerilog/UVM verification support | treat as commercial full-feature reference class, but public docs are not granular enough for our subset definition | external compatibility target, not initial baseline |
| Synopsys VCS | commercial simulator | product materials describe broad SystemVerilog and native testbench support | same as above: broad commercial reference, but not the first public open-source baseline for this project | external compatibility target |
| Cadence Xcelium | commercial simulator | product materials describe support for SystemVerilog, UVM, mixed-signal, low power, and related verification flows | same as above: broad commercial reference, but too broad to use as first-stage language contract | external compatibility target |

## Platform Notes

### 1. Icarus Verilog

Official language generations exposed by `iverilog`:

- `-g1995`
- `-g2001`
- `-g2005`
- `-g2009`
- `-g2012`

Important official wording:

- `-g2009` enables IEEE 1800-2009, which includes SystemVerilog
- `-g2012` enables IEEE 1800-2012, which includes SystemVerilog
- documentation also says actual SystemVerilog support is ongoing

Project conclusion:

- use Icarus as the first practical checker for stage 1
- define the skill subset more narrowly than the full IEEE 1800 language
- never equate "Icarus rejects this" with "the syntax is illegal by standard"

### 2. Verilator

Official position:

- Verilator reads Verilog and SystemVerilog
- its language guide documents supported, limited, and unsupported areas
- it is a compiler-oriented flow, not a classic interpreted simulator

Project conclusion:

- good as a stronger language/compile cross-check
- useful later when we want a stricter practical subset
- still not the normative language definition

### 3. Verible

Official position:

- Verible's main mission is parsing SystemVerilog
- `verible-verilog-syntax` defaults to SystemVerilog-2017 parsing modes

Project conclusion:

- excellent parser and style/lint anchor
- very useful for the "teach AI how to write the language" stage
- but it does not replace a compile/elaboration backend

### 4. Yosys

Official position:

- `read_verilog` supports a large subset of Verilog-2005
- `-sv` enables only a small subset of SystemVerilog
- documentation lists many supported SystemVerilog features, but still as a subset

Project conclusion:

- important later if the chain grows into synthesis or formal-oriented checks
- not suitable as the main stage-1 authority for general Verilog/SystemVerilog development syntax

### 5. Commercial Simulators: Questa / VCS / Xcelium

Official public position:

- vendor pages describe broad SystemVerilog and UVM support
- Xcelium public materials also explicitly describe SystemVerilog, UVM, and mixed-signal support
- VCS public materials describe broad SystemVerilog and native testbench support
- Siemens materials publicly emphasize SystemVerilog/UVM workflows across the Questa family

Project conclusion:

- these tools represent the broad commercial reference class
- they are useful as later portability targets
- but their public-facing pages are not a good starting point for writing a precise open-source-first language contract

### 5. AMD Vivado / xsim

Official position from UG900:

- Vivado simulator supports a subset of SystemVerilog
- `.v` files default to Verilog-2001 syntax
- `.sv` files default to SystemVerilog syntax
- `xvlog -sv` enables SystemVerilog parsing for command-line flows
- UG900 includes a table for the synthesizable set of SystemVerilog 1800-2012
- UG900 also documents supported testbench features, UVM support, DPI support, and SystemC support

Project conclusion:

- Vivado absolutely belongs in the mainstream platform list
- it is especially relevant for FPGA-user workflows
- but it still should not define the first-stage language contract, because its own official wording is subset-based and vendor-flow-oriented
- better role:
  later vendor compatibility target and optional backend for FPGA-oriented branches of the chain

### 6. Commercial Simulators: Questa / VCS / Xcelium

## Main Decision For This Project

If the goal is to build the first skill in a public open-source skill chain, the correct interpretation is:

- normative syntax source:
  IEEE language standards
- first practical compile/sim backend:
  Icarus Verilog
- first strong parser/lint companion:
  Verible
- later stronger compile cross-check:
  Verilator
- later synthesis/formal subset path:
  Yosys
- later FPGA vendor-platform target:
  Vivado / xsim
- later portability target class:
  Questa / VCS / Xcelium

## What This Means For Stage 1

Stage 1 should not claim:

- "full SystemVerilog support"
- "compatible with all mainstream simulators"

Stage 1 should claim:

- Verilog-2005 baseline
- RTL-oriented SystemVerilog subset
- syntax/elaboration checking on open-source toolchains
- explicit room for later vendor-oriented paths such as Vivado
- explicit distinction between:
  standard-legal syntax,
  supported-by-backend syntax,
  and skill-approved default syntax

## References

- [Icarus Verilog documentation](https://steveicarus.github.io/iverilog/)
- [iverilog command line flags](https://steveicarus.github.io/iverilog/usage/command_line_flags.html)
- [Verilator overview](https://verilator.org/guide/latest/overview.html)
- [Verilator language guide](https://verilator.org/guide/latest/languages.html)
- [Verible documentation](https://chipsalliance.github.io/verible/)
- [verible-verilog-syntax](https://chipsalliance.github.io/verible/verilog_syntax.html)
- [Yosys read_verilog frontend](https://yosyshq.readthedocs.io/projects/yosys/en/latest/cmd/index_frontends.html)
- [Yosys notes on Verilog support](https://yosyshq.readthedocs.io/projects/yosys/en/v0.49/yosys_internals/verilog.html)
- [Vivado Design Suite User Guide: Logic Simulation (UG900)](https://www.xilinx.com/support/documents/sw_manuals/xilinx2022_1/ug900-vivado-logic-simulation.pdf)
- [Synopsys VCS](https://www.synopsys.com/zh-cn/verification/simulation/vcs.html)
- [Cadence Xcelium](https://www.cadence.com/en_US/home/company/newsroom/press-releases/pr/2020/cadence-delivers-machine-learning-optimized-xcelium-logic-simula.html)
- [Siemens Questa ADMS](https://eda.sw.siemens.com/en-US/ic/questa/adms/)
