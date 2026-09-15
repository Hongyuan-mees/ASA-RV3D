#!/usr/bin/env python3
"""Compare tier assignments and report instance-level deltas.

Used as a sanity check for scenario-aware partitioning:

  Does scenario_aware create a genuinely different assignment from v3_context,
  or is it effectively copying the previous result?
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_COMPARISONS = [
    {
        "design": "ibex",
        "scenario": "state_and_clock_protected",
        "baseline": "results/ibex_partition_v3_context/architecture_score_v2_assignment.csv",
        "candidate": "results/ibex_scenario_partition/state_and_clock_protected/scenario_aware_assignment.csv",
    },
    {
        "design": "riscv32i",
        "scenario": "state_and_clock_protected",
        "baseline": "results/riscv32i_partition_v3_context/architecture_score_v2_assignment.csv",
        "candidate": "results/riscv32i_scenario_partition/state_and_clock_protected/scenario_aware_assignment.csv",
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_assignment(path: Path) -> dict[str, dict[str, str]]:
    return {row["instance"]: row for row in read_csv(path)}


def compare(design: str, scenario: str, baseline_path: Path, candidate_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    baseline = load_assignment(baseline_path)
    candidate = load_assignment(candidate_path)
    common = sorted(set(baseline) & set(candidate))
    changed = [inst for inst in common if baseline[inst]["tier"] != candidate[inst]["tier"]]

    unit_counts = Counter()
    group_counts = Counter()
    direction_counts = Counter()
    rows = []
    for inst in changed:
        cand = candidate[inst]
        base = baseline[inst]
        unit = cand.get("architecture_unit") or base.get("architecture_unit") or "unknown"
        group = cand.get("semantic_group") or base.get("semantic_group") or "unknown"
        direction = f"{base['tier']}->{cand['tier']}"
        unit_counts[unit] += 1
        group_counts[group] += 1
        direction_counts[direction] += 1
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "instance": inst,
                "baseline_tier": base["tier"],
                "candidate_tier": cand["tier"],
                "direction": direction,
                "architecture_unit": unit,
                "semantic_group": group,
            }
        )

    top_units = ";".join(f"{unit}:{count}" for unit, count in unit_counts.most_common(8))
    top_groups = ";".join(f"{group}:{count}" for group, count in group_counts.most_common())
    directions = ";".join(f"{direction}:{count}" for direction, count in direction_counts.most_common())

    summary = {
        "design": design,
        "scenario": scenario,
        "baseline_file": str(baseline_path),
        "candidate_file": str(candidate_path),
        "common_instances": len(common),
        "different_tier_instances": len(changed),
        "difference_fraction": f"{len(changed) / len(common) if common else 0.0:.6f}",
        "top_changed_units": top_units,
        "changed_semantic_groups": top_groups,
        "move_directions": directions,
    }
    return summary, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-summary", type=Path, default=Path("results/benchmark_summary/scenario_vs_v3_assignment_delta.csv"))
    parser.add_argument("--output-instances", type=Path, default=Path("results/benchmark_summary/scenario_vs_v3_assignment_delta_instances.csv"))
    args = parser.parse_args()

    summaries = []
    all_rows = []
    for spec in DEFAULT_COMPARISONS:
        summary, rows = compare(
            design=spec["design"],
            scenario=spec["scenario"],
            baseline_path=Path(spec["baseline"]),
            candidate_path=Path(spec["candidate"]),
        )
        summaries.append(summary)
        all_rows.extend(rows)

    write_csv(
        args.output_summary,
        summaries,
        [
            "design",
            "scenario",
            "baseline_file",
            "candidate_file",
            "common_instances",
            "different_tier_instances",
            "difference_fraction",
            "top_changed_units",
            "changed_semantic_groups",
            "move_directions",
        ],
    )
    write_csv(
        args.output_instances,
        all_rows,
        [
            "design",
            "scenario",
            "instance",
            "baseline_tier",
            "candidate_tier",
            "direction",
            "architecture_unit",
            "semantic_group",
        ],
    )
    print(args.output_summary)
    print(args.output_instances)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
