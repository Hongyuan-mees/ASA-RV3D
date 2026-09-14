# Server Environment Notes

Date: 2026-09-14

This file records a sanitized summary of the initial server environment before installing OpenROAD-flow-scripts or running any EDA flow.

## Server Workspace

Project work must stay under the approved user workspace on the server.

Do not use files already present in the workspace unless their source and purpose are known.

## Disk Status

Initial observation:

- CPU and memory are expected to be sufficient for early experiments.
- Disk space is the limiting resource.
- Avoid running many experiments in parallel.
- Avoid global cleanup commands such as `docker system prune`.
- Keep generated EDA files outside Git tracking.

## Repository Size

The project repository was small at initialization.

## Tool Availability

Docker and Git are available on the server.

## Planned Server Directory Layout

The recommended server-side layout is:

```text
approved-user-workspace/
├── RV3D_Public/           # this project repository
├── openroad-flow-scripts/ # public ORFS checkout, kept outside this repo
├── rv3d_runs/             # generated flow outputs, ignored by Git
└── rv3d_cache/            # optional cache area if needed later
```

Do not clone OpenROAD-flow-scripts into `RV3D_Public/third_party/` during the initial baseline setup.

## Initial Resource Policy

For early ORFS/Ibex experiments:

- use 4 to 8 CPU threads
- run only 1 experiment at a time first
- keep large build output under `rv3d_runs/`
- record public source URLs, licenses, and commit IDs
- remove only project-owned generated directories after confirming their paths
