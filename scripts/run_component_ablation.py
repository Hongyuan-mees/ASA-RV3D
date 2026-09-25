#!/usr/bin/env python3
"""Build component ablation tables for ASA-RV3D experiments.

This script is experiment-facing, not paper text.  It detects available
assignments for:

1. TritonPart
2. ASA-RV3D without timing guard, if present
3. ASA-RV3D with timing-regret guard
4. Path-aware ASA-RV3D

It then evaluates timing-weighted crossing for all available assignments and
joins the existing path-aware downstream vertical-delay summaries when present.
Missing optional ablations are reported rather than fabricated.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def assignment_candidates(design: str, scenario: str) -> dict[str, Path]:
    return {
        "tritonpart": Path("results") / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv",
        "asa_no_timing_guard": (
            Path("results")
            / f"{design}_tritonpart_guarded_repair"
            / scenario
            / "tritonpart_guarded_repair_assignment.csv"
        ),
        "asa_timing_regret": (
            Path("results")
            / f"{design}_tritonpart_timing_regret_guarded_repair"
            / scenario
            / "tritonpart_timing_regret_guarded_repair_assignment.csv"
        ),
        "asa_path_aware": (
            Path("results")
            / f"{design}_tritonpart_path_aware_guarded_repair"
            / scenario
            / "tritonpart_path_aware_guarded_repair_assignment.csv"
        ),
    }


def run_timing_crossing(design: str, scenario: str, assignments: dict[str, Path], force: bool) -> Path | None:
    available = {case: path for case, path in assignments.items() if path.exists()}
    if len(available) < 2:
        return None
    output = Path("results") / "benchmark_summary" / f"{design}_{scenario}_component_ablation_timing_crossing.csv"
    if output.exists() and not force:
        return output
    cmd = [
        sys.executable,
        "evaluation/evaluate_timing_crossing.py",
        "--design",
        design,
        "--features-dir",
        str(Path("results") / f"{design}_features"),
        "--timing",
        str(Path("results") / f"{design}_features" / "timing_context_scores.csv"),
        "--output",
        str(output),
    ]
    for case, path in available.items():
        cmd.extend(["--assignment", f"{case}={path}"])
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    return output


def finite_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    timing_rows: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []
    downstream_rows: list[dict[str, object]] = []

    for design in DESIGNS:
        for scenario in SCENARIOS:
            assignments = assignment_candidates(design, scenario)
            for case, path in assignments.items():
                if not path.exists():
                    missing_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "case": case,
                            "missing_assignment": str(path),
                        }
                    )

            timing_path = run_timing_crossing(design, scenario, assignments, args.force)
            if timing_path and timing_path.exists():
                for row in read_csv(timing_path):
                    timing_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "case": row["case"],
                            "crossing_nets": row["crossing_nets"],
                            "timing_crossing_nets": row["timing_crossing_nets"],
                            "timing_crossing_net_fraction": row["timing_crossing_net_fraction"],
                            "high_timing_crossing_nets": row["high_timing_crossing_nets"],
                            "timing_weighted_crossing": row["timing_weighted_crossing"],
                            "top_timing_crossing_unit": row["top_timing_crossing_unit"],
                            "top_timing_crossing_unit_hits": row["top_timing_crossing_unit_hits"],
                        }
                    )

            downstream_path = Path("results") / "benchmark_summary" / f"{design}_{scenario}_path_aware_downstream_vertical_delay.csv"
            if downstream_path.exists():
                by_case = {row["case"]: row for row in read_csv(downstream_path)}
                for case in ["tritonpart", "asa_rv3d", "path_aware_asa_rv3d"]:
                    if case not in by_case:
                        continue
                    row = by_case[case]
                    downstream_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "case": case,
                            "crossing_path_fraction": row["crossing_path_fraction"],
                            "mean_tier_transitions_per_path": row["mean_tier_transitions_per_path"],
                            "estimated_wns_degradation_ns": row["estimated_wns_degradation_ns"],
                            "estimated_tns_degradation_ns": row["estimated_tns_degradation_ns"],
                            "wns_degradation_reduction_vs_asa_rv3d": row["wns_degradation_reduction_vs_asa_rv3d"],
                            "tns_degradation_reduction_vs_asa_rv3d": row["tns_degradation_reduction_vs_asa_rv3d"],
                        }
                    )

    write_csv(
        Path("results/benchmark_summary/component_ablation_timing_crossing_summary.csv"),
        timing_rows,
        [
            "design",
            "scenario",
            "case",
            "crossing_nets",
            "timing_crossing_nets",
            "timing_crossing_net_fraction",
            "high_timing_crossing_nets",
            "timing_weighted_crossing",
            "top_timing_crossing_unit",
            "top_timing_crossing_unit_hits",
        ],
    )
    write_csv(
        Path("results/benchmark_summary/component_ablation_downstream_summary.csv"),
        downstream_rows,
        [
            "design",
            "scenario",
            "case",
            "crossing_path_fraction",
            "mean_tier_transitions_per_path",
            "estimated_wns_degradation_ns",
            "estimated_tns_degradation_ns",
            "wns_degradation_reduction_vs_asa_rv3d",
            "tns_degradation_reduction_vs_asa_rv3d",
        ],
    )
    write_csv(
        Path("results/benchmark_summary/component_ablation_missing_inputs.csv"),
        missing_rows,
        ["design", "scenario", "case", "missing_assignment"],
    )

    rollup_rows: list[dict[str, object]] = []
    for case in sorted({row["case"] for row in timing_rows}):
        values = [finite_float(row["timing_weighted_crossing"]) for row in timing_rows if row["case"] == case]
        rollup_rows.append(
            {
                "metric_group": "timing_crossing",
                "case": case,
                "available_cases": len(values),
                "mean_timing_weighted_crossing": f"{sum(values) / len(values):.6f}" if values else "",
            }
        )
    for case in sorted({row["case"] for row in downstream_rows}):
        wns = [finite_float(row["estimated_wns_degradation_ns"]) for row in downstream_rows if row["case"] == case]
        tns = [finite_float(row["estimated_tns_degradation_ns"]) for row in downstream_rows if row["case"] == case]
        rollup_rows.append(
            {
                "metric_group": "downstream_vertical_delay",
                "case": case,
                "available_cases": len(wns),
                "mean_timing_weighted_crossing": "",
                "mean_wns_degradation_ns": f"{sum(wns) / len(wns):.6f}" if wns else "",
                "mean_tns_degradation_ns": f"{sum(tns) / len(tns):.6f}" if tns else "",
            }
        )
    write_csv(
        Path("results/benchmark_summary/component_ablation_rollup.csv"),
        rollup_rows,
        [
            "metric_group",
            "case",
            "available_cases",
            "mean_timing_weighted_crossing",
            "mean_wns_degradation_ns",
            "mean_tns_degradation_ns",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
