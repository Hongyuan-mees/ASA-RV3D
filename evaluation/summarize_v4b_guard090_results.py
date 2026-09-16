#!/usr/bin/env python3
"""Summarize guarded physical-context partition results.

This is the compact audit table for the final v4b/guard090 candidate. It reads
the per-scenario partition outputs and compares only two rows:

  - scenario_aware: the previous scenario-aware baseline
  - physical_guarded: the final guarded physical-context result

The table is intentionally small. It is meant to answer whether v4b improves
the final objective without hiding balance regressions.
"""

from __future__ import annotations

import csv
from pathlib import Path


DESIGNS = ("ibex", "riscv32i")
SCENARIOS = (
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def ff(row: dict[str, str], key: str) -> float:
    return float(row[key])


def main() -> int:
    rows: list[dict[str, object]] = []
    for design in DESIGNS:
        for scenario in SCENARIOS:
            path = (
                Path("results")
                / f"{design}_partition_v4b_physical_guard090"
                / scenario
                / "partition_comparison.csv"
            )
            data = {row["strategy"]: row for row in read_csv(path)}
            baseline = data["scenario_aware"]
            guarded = data["physical_guarded"]

            base_obj = ff(baseline, "physical_augmented_objective")
            guarded_obj = ff(guarded, "physical_augmented_objective")
            base_cross = ff(baseline, "crossing_connections_proxy")
            guarded_cross = ff(guarded, "crossing_connections_proxy")
            base_phys = ff(baseline, "physical_context_crossing_penalty")
            guarded_phys = ff(guarded, "physical_context_crossing_penalty")

            rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "baseline_crossing_proxy": int(base_cross),
                    "guarded_crossing_proxy": int(guarded_cross),
                    "crossing_delta": int(guarded_cross - base_cross),
                    "baseline_physical_penalty": f"{base_phys:.6f}",
                    "guarded_physical_penalty": f"{guarded_phys:.6f}",
                    "physical_penalty_delta": f"{guarded_phys - base_phys:.6f}",
                    "baseline_augmented_objective": f"{base_obj:.6f}",
                    "guarded_augmented_objective": f"{guarded_obj:.6f}",
                    "objective_delta": f"{guarded_obj - base_obj:.6f}",
                    "objective_reduction_vs_baseline": f"{(base_obj - guarded_obj) / base_obj if base_obj else 0.0:.6f}",
                    "guarded_instance_balance": guarded["instance_balance_ratio"],
                    "guarded_weight_balance": guarded["weight_balance_ratio"],
                    "guarded_reduction_vs_generic": guarded["reduction_vs_generic_physical_augmented_objective"],
                    "guarded_improves_baseline": int(guarded_obj <= base_obj),
                }
            )

    out = Path("results/benchmark_summary/v4b_guard090_summary.csv")
    fields = [
        "design",
        "scenario",
        "baseline_crossing_proxy",
        "guarded_crossing_proxy",
        "crossing_delta",
        "baseline_physical_penalty",
        "guarded_physical_penalty",
        "physical_penalty_delta",
        "baseline_augmented_objective",
        "guarded_augmented_objective",
        "objective_delta",
        "objective_reduction_vs_baseline",
        "guarded_instance_balance",
        "guarded_weight_balance",
        "guarded_reduction_vs_generic",
        "guarded_improves_baseline",
    ]
    write_csv(out, rows, fields)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
