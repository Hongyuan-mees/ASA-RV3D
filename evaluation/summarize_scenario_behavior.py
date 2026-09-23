#!/usr/bin/env python3
"""Create compact paper-facing summaries from scenario behavior analysis."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean


SCENARIOS = (
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def scenario_label(name: str) -> str:
    return {
        "control_datapath_split": "control/datapath",
        "memory_near_logic": "memory-near-logic",
        "state_and_clock_protected": "state/clock",
    }.get(name, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    delta_rows = read_csv(args.input_dir / "scenario_behavior_delta_summary.csv")
    pairwise_rows = read_csv(args.input_dir / "scenario_behavior_pairwise_summary.csv")
    gap_rows = read_csv(args.input_dir / "scenario_behavior_semantic_gap_summary.csv")

    designs = sorted({row["design"] for row in gap_rows})

    compact_rows: list[dict[str, object]] = []
    for design in designs:
        design_pairwise = [row for row in pairwise_rows if row["design"] == design]
        changed = [float(row["changed_fraction"]) for row in design_pairwise]
        max_pair = max(design_pairwise, key=lambda row: float(row["changed_fraction"])) if design_pairwise else None

        design_deltas = [row for row in delta_rows if row["design"] == design]
        abs_deltas = [float(row["abs_delta_tier0_instance_fraction"]) for row in design_deltas]
        max_delta = max(design_deltas, key=lambda row: float(row["abs_delta_tier0_instance_fraction"])) if design_deltas else None

        asa_gaps = [
            float(row["control_datapath_tier0_gap"])
            for row in gap_rows
            if row["design"] == design and row["case"] == "asa_rv3d"
        ]

        if not changed:
            scenario_sensitivity = "not_available"
        elif max(changed) >= 0.01:
            scenario_sensitivity = "visible_but_small"
        elif max(changed) >= 0.001:
            scenario_sensitivity = "small"
        else:
            scenario_sensitivity = "near_invariant"

        compact_rows.append(
            {
                "design": design,
                "scenario_sensitivity": scenario_sensitivity,
                "mean_pairwise_scenario_changed_fraction": fmt(mean(changed) if changed else 0.0),
                "max_pairwise_scenario_changed_fraction": fmt(max(changed) if changed else 0.0),
                "most_different_scenario_pair": (
                    f"{scenario_label(max_pair['scenario_a'])} vs {scenario_label(max_pair['scenario_b'])}"
                    if max_pair
                    else ""
                ),
                "mean_abs_unit_tier0_delta_vs_tritonpart": fmt(mean(abs_deltas) if abs_deltas else 0.0),
                "max_abs_unit_tier0_delta_vs_tritonpart": fmt(max(abs_deltas) if abs_deltas else 0.0),
                "max_delta_architecture_unit": max_delta["architecture_unit"] if max_delta else "",
                "max_delta_scenario": scenario_label(max_delta["scenario"]) if max_delta else "",
                "mean_asa_control_datapath_tier0_gap": fmt(mean(asa_gaps) if asa_gaps else 0.0),
                "paper_interpretation": (
                    "Scenario choice has visible but still guarded impact."
                    if scenario_sensitivity == "visible_but_small"
                    else "Scenario choice is strongly bounded by timing and balance guards."
                    if scenario_sensitivity in {"small", "near_invariant"}
                    else "No interpretation available."
                ),
            }
        )

    top_delta_rows: list[dict[str, object]] = []
    for design in designs:
        for scenario in SCENARIOS:
            subset = [
                row
                for row in delta_rows
                if row["design"] == design and row["scenario"] == scenario
            ]
            subset.sort(key=lambda row: float(row["abs_delta_tier0_instance_fraction"]), reverse=True)
            for rank, row in enumerate(subset[: args.top_k], start=1):
                top_delta_rows.append(
                    {
                        "design": design,
                        "scenario": scenario,
                        "rank": rank,
                        "architecture_unit": row["architecture_unit"],
                        "semantic_group": row["semantic_group"],
                        "instance_count": row["instance_count"],
                        "tritonpart_tier0_instance_fraction": row["tritonpart_tier0_instance_fraction"],
                        "asa_rv3d_tier0_instance_fraction": row["asa_rv3d_tier0_instance_fraction"],
                        "delta_tier0_instance_fraction": row["delta_tier0_instance_fraction"],
                        "abs_delta_tier0_instance_fraction": row["abs_delta_tier0_instance_fraction"],
                    }
                )

    write_csv(
        args.output_dir / "scenario_behavior_paper_summary.csv",
        [
            "design",
            "scenario_sensitivity",
            "mean_pairwise_scenario_changed_fraction",
            "max_pairwise_scenario_changed_fraction",
            "most_different_scenario_pair",
            "mean_abs_unit_tier0_delta_vs_tritonpart",
            "max_abs_unit_tier0_delta_vs_tritonpart",
            "max_delta_architecture_unit",
            "max_delta_scenario",
            "mean_asa_control_datapath_tier0_gap",
            "paper_interpretation",
        ],
        compact_rows,
    )
    write_csv(
        args.output_dir / "scenario_behavior_top_unit_changes.csv",
        [
            "design",
            "scenario",
            "rank",
            "architecture_unit",
            "semantic_group",
            "instance_count",
            "tritonpart_tier0_instance_fraction",
            "asa_rv3d_tier0_instance_fraction",
            "delta_tier0_instance_fraction",
            "abs_delta_tier0_instance_fraction",
        ],
        top_delta_rows,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
