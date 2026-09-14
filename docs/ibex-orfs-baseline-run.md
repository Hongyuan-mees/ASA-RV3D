# Ibex ORFS Baseline Run

This note records the first public-resource Ibex baseline run used by the RV3D project.

## Environment

- Cloud instance: Aliyun ECS `rv3d-orfs-hk`
- OS: Ubuntu 22.04 64-bit
- Compute: 8 vCPU, 32 GiB RAM
- ORFS checkout: `~/openroad-flow-scripts`
- Docker image: `openroad/orfs:latest`
- Image digest observed: `sha256:ee88641037a1c8e3403203bdca2b6256bf44a7957fa26719c8463ba638d76f9d`
- OpenROAD version observed in log: `26Q3-2056-g41a28926b9`

## Command

```bash
cd ~/openroad-flow-scripts/flow
time util/docker_shell make DESIGN_CONFIG=./designs/sky130hd/ibex/config.mk
```

## Design

- Design nickname: `ibex`
- Top module: `ibex_core`
- Platform: `sky130hd`
- HDL frontend: `slang`
- Source: ORFS bundled Ibex SystemVerilog sources, derived from lowRISC Ibex commit `77d801001554cce8fe69e742e96539eecbe74425`

## Outcome And Data Quality

Status: clean baseline.

The initial run reached final artifact generation but failed in the final report step because OpenROAD tried to initialize the Qt GUI in a headless environment.

The final reporting stage was rerun with Qt's offscreen platform:

```bash
cd ~/openroad-flow-scripts/flow
time util/docker_shell env QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software make DESIGN_CONFIG=./designs/sky130hd/ibex/config.mk
```

This rerun completed the final report and GDS generation without the previous `GUI-0077` / stack-trace failure.

Observed final artifacts on the cloud server:

| File | Size |
| --- | ---: |
| `results/sky130hd/ibex/base/6_final.def` | 19M |
| `results/sky130hd/ibex/base/6_final.gds` | 21M |
| `results/sky130hd/ibex/base/6_final.odb` | 35M |
| `results/sky130hd/ibex/base/6_final.sdc` | 28K |
| `results/sky130hd/ibex/base/6_final.spef` | 21M |
| `results/sky130hd/ibex/base/6_final.v` | 1.9M |

These raw artifacts are intentionally not tracked in Git because they are generated and comparatively large.

## Metrics

From `reports/sky130hd/ibex/base/6_finish.rpt` and `logs/sky130hd/ibex/base/6_report.log`:

| Metric | Value |
| --- | ---: |
| TNS max | -1.19 |
| WNS max | -0.07 |
| Worst slack max | -0.07 |
| `core_clock` minimum period | 10.07 ns |
| `core_clock` fmax | 99.35 MHz |
| `vclk_core_clock` minimum period | 9.42 ns |
| `vclk_core_clock` fmax | 106.20 MHz |
| Design area | 154127 um^2 |
| Utilization | 60% |
| VDD total power | 4.86e-02 W |
| VDD worst IR drop | 5.75e-04 V |
| VSS total power | 4.86e-02 W |
| VSS worst IR drop | 4.75e-04 V |
| Route DRC report lines | 0 |

Cell-type summary from the final report:

| Cell category | Count | Area |
| --- | ---: | ---: |
| Fill cell | 22027 | 102799.84 |
| Tap cell | 3384 | 4234.06 |
| Antenna cell | 78 | 195.19 |
| Clock buffer | 215 | 5108.65 |
| Timing repair buffer | 1382 | 11928.94 |
| Inverter | 222 | 833.30 |
| Clock inverter | 144 | 1712.89 |
| Sequential cell | 1939 | 49894.10 |
| Multi-input combinational cell | 12052 | 80219.44 |
| Total | 41443 | 256926.41 |

## Notes

- `reports/sky130hd/ibex/base/5_route_drc.rpt` was present and empty, so the recorded route DRC report line count is zero.
- The earlier `6_report` failure was a headless GUI reporting issue, not an implementation-stage failure. The clean rerun used `QT_QPA_PLATFORM=offscreen`.
- The top-level `synth_stat.txt` summary was not fully captured in the pasted terminal output; rerun a targeted grep before recording top-level synthesis cell/wire totals.
