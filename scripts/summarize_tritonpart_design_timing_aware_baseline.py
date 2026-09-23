#!/usr/bin/env python3
"""Summarize OpenROAD triton_part_design timing-aware baseline evidence.

This script collects the native OpenROAD TritonPart timing-aware smoke/import
results into paper-facing CSVs. It intentionally separates two questions:

1. Did the native timing-aware baseline run?
2. If imported into RV3D's instance space, how does its timing-crossing proxy
   compare with the existing TritonPart hypergraph baseline and ASA-RV3D?
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]


def read_status(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def read_crossing_rows(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {row["case"]: row for row in csv.DictReader(f)}


def pct_change(new_value: float, old_value: float) -> float:
    if old_value == 0:
        return 0.0
    return (old_value - new_value) / old_value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--orfs-flow-dir",
        type=Path,
        default=Path.home() / "openroad-flow-scripts" / "flow",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path(
            "results/benchmark_summary/tritonpart_design_timing_aware_baseline_summary.csv"
        ),
    )
    parser.add_argument(
        "--output-rollup",
        type=Path,
        default=Path(
            "results/benchmark_summary/tritonpart_design_timing_aware_baseline_rollup.csv"
        ),
    )
    args = parser.parse_args()

    rows: list[dict[str, str]] = []
    feasible_cases = 0
    comparable_cases = 0
    native_better_than_hypergraph = 0
    native_better_than_asa = 0

    for design in DESIGNS:
        status_path = (
            args.orfs_flow_dir
            / "rv3d_tritonpart_design_timing_aware_smoke"
            / design
            / "timing_top1"
            / "status.txt"
        )
        status = read_status(status_path)

        crossing_path = Path(
            f"results/benchmark_summary/{design}_tritonpart_design_timing_aware_crossing.csv"
        )
        crossing = read_crossing_rows(crossing_path)

        manifest_path = Path(f"results/{design}_tritonpart_design_timing_aware/manifest.json")
        manifest = {}
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        run_status = "not_run"
        if status:
            if status.get("return_code") == "0" and status.get("solution_exists") == "true":
                run_status = "ran"
                feasible_cases += 1
            else:
                run_status = "failed"

        hyper = crossing.get("tritonpart_hypergraph")
        native = crossing.get("tritonpart_design_timing_aware")
        asa = crossing.get("asa_rv3d")

        if hyper and native and asa:
            comparable_cases += 1
            hyper_tw = float(hyper["timing_weighted_crossing"])
            native_tw = float(native["timing_weighted_crossing"])
            asa_tw = float(asa["timing_weighted_crossing"])
            native_vs_hyper = pct_change(native_tw, hyper_tw)
            native_vs_asa = pct_change(native_tw, asa_tw)
            if native_tw < hyper_tw:
                native_better_than_hypergraph += 1
            if native_tw < asa_tw:
                native_better_than_asa += 1
        else:
            hyper_tw = native_tw = asa_tw = ""
            native_vs_hyper = native_vs_asa = ""

        rows.append(
            {
                "design": design,
                "native_timing_aware_status": run_status,
                "return_code": status.get("return_code", ""),
                "solution_rows": status.get("solution_line_count", ""),
                "import_reference_rows": str(manifest.get("reference_rows", "")),
                "import_fallback_rows": str(manifest.get("fallback_rows", "")),
                "tritonpart_hypergraph_timing_weighted_crossing": str(hyper_tw),
                "tritonpart_design_timing_aware_timing_weighted_crossing": str(native_tw),
                "asa_rv3d_timing_weighted_crossing": str(asa_tw),
                "native_reduction_vs_hypergraph": (
                    f"{native_vs_hyper:.6f}" if native_vs_hyper != "" else ""
                ),
                "native_reduction_vs_asa": (
                    f"{native_vs_asa:.6f}" if native_vs_asa != "" else ""
                ),
                "crossing_csv": str(crossing_path) if crossing_path.exists() else "",
                "manifest": str(manifest_path) if manifest_path.exists() else "",
                "status_file": str(status_path) if status_path.exists() else "",
            }
        )

    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.output_summary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    rollup = [
        {"metric": "designs", "value": ",".join(DESIGNS)},
        {"metric": "native_timing_aware_feasible_cases", "value": str(feasible_cases)},
        {"metric": "native_timing_aware_comparable_cases", "value": str(comparable_cases)},
        {
            "metric": "native_better_than_hypergraph_timing_weighted_cases",
            "value": str(native_better_than_hypergraph),
        },
        {
            "metric": "native_better_than_asa_timing_weighted_cases",
            "value": str(native_better_than_asa),
        },
    ]
    with args.output_rollup.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rollup)

    print(args.output_summary)
    print(args.output_rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
