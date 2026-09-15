#!/usr/bin/env python3
"""Analyze scenario-aware partition behavior across RISC-V 3D scenarios.

Stage 5 of the ASA-RV3D plan.

This script checks whether different scenario-aware partitions actually change
architecture-unit placement and bottleneck structure. It intentionally produces
machine-readable CSVs only; final figures come later.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_SCENARIOS = [
    "state_and_clock_protected",
    "memory_near_logic",
    "control_datapath_split",
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


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except ValueError:
        return default


def unit_distribution(design: str, scenario: str, assignment: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    by_unit: dict[str, Counter[str]] = defaultdict(Counter)
    by_group: dict[str, str] = {}
    for row in assignment.values():
        unit = row.get("architecture_unit", "unclassified")
        tier = row["tier"]
        by_unit[unit][tier] += 1
        by_group[unit] = row.get("semantic_group", "infrastructure")

    rows = []
    for unit, counts in sorted(by_unit.items()):
        total = counts["tier0"] + counts["tier1"]
        tier0_frac = counts["tier0"] / total if total else 0.0
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "architecture_unit": unit,
                "semantic_group": by_group.get(unit, "infrastructure"),
                "tier0_count": counts["tier0"],
                "tier1_count": counts["tier1"],
                "total_count": total,
                "tier0_fraction": f"{tier0_frac:.6f}",
                "tier_dominance": f"{abs(counts['tier0'] - counts['tier1']) / total if total else 0.0:.6f}",
                "dominant_tier": "tier0" if counts["tier0"] >= counts["tier1"] else "tier1",
            }
        )
    return rows


def load_net_features(features_dir: Path) -> dict[str, list[str]]:
    rows = read_csv(features_dir / "instance_features.csv")
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = row["instance"]
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return net_to_instances


def crossing_unit_rows(
    design: str,
    scenario: str,
    assignment: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
) -> list[dict[str, object]]:
    pair_counts = Counter()
    unit_counts = Counter()
    crossing_net_count = 0

    for net, insts_all in net_to_instances.items():
        insts = [inst for inst in insts_all if inst in assignment]
        if not insts:
            continue
        tiers = {assignment[inst]["tier"] for inst in insts}
        if len(tiers) <= 1:
            continue
        crossing_net_count += 1
        units = sorted({assignment[inst].get("architecture_unit", "unclassified") for inst in insts})
        for unit in units:
            unit_counts[unit] += 1
        for i, left in enumerate(units):
            for right in units[i:]:
                pair_counts[(left, right)] += 1

    unit_rows = [
        {
            "design": design,
            "scenario": scenario,
            "architecture_unit": unit,
            "crossing_net_count": count,
            "fraction_of_crossing_nets": f"{count / crossing_net_count if crossing_net_count else 0.0:.6f}",
        }
        for unit, count in unit_counts.most_common()
    ]
    pair_rows = [
        {
            "design": design,
            "scenario": scenario,
            "unit_a": left,
            "unit_b": right,
            "crossing_net_count": count,
            "fraction_of_crossing_nets": f"{count / crossing_net_count if crossing_net_count else 0.0:.6f}",
        }
        for (left, right), count in pair_counts.most_common()
    ]
    return unit_rows, pair_rows


def scenario_migration_rows(
    design: str,
    scenario_assignments: dict[str, dict[str, dict[str, str]]],
) -> list[dict[str, object]]:
    scenarios = list(scenario_assignments)
    instances = sorted(set.intersection(*(set(a) for a in scenario_assignments.values())))
    rows = []
    for inst in instances:
        tiers = {scenario: scenario_assignments[scenario][inst]["tier"] for scenario in scenarios}
        unique_tiers = set(tiers.values())
        if len(unique_tiers) <= 1:
            continue
        ref = scenario_assignments[scenarios[0]][inst]
        row = {
            "design": design,
            "instance": inst,
            "architecture_unit": ref.get("architecture_unit", "unclassified"),
            "semantic_group": ref.get("semantic_group", "infrastructure"),
            "unique_tier_count": len(unique_tiers),
        }
        for scenario in scenarios:
            row[f"{scenario}_tier"] = tiers[scenario]
        rows.append(row)
    return rows


def migration_summary_rows(migration_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for row in migration_rows:
        key = (str(row["design"]), str(row["architecture_unit"]))
        counts[key]["migrating_instances"] += 1
        counts[key]["unique_tier_count_sum"] += int(row["unique_tier_count"])

    rows = []
    for (design, unit), counter in sorted(counts.items()):
        count = counter["migrating_instances"]
        rows.append(
            {
                "design": design,
                "architecture_unit": unit,
                "migrating_instances": count,
                "mean_unique_tier_count": f"{counter['unique_tier_count_sum'] / count if count else 0.0:.6f}",
            }
        )
    rows.sort(key=lambda row: (-int(row["migrating_instances"]), row["design"], row["architecture_unit"]))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--partition-root", type=Path, required=True)
    parser.add_argument("--scenario", action="append", default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    scenarios = args.scenario or DEFAULT_SCENARIOS
    net_to_instances = load_net_features(args.features_dir)
    scenario_assignments: dict[str, dict[str, dict[str, str]]] = {}

    distribution_rows = []
    unit_crossing_rows = []
    pair_crossing_rows = []

    for scenario in scenarios:
        assignment_path = args.partition_root / scenario / "scenario_aware_assignment.csv"
        assignment = load_assignment(assignment_path)
        scenario_assignments[scenario] = assignment
        distribution_rows.extend(unit_distribution(args.design, scenario, assignment))
        unit_rows, pair_rows = crossing_unit_rows(args.design, scenario, assignment, net_to_instances)
        unit_crossing_rows.extend(unit_rows)
        pair_crossing_rows.extend(pair_rows)

    migration = scenario_migration_rows(args.design, scenario_assignments)
    migration_summary = migration_summary_rows(migration)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    dist_path = args.output_dir / f"{args.design}_scenario_unit_distribution.csv"
    migration_path = args.output_dir / f"{args.design}_scenario_unit_migration.csv"
    migration_summary_path = args.output_dir / f"{args.design}_scenario_unit_migration_summary.csv"
    unit_cross_path = args.output_dir / f"{args.design}_scenario_crossing_units.csv"
    pair_cross_path = args.output_dir / f"{args.design}_scenario_crossing_unit_pairs.csv"
    manifest_path = args.output_dir / f"{args.design}_scenario_partition_analysis_manifest.json"

    write_csv(
        dist_path,
        distribution_rows,
        [
            "design",
            "scenario",
            "architecture_unit",
            "semantic_group",
            "tier0_count",
            "tier1_count",
            "total_count",
            "tier0_fraction",
            "tier_dominance",
            "dominant_tier",
        ],
    )
    write_csv(
        migration_path,
        migration,
        ["design", "instance", "architecture_unit", "semantic_group", "unique_tier_count", *[f"{s}_tier" for s in scenarios]],
    )
    write_csv(
        migration_summary_path,
        migration_summary,
        ["design", "architecture_unit", "migrating_instances", "mean_unique_tier_count"],
    )
    write_csv(
        unit_cross_path,
        unit_crossing_rows,
        ["design", "scenario", "architecture_unit", "crossing_net_count", "fraction_of_crossing_nets"],
    )
    write_csv(
        pair_cross_path,
        pair_crossing_rows,
        ["design", "scenario", "unit_a", "unit_b", "crossing_net_count", "fraction_of_crossing_nets"],
    )
    manifest = {
        "design": args.design,
        "features_dir": str(args.features_dir),
        "partition_root": str(args.partition_root),
        "scenarios": scenarios,
        "outputs": [
            str(dist_path),
            str(migration_path),
            str(migration_summary_path),
            str(unit_cross_path),
            str(pair_cross_path),
            str(manifest_path),
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(dist_path)
    print(migration_path)
    print(migration_summary_path)
    print(unit_cross_path)
    print(pair_cross_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
