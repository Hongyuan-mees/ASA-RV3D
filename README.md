# RV3D-Public

RV3D-Public is a clean, public-resource-only research project for a RISC-V competition.

The working goal is to use an open RISC-V processor as the real design object and study architecture-aware EDA methods for 2-tier 3D logic partitioning / tier assignment.

Current focus:

- Processor target: lowRISC Ibex
- Baseline flow: OpenROAD-flow-scripts, OpenROAD, Yosys
- Initial technology target: sky130hd
- MVP task: compare generic 2-way partitioning with RISC-V architecture-aware 2-tier partitioning

This repository is initially private on GitHub, but the project must only use public resources and self-written code.

## Project Boundary

This repository must stay fully separated from private lab projects.

Do not add:

- private lab source code
- private lab data, reports, screenshots, or experiment results
- private PDK files
- private scripts copied or adapted from lab repositories
- symbolic links to lab projects
- generated EDA build directories or large intermediate artifacts

Allowed materials:

- public open-source code and tools
- public datasets and public benchmark designs
- code written specifically for this project
- results regenerated from public resources by this project

If a file's source is unclear, do not use it.

## Planned Workflow

Phase 0: project initialization

- create the clean repository structure
- verify Windows local development and GitHub synchronization
- verify server-side `git pull` synchronization only under the approved user workspace

Phase 1: public baseline

- run the official Ibex + sky130hd flow in OpenROAD-flow-scripts
- record tool versions, source commits, and reproduction steps

Phase 2: data extraction

- collect synthesized netlist and hierarchy information
- collect physical-design outputs that are available from the public flow
- collect timing information if the public flow is stable enough

Phase 3: generic partition baseline

- study OpenROAD Partition Manager / TritonPart
- produce a reproducible generic 2-way partition result

Phase 4: architecture-aware method

- classify gate-level instances by public Ibex module hierarchy
- generate RISC-V architecture-aware grouping, weights, or constraints
- call a generic public partition backend

Phase 5: evaluation

- compare generic and architecture-aware partitioning
- report proxy metrics such as area balance, cut nets, estimated inter-tier connections, HPWL-related metrics, timing if available, and runtime

## Development Workflow

This project uses a mixed local/server workflow.

Windows local machine:

- write and edit project code
- update documentation
- commit changes with Git
- push changes to the GitHub private repository
- analyze returned experiment logs and summarized results

GitHub private repository:

- acts as the single official project repository
- synchronizes code between the Windows local machine and the server
- stores source code, configs, scripts, documentation, summary CSV files, and final figures

Server:

- pulls code from GitHub
- runs Docker, OpenROAD-flow-scripts, OpenROAD, Yosys, and other heavy EDA tasks
- stores large generated build outputs outside Git tracking
- returns only non-sensitive logs, errors, and summarized public-resource results for local analysis

Expected loop:

```text
Windows local edit
-> git commit
-> git push
-> server git pull
-> server run experiment
-> copy non-sensitive result summary or error message back to local analysis
```

Current verified setup:

- Windows local repository is stored on a non-system data drive.
- Server repository is stored under the approved user workspace.

## Server Safety Rules

On the server, this project must stay under the approved user workspace.

Do not operate outside that workspace for project setup, cleanup, or experiments.

Do not run global cleanup commands such as:

```bash
docker system prune
```

Initial server experiments should be small and resource-limited:

- use about 4 to 8 CPU threads
- run only 1 to 2 experiments at a time
- avoid filling the shared server data filesystem, which has limited free space
- keep large EDA intermediates out of Git

## Repository Layout

```text
RV3D-Public/
├── classifier/   # module and instance classification
├── partition/    # partition policy generation and backend wrappers
├── evaluation/   # metric extraction and comparison scripts
├── scripts/      # reproducibility and utility scripts
├── configs/      # experiment configuration files
├── results/      # tracked summaries and final figures only
├── docs/         # notes, project reports, and design documentation
├── third_party/  # dependency notes, submodules, or lightweight manifests
└── work/         # local scratch space, ignored by Git
```

## Dependency Policy

Large third-party projects should not be copied into this repository by default.

Preferred approaches:

- clone public repositories separately
- use Git submodules only when there is a clear reason
- record exact commit IDs and licenses
- use Docker or documented installation steps for reproducibility

## Current Status

Project initialization is complete.

OpenROAD-flow-scripts and Ibex have not been installed or run yet.

The Phase 1 ORFS baseline preparation plan is documented in `docs/phase1-orfs-plan.md`.
