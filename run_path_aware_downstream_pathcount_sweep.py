#!/usr/bin/env python3
"""Run max-path-count sensitivity for path-aware downstream validation.

The path-aware assignments are generated with the existing repair flow.  This
script re-evaluates the downstream fixed vertical-delay proxy using different
numbers of OpenSTA max paths, checking whether the conclusion depends on the
top-100 path cutoff.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
DEFAULT_PATH_COUNTS = [50, 100, 200]


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


def finite_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def output_for(design: str, scenario: str, max_paths: int, delay: float) -> Path:
    delay_tag = str(delay).replace(".", "p")
    return (
        Path("results")
        / "benchmark_summary"
        / f"{design}_{scenario}_path_aware_downstream_maxpaths_{max_paths}_delay_{delay_tag}.csv"
    )


def run_case(design: str, scenario: str, max_paths: int, delay: float, force: bool) -> Path:
    output = output_for(design, scenario, max_paths, delay)
    if output.exists() and not force:
        return output
    cmd = [
        sys.executable,
        "evaluation/evaluate_path_aware_downstream_vertical_delay.py",
        "--design",
        design,
        "--scenario",
        scenario,
        "--max-paths",
        str(max_paths),
        "--vertical-delay-ns",
        str(delay),
        "--output",
        str(output),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-paths", type=int, action="append", help="Path count cutoff. Can be repeated.")
    parser.add_argument("--vertical-delay-ns", type=float, default=0.05)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path_counts = args.max_paths or DEFAULT_PATH_COUNTS

    summary_rows: list[dict[str, object]] = []
    rollup_rows: list[dict[str, object]] = []

    for max_paths in path_counts:
        group_rows: list[dict[str, object]] = []
        for design in DESIGNS:
            for scenario in SCENARIOS:
                path = run_case(design, scenario, max_paths, args.vertical_delay_ns, args.force)
                rows = read_csv(path)
                by_case = {row["case"]: row for row in rows}
                tri = by_case["tritonpart"]
                asa = by_case["asa_rv3d"]
                paw = by_case["path_aware_asa_rv3d"]
                out_row = {
                    "max_paths": max_paths,
                    "vertical_delay_ns": f"{args.vertical_delay_ns:.6f}",
                    "design": design,
                    "scenario": scenario,
                    "tritonpart_wns_degradation": tri["estimated_wns_degradation_ns"],
                    "asa_rv3d_wns_degradation": asa["estimated_wns_degradation_ns"],
                    "path_aware_wns_degradation": paw["estimated_wns_degradation_ns"],
                    "tritonpart_tns_degradation": tri["estimated_tns_degradation_ns"],
                    "asa_rv3d_tns_degradation": asa["estimated_tns_degradation_ns"],
                    "path_aware_tns_degradation": paw["estimated_tns_degradation_ns"],
                    "tritonpart_crossing_path_fraction": tri["crossing_path_fraction"],
                    "asa_rv3d_crossing_path_fraction": asa["crossing_path_fraction"],
                    "path_aware_crossing_path_fraction": paw["crossing_path_fraction"],
                    "path_aware_wns_reduction_vs_asa": paw["wns_degradation_reduction_vs_asa_rv3d"],
                    "path_aware_tns_reduction_vs_asa": paw["tns_degradation_reduction_vs_asa_rv3d"],
                }
                summary_rows.append(out_row)
                group_rows.append(out_row)

        positive_wns = sum(finite_float(row["path_aware_wns_reduction_vs_asa"]) > 0 for row in group_rows)
        positive_tns = sum(finite_float(row["path_aware_tns_reduction_vs_asa"]) > 0 for row in group_rows)
        mean_wns = sum(finite_float(row["path_aware_wns_reduction_vs_asa"]) for row in group_rows) / len(group_rows)
        mean_tns = sum(finite_float(row["path_aware_tns_reduction_vs_asa"]) for row in group_rows) / len(group_rows)
        mean_path = sum(finite_float(row["path_aware_crossing_path_fraction"]) for row in group_rows) / len(group_rows)
        rollup_rows.append(
            {
                "max_paths": max_paths,
                "vertical_delay_ns": f"{args.vertical_delay_ns:.6f}",
                "cases": len(group_rows),
                "positive_wns_reduction_vs_asa_cases": positive_wns,
                "positive_tns_reduction_vs_asa_cases": positive_tns,
                "mean_wns_reduction_vs_asa": f"{mean_wns:.6f}",
                "mean_tns_reduction_vs_asa": f"{mean_tns:.6f}",
                "mean_path_aware_crossing_path_fraction": f"{mean_path:.6f}",
            }
        )

    write_csv(
        Path("results/benchmark_summary/path_aware_downstream_pathcount_sweep_summary.csv"),
        summary_rows,
        [
            "max_paths",
            "vertical_delay_ns",
            "design",
            "scenario",
            "tritonpart_wns_degradation",
            "asa_rv3d_wns_degradation",
            "path_aware_wns_degradation",
            "tritonpart_tns_degradation",
            "asa_rv3d_tns_degradation",
            "path_aware_tns_degradation",
            "tritonpart_crossing_path_fraction",
            "asa_rv3d_crossing_path_fraction",
            "path_aware_crossing_path_fraction",
            "path_aware_wns_reduction_vs_asa",
            "path_aware_tns_reduction_vs_asa",
        ],
    )
    write_csv(
        Path("results/benchmark_summary/path_aware_downstream_pathcount_sweep_rollup.csv"),
        rollup_rows,
        [
            "max_paths",
            "vertical_delay_ns",
            "cases",
            "positive_wns_reduction_vs_asa_cases",
            "positive_tns_reduction_vs_asa_cases",
            "mean_wns_reduction_vs_asa",
            "mean_tns_reduction_vs_asa",
            "mean_path_aware_crossing_path_fraction",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
