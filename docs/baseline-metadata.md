# Baseline Metadata

Date: 2026-09-14

This file records public-source metadata for the first Ibex + ORFS baseline.

No private lab source code, private data, private scripts, or private results are used.

## OpenROAD-flow-scripts

- Project: OpenROAD-flow-scripts
- Upstream: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts
- Local checkout method: shallow clone with recursive shallow submodules
- Checked-out commit:

```text
5e8b1450d19263f797a27c4f371b9dd19f32a3aa
```

- Branch status observed after clone:

```text
master...origin/master
```

- Checkout size observed after clone:

```text
4.1G
```

## Ibex Design Snapshot In ORFS

- ORFS design nickname: `ibex`
- ORFS top design name: `ibex_core`
- ORFS platform: `sky130hd`
- ORFS config path: `flow/designs/sky130hd/ibex/config.mk`
- ORFS RTL source path: `flow/designs/src/ibex_sv/`
- ORFS frontend setting: `SYNTH_HDL_FRONTEND = slang`
- ORFS hierarchical setting: `OPENROAD_HIERARCHICAL = 1`

Relevant `config.mk` entries:

```make
export DESIGN_NICKNAME = ibex
export DESIGN_NAME = ibex_core
export PLATFORM    = sky130hd
export VERILOG_FILES = $(sort $(wildcard $(DESIGN_HOME)/src/ibex_sv/*.sv)) \
$(DESIGN_HOME)/src/ibex_sv/syn/rtl/prim_clock_gating.v
export VERILOG_INCLUDE_DIRS = \
$(DESIGN_HOME)/src/ibex_sv/vendor/lowrisc_ip/prim/rtl/
export SYNTH_HDL_FRONTEND = slang
export SDC_FILE = $(DESIGN_HOME)/$(PLATFORM)/$(DESIGN_NICKNAME)/constraint.sdc
export OPENROAD_HIERARCHICAL = 1
```

## Ibex Upstream Source

The ORFS Ibex snapshot README states:

- Ibex is a small 32-bit RISC-V CPU core.
- ISA family: `RV32IMC/EMC`
- Pipeline: two-stage
- Upstream project: https://github.com/lowRISC/ibex
- Upstream commit used by the ORFS snapshot:

```text
77d801001554cce8fe69e742e96539eecbe74425
```

ORFS notes the following modifications to its Ibex snapshot:

- default configuration from the upstream repository
- source files pruned to the used subset
- most files moved to the top source directory
- timing constraints added
- LICENSE added

## Ibex Source Files Observed

The ORFS Ibex source snapshot includes RISC-V microarchitecture-relevant modules such as:

- `ibex_alu.sv`
- `ibex_compressed_decoder.sv`
- `ibex_controller.sv`
- `ibex_core.sv`
- `ibex_decoder.sv`
- `ibex_ex_block.sv`
- `ibex_id_stage.sv`
- `ibex_if_stage.sv`
- `ibex_load_store_unit.sv`
- `ibex_multdiv_fast.sv`
- `ibex_multdiv_slow.sv`
- `ibex_register_file_ff.sv`
- `ibex_wb_stage.sv`

These public module names are good initial anchors for the later architecture-aware classifier.

## Ibex sky130hd Config Directory

The ORFS Ibex sky130hd config directory contains:

```text
autotuner.json
config.mk
constraint_doe.sdc
constraint.sdc
fastroute.tcl
rules-base.json
```

## Immediate Next Step

Before running the flow:

- inspect the official ORFS Docker workflow
- confirm whether a prebuilt Docker image can be used
- avoid source-building OpenROAD unless necessary
- keep the first run limited to the official Ibex baseline
- record the exact run command and generated report locations
