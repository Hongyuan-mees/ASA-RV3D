#!/usr/bin/env python3
"""Run a scenario-transfer test for ASA-RV3D.

This Stage-5 experiment asks whether scenario-aware partitions are genuinely
scenario-specific:

  If an assignment optimized for scenario A is evaluated under scenario B, does
  it lose to the assignment optimized directly for scenario B?

The script reuses the existing scenario cost model from evaluate_scenario_cost.py
and evaluates the same assignment set under every 3D scenario.

Outputs:

  results/benchmark_summary/scenario_transfer_matrix.csv
  results/benchmark_summary/scenario_transfer_best_summary.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "evaluation") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "evaluation"))

from evaluate_scenario_cost import evaluate, load_design, parse_scenarios  # noqa: E402


DESIGNS = ["ibex", "riscv32i"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
FEATURES = {
    "ibex": Path("results/ibex_features"),
    "riscv32i": Path("results/riscv32i_features"),
}
OUT_DIR = Path("results/benchmark_summary")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def assignment_set(design: str) -> list[tuple[str, Path]]:
    base = Path("results") / f"{design}_scenario_partition"
    return [
        (
            "generic",
            base / "control_datapath_split" / "generic_balance_assignment.csv",
        ),
        (
            "v3_context",
            Path("results") / f"{design}_partition_v3_context" / "architecture_score_v2_assignment.csv",
        ),
        (
            "scenario_control_datapath_split",
            base / "control_datapath_split" / "scenario_aware_assignment.csv",
        ),
        (
            "scenario_memory_near_logic",
            base / "memory_near_logic" / "scenario_aware_assignment.csv",
        ),
        (
            "scenario_state_and_clock_protected",
            base / "state_and_clock_protected" / "scenario_aware_assignment.csv",
        ),
    ]


def optimized_for(case: str) -> str:
    prefix = "scenario_"
    if case.startswith(prefix):
        return case[len(prefix) :]
    return "none"


def crossing_fraction(row: dict[str, object]) -> str:
    if row.get("crossing_connection_fraction") not in (None, ""):
        return str(row["crossing_connection_fraction"])
    crossing = float(row.get("crossing_connections_proxy", 0) or 0)
    total = float(row.get("total_net_connections", 0) or 0)
    return f"{(crossing / total) if total else 0.0:.6f}"


def main() -> int:
    scenarios = parse_scenarios(Path("configs/3d_integration_scenarios.yaml"))
    matrix_rows: list[dict[str, object]] = []
    best_rows: list[dict[str, object]] = []

    for design in DESIGNS:
        instances, net_to_instances = load_design(FEATURES[design])
        assignments = assignment_set(design)

        for scenario_name in SCENARIOS:
            evaluated: list[dict[str, object]] = []
            for case, assignment_path in assignments:
                if not assignment_path.exists():
                    raise FileNotFoundError(assignment_path)
                summary, _ = evaluate(
                    design,
                    scenario_name,
                    scenarios[scenario_name],
                    case,
                    assignment_path,
                    instances,
                    net_to_instances,
                )
                evaluated.append(summary)

            best = min(evaluated, key=lambda row: float(row["scenario_objective"]))
            best_obj = float(best["scenario_objective"])
            own_case = f"scenario_{scenario_name}"
            own = next(row for row in evaluated if row["case"] == own_case)
            v3 = next(row for row in evaluated if row["case"] == "v3_context")
            generic = next(row for row in evaluated if row["case"] == "generic")

            for row in evaluated:
                objective = float(row["scenario_objective"])
                matrix_rows.append(
                    {
                        "design": design,
                        "evaluation_scenario": scenario_name,
                        "assignment_case": row["case"],
                        "assignment_optimized_for": optimized_for(str(row["case"])),
                        "scenario_objective": f"{objective:.6f}",
                        "objective_ratio_vs_best": f"{objective / best_obj:.6f}",
                        "objective_gap_vs_best": f"{objective - best_obj:.6f}",
                        "is_best": "1" if row["case"] == best["case"] else "0",
                        "crossing_connections_proxy": row["crossing_connections_proxy"],
                        "crossing_connection_fraction": crossing_fraction(row),
                        "instance_balance_ratio": row["instance_balance_ratio"],
                        "weight_balance_ratio": row["weight_balance_ratio"],
                    }
                )

            own_obj = float(own["scenario_objective"])
            v3_obj = float(v3["scenario_objective"])
            generic_obj = float(generic["scenario_objective"])
            best_rows.append(
                {
                    "design": design,
                    "evaluation_scenario": scenario_name,
                    "best_assignment_case": best["case"],
                    "own_scenario_assignment_case": own_case,
                    "best_objective": f"{best_obj:.6f}",
                    "own_scenario_objective": f"{own_obj:.6f}",
                    "v3_context_objective": f"{v3_obj:.6f}",
                    "generic_objective": f"{generic_obj:.6f}",
                    "own_is_best": "1" if own["case"] == best["case"] else "0",
                    "own_gap_vs_best": f"{own_obj - best_obj:.6f}",
                    "own_reduction_vs_v3_context": f"{(v3_obj - own_obj) / v3_obj:.6f}",
                    "own_reduction_vs_generic": f"{(generic_obj - own_obj) / generic_obj:.6f}",
                }
            )

    matrix_fields = [
        "design",
        "evaluation_scenario",
        "assignment_case",
        "assignment_optimized_for",
        "scenario_objective",
        "objective_ratio_vs_best",
        "objective_gap_vs_best",
        "is_best",
        "crossing_connections_proxy",
        "crossing_connection_fraction",
        "instance_balance_ratio",
        "weight_balance_ratio",
    ]
    best_fields = [
        "design",
        "evaluation_scenario",
        "best_assignment_case",
        "own_scenario_assignment_case",
        "best_objective",
        "own_scenario_objective",
        "v3_context_objective",
        "generic_objective",
        "own_is_best",
        "own_gap_vs_best",
        "own_reduction_vs_v3_context",
        "own_reduction_vs_generic",
    ]

    matrix_path = OUT_DIR / "scenario_transfer_matrix.csv"
    best_path = OUT_DIR / "scenario_transfer_best_summary.csv"
    write_csv(matrix_path, matrix_rows, matrix_fields)
    write_csv(best_path, best_rows, best_fields)
    print(matrix_path)
    print(best_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
