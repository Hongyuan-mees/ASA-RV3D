#!/usr/bin/env python3
"""Evaluate v4 physical-context partitions against earlier assignments.

This script compares all relevant assignments under the same scenario-specific
physical-augmented objective:

  scenario objective + physical_weight * physical_context_crossing_penalty

It is intentionally table-only. Do not use it for plotting; use it to decide
whether the physical-aware partitioner is genuinely better than v3 and the
previous scenario-aware partitioner.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_assignment(path: Path) -> dict[str, str]:
    return {row["instance"]: row["tier"] for row in read_csv(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("results/benchmark_summary/v4_physical_comparison.csv"))
    parser.add_argument("--physical-weight", type=float, default=1.0)
    parser.add_argument("--architecture-weight", type=float, default=0.35)
    parser.add_argument("--context-weight", type=float, default=1.0)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/3d_integration_scenarios.yaml"))
    args = parser.parse_args()

    sys.path.insert(0, str(Path("partition").resolve()))
    import partition_scenario_aware as scenario_base
    import partition_v4_physical_context as physical_v4

    scenario_names = [
        "control_datapath_split",
        "memory_near_logic",
        "state_and_clock_protected",
    ]
    designs = ["ibex", "riscv32i"]
    scenarios = scenario_base.parse_scenarios(args.scenarios)
    rows: list[dict[str, object]] = []

    for design in designs:
        features_dir = Path("results") / f"{design}_features"
        instances = scenario_base.load_instances(features_dir)
        physical_scores = physical_v4.load_physical_scores(features_dir)

        for scenario_name in scenario_names:
            scenario = scenarios[scenario_name]
            net_info = scenario_base.build_net_info(instances, scenario)
            net_risk = physical_v4.build_net_physical_risk(net_info, physical_scores)

            assignments = {
                "generic": Path("results") / f"{design}_partition_v4_physical" / scenario_name / "generic_balance_assignment.csv",
                "v3_context": Path("results") / f"{design}_partition_v3_context" / "architecture_score_v2_assignment.csv",
                "scenario_aware": Path("results") / f"{design}_scenario_partition" / scenario_name / "scenario_aware_assignment.csv",
                "v4_physical": Path("results") / f"{design}_partition_v4_physical" / scenario_name / "physical_context_aware_assignment.csv",
            }

            summary_rows = []
            for case, path in assignments.items():
                if not path.exists():
                    raise FileNotFoundError(path)
                assignment = load_assignment(path)
                summary = physical_v4.summarize_assignment(
                    case,
                    assignment,
                    instances,
                    net_info,
                    net_risk,
                    scenario,
                    scenario_name,
                    args.architecture_weight,
                    args.context_weight,
                    args.physical_weight,
                )
                summary_rows.append(summary)

            by_case = {row["strategy"]: row for row in summary_rows}
            generic_obj = float(by_case["generic"]["physical_augmented_objective"])
            scenario_obj = float(by_case["scenario_aware"]["physical_augmented_objective"])
            best_obj = min(float(row["physical_augmented_objective"]) for row in summary_rows)

            for row in summary_rows:
                cur = float(row["physical_augmented_objective"])
                rows.append(
                    {
                        "design": design,
                        "scenario": scenario_name,
                        "case": row["strategy"],
                        "crossing_connections_proxy": row["crossing_connections_proxy"],
                        "crossing_connection_fraction": row["crossing_connection_fraction"],
                        "instance_balance_ratio": row["instance_balance_ratio"],
                        "weight_balance_ratio": row["weight_balance_ratio"],
                        "scenario_objective": row["scenario_objective"],
                        "physical_context_crossing_penalty": row["physical_context_crossing_penalty"],
                        "physical_augmented_objective": row["physical_augmented_objective"],
                        "reduction_vs_generic": f"{(generic_obj - cur) / generic_obj if generic_obj else 0.0:.6f}",
                        "reduction_vs_scenario_aware": f"{(scenario_obj - cur) / scenario_obj if scenario_obj else 0.0:.6f}",
                        "gap_vs_best": f"{cur - best_obj:.6f}",
                        "is_best": int(abs(cur - best_obj) < 1e-9),
                    }
                )

    fields = [
        "design",
        "scenario",
        "case",
        "crossing_connections_proxy",
        "crossing_connection_fraction",
        "instance_balance_ratio",
        "weight_balance_ratio",
        "scenario_objective",
        "physical_context_crossing_penalty",
        "physical_augmented_objective",
        "reduction_vs_generic",
        "reduction_vs_scenario_aware",
        "gap_vs_best",
        "is_best",
    ]
    write_csv(args.output, rows, fields)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
