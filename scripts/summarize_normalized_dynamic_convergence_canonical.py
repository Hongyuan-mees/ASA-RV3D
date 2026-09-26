#!/usr/bin/env python3
"""Summarize canonical metrics for normalized dynamic convergence runs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_DESIGNS = ["picorv32", "riscv32i", "scr1_core_tuned"]
DEFAULT_SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]

NATIVE = "native_timing_aware"
ON = "normalized_convergence_architecture_on"
OFF = "normalized_convergence_architecture_off"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def f(row: dict[str, object] | dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def by_case(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["case"]: row for row in rows if row.get("case")}


def pct_reduction(before: float, after: float) -> float:
    return (before - after) / before if before else 0.0


def load_case(root: Path, design: str, scenario: str) -> dict[str, object]:
    prefix = f"{design}_{scenario}_normalized_dynamic_convergence"
    timing = by_case(read_rows(root / "results" / "benchmark_summary" / f"{prefix}_timing_crossing.csv"))
    path = by_case(read_rows(root / "results" / "benchmark_summary" / f"{prefix}_path_cuts.csv"))
    structural_rows = read_rows(root / "results" / "benchmark_summary" / f"{prefix}_structural_rollup.csv")

    required_cases = [NATIVE, ON, OFF]
    missing = []
    for case in required_cases:
        if case not in timing:
            missing.append(f"timing:{case}")
        if case not in path:
            missing.append(f"path:{case}")
    structural = structural_rows[0] if structural_rows else {}
    if not structural:
        missing.append("structural_rollup")

    row: dict[str, object] = {
        "design": design,
        "scenario": scenario,
        "status": "missing_input" if missing else "canonical_compared",
        "missing": ";".join(missing),
    }
    if missing:
        return row

    native_timing = timing[NATIVE]
    on_timing = timing[ON]
    off_timing = timing[OFF]
    native_path = path[NATIVE]
    on_path = path[ON]
    off_path = path[OFF]

    row.update(
        {
            "native_crossing_nets": native_timing["crossing_nets"],
            "on_crossing_nets": on_timing["crossing_nets"],
            "off_crossing_nets": off_timing["crossing_nets"],
            "on_crossing_reduction_vs_native": f"{pct_reduction(f(native_timing, 'crossing_nets'), f(on_timing, 'crossing_nets')):.6f}",
            "off_crossing_reduction_vs_native": f"{pct_reduction(f(native_timing, 'crossing_nets'), f(off_timing, 'crossing_nets')):.6f}",
            "on_minus_off_crossing_nets": f"{f(on_timing, 'crossing_nets') - f(off_timing, 'crossing_nets'):.0f}",
            "native_timing_weighted_crossing": native_timing["timing_weighted_crossing"],
            "on_timing_weighted_crossing": on_timing["timing_weighted_crossing"],
            "off_timing_weighted_crossing": off_timing["timing_weighted_crossing"],
            "on_timing_weighted_reduction_vs_native": f"{pct_reduction(f(native_timing, 'timing_weighted_crossing'), f(on_timing, 'timing_weighted_crossing')):.6f}",
            "off_timing_weighted_reduction_vs_native": f"{pct_reduction(f(native_timing, 'timing_weighted_crossing'), f(off_timing, 'timing_weighted_crossing')):.6f}",
            "on_minus_off_timing_weighted_crossing": f"{f(on_timing, 'timing_weighted_crossing') - f(off_timing, 'timing_weighted_crossing'):.6f}",
            "native_timing_crossing_nets": native_timing["timing_crossing_nets"],
            "on_timing_crossing_nets": on_timing["timing_crossing_nets"],
            "off_timing_crossing_nets": off_timing["timing_crossing_nets"],
            "on_minus_off_timing_crossing_nets": f"{f(on_timing, 'timing_crossing_nets') - f(off_timing, 'timing_crossing_nets'):.0f}",
            "native_P_avg_cut": native_path["P_avg_cut"],
            "on_P_avg_cut": on_path["P_avg_cut"],
            "off_P_avg_cut": off_path["P_avg_cut"],
            "on_P_avg_cut_regret": f"{(f(on_path, 'P_avg_cut') - f(native_path, 'P_avg_cut')) / f(native_path, 'P_avg_cut') if f(native_path, 'P_avg_cut') else 0.0:.6f}",
            "off_P_avg_cut_regret": f"{(f(off_path, 'P_avg_cut') - f(native_path, 'P_avg_cut')) / f(native_path, 'P_avg_cut') if f(native_path, 'P_avg_cut') else 0.0:.6f}",
            "native_P_wst_cut": native_path["P_wst_cut"],
            "on_P_wst_cut": on_path["P_wst_cut"],
            "off_P_wst_cut": off_path["P_wst_cut"],
            "on_P_wst_cut_delta": f"{f(on_path, 'P_wst_cut') - f(native_path, 'P_wst_cut'):.6f}",
            "off_P_wst_cut_delta": f"{f(off_path, 'P_wst_cut') - f(native_path, 'P_wst_cut'):.6f}",
            "native_structural_sensitive_crossing_nets": structural["native_scenario_sensitive_crossing_nets"],
            "on_structural_sensitive_crossing_nets": structural["architecture_on_scenario_sensitive_crossing_nets"],
            "off_structural_sensitive_crossing_nets": structural["architecture_off_scenario_sensitive_crossing_nets"],
            "on_structural_reduction_vs_native": structural["architecture_on_reduction_vs_native"],
            "on_structural_reduction_vs_off": structural["architecture_on_reduction_vs_off"],
            "architecture_on_better_structural_than_off": structural["architecture_on_better_than_off"],
        }
    )
    return row


def count(rows: list[dict[str, object]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_convergence_canonical_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_convergence_canonical_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    rows = [load_case(args.root, design, scenario) for design in designs for scenario in scenarios]
    write_csv(args.root / args.summary, rows)

    compared = [row for row in rows if row.get("status") == "canonical_compared"]
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "canonical_compared_cases", "value": len(compared)},
        {"metric": "designs", "value": ",".join(designs)},
        {"metric": "scenarios", "value": ",".join(scenarios)},
        {
            "metric": "mean_on_crossing_reduction_vs_native",
            "value": f"{mean([f(row, 'on_crossing_reduction_vs_native') for row in compared]):.6f}",
        },
        {
            "metric": "mean_off_crossing_reduction_vs_native",
            "value": f"{mean([f(row, 'off_crossing_reduction_vs_native') for row in compared]):.6f}",
        },
        {
            "metric": "mean_on_timing_weighted_reduction_vs_native",
            "value": f"{mean([f(row, 'on_timing_weighted_reduction_vs_native') for row in compared]):.6f}",
        },
        {
            "metric": "mean_off_timing_weighted_reduction_vs_native",
            "value": f"{mean([f(row, 'off_timing_weighted_reduction_vs_native') for row in compared]):.6f}",
        },
        {
            "metric": "mean_on_structural_reduction_vs_native",
            "value": f"{mean([f(row, 'on_structural_reduction_vs_native') for row in compared]):.6f}",
        },
        {
            "metric": "mean_on_structural_reduction_vs_off",
            "value": f"{mean([f(row, 'on_structural_reduction_vs_off') for row in compared]):.6f}",
        },
        {
            "metric": "architecture_on_better_structural_than_off_cases",
            "value": count(compared, "architecture_on_better_structural_than_off", "true"),
        },
        {
            "metric": "architecture_off_better_or_equal_structural_cases",
            "value": len(compared) - count(compared, "architecture_on_better_structural_than_off", "true"),
        },
        {
            "metric": "max_on_P_avg_cut_regret",
            "value": f"{max([f(row, 'on_P_avg_cut_regret') for row in compared], default=0.0):.6f}",
        },
        {
            "metric": "max_on_P_wst_cut_delta",
            "value": f"{max([f(row, 'on_P_wst_cut_delta') for row in compared], default=0.0):.6f}",
        },
    ]
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
