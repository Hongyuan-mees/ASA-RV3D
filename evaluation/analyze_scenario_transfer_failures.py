#!/usr/bin/env python3
"""Analyze why some scenario-transfer cases are not own-scenario best.

This script follows the Stage-5 mainline:

  scenario-aware partitioning
  -> scenario transfer test
  -> explain the non-own-best cases

It compares the own-scenario assignment against the best assignment under each
evaluation scenario, then reports:

  1. objective/crossing/balance gaps,
  2. architecture-unit cost deltas,
  3. tier differences grouped by architecture unit.

Outputs:

  results/benchmark_summary/scenario_transfer_failure_analysis.csv
  results/benchmark_summary/scenario_transfer_failure_unit_cost_delta.csv
  results/benchmark_summary/scenario_transfer_failure_tier_delta.csv
"""

from __future__ import annotations

import csv
import sys
from collections import Counter, defaultdict
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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def assignment_path(design: str, case: str) -> Path:
    if case == "generic":
        return Path("results") / f"{design}_scenario_partition" / "control_datapath_split" / "generic_balance_assignment.csv"
    if case == "v3_context":
        return Path("results") / f"{design}_partition_v3_context" / "architecture_score_v2_assignment.csv"
    prefix = "scenario_"
    if case.startswith(prefix):
        scenario = case[len(prefix) :]
        return Path("results") / f"{design}_scenario_partition" / scenario / "scenario_aware_assignment.csv"
    raise ValueError(f"Unknown assignment case: {case}")


def load_assignment(path: Path) -> dict[str, str]:
    return {row["instance"]: row["tier"] for row in read_csv(path)}


def load_instance_units(features_dir: Path) -> dict[str, str]:
    candidates = [
        features_dir / "architecture_mapping_instances.csv",
        features_dir / "architecture_instance_classes.csv",
        features_dir / "instance_features.csv",
    ]
    for path in candidates:
        if not path.exists():
            continue
        rows = read_csv(path)
        if not rows:
            continue
        sample = rows[0]
        instance_key = "instance" if "instance" in sample else "name" if "name" in sample else None
        unit_key = (
            "architecture_unit"
            if "architecture_unit" in sample
            else "architecture_class"
            if "architecture_class" in sample
            else "top_arch_class"
            if "top_arch_class" in sample
            else None
        )
        if instance_key and unit_key:
            return {row[instance_key]: row[unit_key] for row in rows if row.get(instance_key)}
    raise FileNotFoundError(f"Could not find instance-to-architecture mapping in {features_dir}")


def evaluate_case(
    design: str,
    scenario: str,
    case: str,
    scenarios: dict[str, dict[str, dict[str, float]]],
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    path = assignment_path(design, case)
    if not path.exists():
        raise FileNotFoundError(path)
    return evaluate(design, scenario, scenarios[scenario], case, path, instances, net_to_instances)


def index_best_summary() -> dict[tuple[str, str], dict[str, str]]:
    path = OUT_DIR / "scenario_transfer_best_summary.csv"
    rows = read_csv(path)
    return {(row["design"], row["evaluation_scenario"]): row for row in rows}


def unit_cost_map(rows: list[dict[str, object]]) -> dict[str, float]:
    out = {}
    for row in rows:
        unit = str(row["architecture_unit"])
        out[unit] = float(row["scenario_proxy_cost"])
    return out


def main() -> int:
    scenarios = parse_scenarios(Path("configs/3d_integration_scenarios.yaml"))
    best_summary = index_best_summary()

    analysis_rows: list[dict[str, object]] = []
    unit_delta_rows: list[dict[str, object]] = []
    tier_delta_rows: list[dict[str, object]] = []

    for design in DESIGNS:
        instances, net_to_instances = load_design(FEATURES[design])
        instance_units = load_instance_units(FEATURES[design])

        for scenario in SCENARIOS:
            summary = best_summary[(design, scenario)]
            own_case = summary["own_scenario_assignment_case"]
            best_case = summary["best_assignment_case"]
            if own_case == best_case:
                continue

            own_summary, own_units = evaluate_case(design, scenario, own_case, scenarios, instances, net_to_instances)
            best_eval, best_units = evaluate_case(design, scenario, best_case, scenarios, instances, net_to_instances)

            own_obj = float(own_summary["scenario_objective"])
            best_obj = float(best_eval["scenario_objective"])
            own_cross = float(own_summary["crossing_connections_proxy"])
            best_cross = float(best_eval["crossing_connections_proxy"])
            own_bal = float(own_summary["instance_balance_ratio"])
            best_bal = float(best_eval["instance_balance_ratio"])
            own_wbal = float(own_summary["weight_balance_ratio"])
            best_wbal = float(best_eval["weight_balance_ratio"])

            analysis_rows.append(
                {
                    "design": design,
                    "evaluation_scenario": scenario,
                    "best_assignment_case": best_case,
                    "own_assignment_case": own_case,
                    "objective_gap": f"{own_obj - best_obj:.6f}",
                    "objective_gap_fraction": f"{(own_obj - best_obj) / best_obj:.6f}",
                    "own_objective": f"{own_obj:.6f}",
                    "best_objective": f"{best_obj:.6f}",
                    "own_crossing_connections_proxy": f"{own_cross:.0f}",
                    "best_crossing_connections_proxy": f"{best_cross:.0f}",
                    "crossing_gap": f"{own_cross - best_cross:.0f}",
                    "own_instance_balance_ratio": f"{own_bal:.6f}",
                    "best_instance_balance_ratio": f"{best_bal:.6f}",
                    "instance_balance_gap": f"{own_bal - best_bal:.6f}",
                    "own_weight_balance_ratio": f"{own_wbal:.6f}",
                    "best_weight_balance_ratio": f"{best_wbal:.6f}",
                    "weight_balance_gap": f"{own_wbal - best_wbal:.6f}",
                }
            )

            own_cost = unit_cost_map(own_units)
            best_cost = unit_cost_map(best_units)
            units = sorted(set(own_cost) | set(best_cost))
            for unit in units:
                delta = own_cost.get(unit, 0.0) - best_cost.get(unit, 0.0)
                if abs(delta) < 1e-9:
                    continue
                unit_delta_rows.append(
                    {
                        "design": design,
                        "evaluation_scenario": scenario,
                        "unit": unit,
                        "own_assignment_case": own_case,
                        "best_assignment_case": best_case,
                        "own_unit_cost": f"{own_cost.get(unit, 0.0):.6f}",
                        "best_unit_cost": f"{best_cost.get(unit, 0.0):.6f}",
                        "unit_cost_delta_own_minus_best": f"{delta:.6f}",
                    }
                )

            own_assignment = load_assignment(assignment_path(design, own_case))
            best_assignment = load_assignment(assignment_path(design, best_case))
            changed_by_unit: Counter[str] = Counter()
            own_tier0_by_unit: Counter[str] = Counter()
            best_tier0_by_unit: Counter[str] = Counter()
            common_instances = sorted(set(own_assignment) & set(best_assignment))
            for inst in common_instances:
                unit = instance_units.get(inst, "unknown")
                if own_assignment[inst] != best_assignment[inst]:
                    changed_by_unit[unit] += 1
                if own_assignment[inst] == "tier0":
                    own_tier0_by_unit[unit] += 1
                if best_assignment[inst] == "tier0":
                    best_tier0_by_unit[unit] += 1

            total_changed = sum(changed_by_unit.values())
            for unit, changed in changed_by_unit.most_common():
                tier_delta_rows.append(
                    {
                        "design": design,
                        "evaluation_scenario": scenario,
                        "unit": unit,
                        "own_assignment_case": own_case,
                        "best_assignment_case": best_case,
                        "changed_instances": changed,
                        "changed_fraction_of_all_changed": f"{changed / total_changed if total_changed else 0.0:.6f}",
                        "own_tier0_instances": own_tier0_by_unit[unit],
                        "best_tier0_instances": best_tier0_by_unit[unit],
                        "tier0_delta_own_minus_best": own_tier0_by_unit[unit] - best_tier0_by_unit[unit],
                    }
                )

    write_csv(
        OUT_DIR / "scenario_transfer_failure_analysis.csv",
        analysis_rows,
        [
            "design",
            "evaluation_scenario",
            "best_assignment_case",
            "own_assignment_case",
            "objective_gap",
            "objective_gap_fraction",
            "own_objective",
            "best_objective",
            "own_crossing_connections_proxy",
            "best_crossing_connections_proxy",
            "crossing_gap",
            "own_instance_balance_ratio",
            "best_instance_balance_ratio",
            "instance_balance_gap",
            "own_weight_balance_ratio",
            "best_weight_balance_ratio",
            "weight_balance_gap",
        ],
    )
    write_csv(
        OUT_DIR / "scenario_transfer_failure_unit_cost_delta.csv",
        unit_delta_rows,
        [
            "design",
            "evaluation_scenario",
            "unit",
            "own_assignment_case",
            "best_assignment_case",
            "own_unit_cost",
            "best_unit_cost",
            "unit_cost_delta_own_minus_best",
        ],
    )
    write_csv(
        OUT_DIR / "scenario_transfer_failure_tier_delta.csv",
        tier_delta_rows,
        [
            "design",
            "evaluation_scenario",
            "unit",
            "own_assignment_case",
            "best_assignment_case",
            "changed_instances",
            "changed_fraction_of_all_changed",
            "own_tier0_instances",
            "best_tier0_instances",
            "tier0_delta_own_minus_best",
        ],
    )

    print(OUT_DIR / "scenario_transfer_failure_analysis.csv")
    print(OUT_DIR / "scenario_transfer_failure_unit_cost_delta.csv")
    print(OUT_DIR / "scenario_transfer_failure_tier_delta.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
