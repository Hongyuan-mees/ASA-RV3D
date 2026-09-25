#!/usr/bin/env python3
"""Summarize dynamic constrained ASA Phase-3 across all three scenarios."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import summarize_dynamic_constrained_asa_phase3 as phase3


DEFAULT_DESIGNS = ["picorv32", "riscv32i"]
DEFAULT_SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]


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


def f(row: dict[str, object], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_constrained_asa_phase3_scenario_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_constrained_asa_phase3_scenario_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    rows: list[dict[str, object]] = []
    for design in designs:
        for scenario in scenarios:
            rows.append(phase3.summarize_case(args.root, design, scenario))
    write_csv(args.root / args.summary, rows)

    admissible = [row for row in rows if row.get("status") == "admissible_phase3"]
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "admissible_phase3_cases", "value": len(admissible)},
        {"metric": "designs", "value": ",".join(designs)},
        {"metric": "scenarios", "value": ",".join(scenarios)},
        {
            "metric": "mean_objective_reduction",
            "value": f"{mean([f(row, 'objective_reduction') for row in admissible]):.6f}",
        },
        {
            "metric": "mean_crossing_reduction",
            "value": f"{mean([f(row, 'crossing_reduction') for row in admissible]):.6f}",
        },
        {
            "metric": "mean_timing_weighted_reduction",
            "value": f"{mean([f(row, 'timing_weighted_reduction') for row in admissible]):.6f}",
        },
        {
            "metric": "mean_P_avg_cut_reduction",
            "value": f"{mean([f(row, 'P_avg_cut_reduction') for row in admissible]):.6f}",
        },
        {
            "metric": "max_P_wst_cut_delta",
            "value": f"{max([f(row, 'P_wst_cut_delta') for row in admissible], default=0.0):.6f}",
        },
        {
            "metric": "max_timing_weighted_regret",
            "value": f"{max([f(row, 'timing_weighted_regret') for row in admissible], default=0.0):.6f}",
        },
    ]
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
