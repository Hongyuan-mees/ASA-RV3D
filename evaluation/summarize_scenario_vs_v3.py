#!/usr/bin/env python3
"""Compare scenario-aware partitioning against the generic v3-context partition.

This is a Stage-5 mainline experiment.  It asks a focused question:

  Under the same 3D scenario objective, does the scenario-aware partitioner
  improve beyond the earlier v3_context partition?

Inputs expected in the RV3D-Public repository:

  results/<design>_scenario_partition/<scenario>/partition_comparison.csv
  results/benchmark_summary/scenario_cost/*scenario*cost*summary*.csv

Output:

  results/benchmark_summary/scenario_aware_vs_v3_summary.csv
"""

from __future__ import annotations

import csv
from pathlib import Path


DESIGNS = ["ibex", "riscv32i"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
SCENARIO_COST_DIR = Path("results/benchmark_summary/scenario_cost")
OUT = Path("results/benchmark_summary/scenario_aware_vs_v3_summary.csv")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def as_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def find_v3_objective(row: dict[str, str], generic_objective: float) -> float:
    """Find the v3_context objective on the same scale as generic_objective.

    The scenario-cost evaluator has several numeric columns: raw cost, normalized
    cost, reduction ratio, and sometimes auxiliary components.  For this
    comparison we need the raw scenario-cost value.  The safest invariant is
    scale: the v3 raw cost should be positive, below the generic raw objective,
    and in the same order of magnitude.  Tiny normalized columns such as 8.4 or
    50.6 are therefore excluded.
    """

    preferred_raw_columns = [
        "scenario_cost_with_uncertainty",
        "scenario_total_objective",
        "scenario_objective",
        "total_scenario_objective",
        "scenario_total_cost",
        "scenario_total_proxy_cost",
        "weighted_scenario_cost",
        "scenario_cost",
        "riscv_3d_proxy_cost",
        "riscv_3d_scenario_cost",
        "scenario_proxy_cost",
    ]

    lower_bound = generic_objective * 0.05
    upper_bound = generic_objective * 1.05

    for key in preferred_raw_columns:
        value = as_float(row.get(key))
        if value is not None and lower_bound <= value <= upper_bound:
            return value

    candidates: list[float] = []
    for key, raw in row.items():
        low = key.lower()
        if any(skip in low for skip in ["reduction", "ratio", "fraction", "balance", "normalized", "mean"]):
            continue
        value = as_float(raw)
        if value is not None and lower_bound <= value <= upper_bound:
            candidates.append(value)
    if not candidates:
        raise ValueError(
            "Could not find a raw v3_context objective column on the same scale "
            f"as generic_objective={generic_objective:.6f}. Row: {row}"
        )
    return max(candidates)


def load_v3_context_rows() -> dict[tuple[str, str], dict[str, str]]:
    paths = sorted(SCENARIO_COST_DIR.glob("*.csv"))
    if not paths:
        raise FileNotFoundError(f"No CSV files found in {SCENARIO_COST_DIR}")

    values: dict[tuple[str, str], dict[str, str]] = {}
    for path in paths:
        try:
            rows = read_csv(path)
        except Exception:
            continue
        for row in rows:
            design = row.get("design", "")
            scenario = row.get("scenario", "")
            case = row.get("case") or row.get("strategy") or row.get("method") or row.get("assignment")
            # Skip per-architecture-unit breakdown rows.  They contain small
            # component costs such as execute_alu=8.42, not total objectives.
            if row.get("architecture_unit"):
                continue
            if design in DESIGNS and scenario in SCENARIOS and case == "v3_context":
                values[(design, scenario)] = row

    missing = [(d, s) for d in DESIGNS for s in SCENARIOS if (d, s) not in values]
    if missing:
        raise RuntimeError(
            "Missing v3_context scenario objectives for: "
            + ", ".join(f"{design}/{scenario}" for design, scenario in missing)
        )
    return values


def load_partition_rows(design: str, scenario: str) -> dict[str, dict[str, str]]:
    path = Path("results") / f"{design}_scenario_partition" / scenario / "partition_comparison.csv"
    rows = read_csv(path)
    return {row["strategy"]: row for row in rows}


def main() -> int:
    v3_rows = load_v3_context_rows()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "design",
        "scenario",
        "generic_objective",
        "v3_context_objective",
        "scenario_aware_objective",
        "v3_context_reduction_vs_generic",
        "scenario_aware_reduction_vs_generic",
        "scenario_aware_reduction_vs_v3_context",
        "scenario_aware_crossing_connections_proxy",
        "scenario_aware_crossing_connection_fraction",
        "scenario_aware_instance_balance_ratio",
        "scenario_aware_weight_balance_ratio",
    ]

    out_rows: list[dict[str, str]] = []
    for design in DESIGNS:
        for scenario in SCENARIOS:
            rows = load_partition_rows(design, scenario)
            generic = rows["generic_balance"]
            scenario_aware = rows["scenario_aware"]

            generic_obj = float(generic["scenario_objective"])
            aware_obj = float(scenario_aware["scenario_objective"])
            v3_obj = find_v3_objective(v3_rows[(design, scenario)], generic_obj)

            out_rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "generic_objective": f"{generic_obj:.6f}",
                    "v3_context_objective": f"{v3_obj:.6f}",
                    "scenario_aware_objective": f"{aware_obj:.6f}",
                    "v3_context_reduction_vs_generic": f"{(generic_obj - v3_obj) / generic_obj:.6f}",
                    "scenario_aware_reduction_vs_generic": f"{(generic_obj - aware_obj) / generic_obj:.6f}",
                    "scenario_aware_reduction_vs_v3_context": f"{(v3_obj - aware_obj) / v3_obj:.6f}",
                    "scenario_aware_crossing_connections_proxy": scenario_aware["crossing_connections_proxy"],
                    "scenario_aware_crossing_connection_fraction": scenario_aware["crossing_connection_fraction"],
                    "scenario_aware_instance_balance_ratio": scenario_aware["instance_balance_ratio"],
                    "scenario_aware_weight_balance_ratio": scenario_aware["weight_balance_ratio"],
                }
            )

    tmp = OUT.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(out_rows)
    tmp.replace(OUT)

    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
