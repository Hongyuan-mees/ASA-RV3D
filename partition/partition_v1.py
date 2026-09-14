#!/usr/bin/env python3
"""Generate and evaluate first-pass 2-tier Ibex partition assignments.

The goal is not to replace a graph partitioner yet. This script creates two
transparent baselines from extracted public ORFS data:

- generic_balance: architecture-oblivious greedy load balancing
- architecture_aware: rule-based RISC-V/Ibex class placement
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ARCH_TIER_POLICY: dict[str, str] = {
    "clock_reset": "tier0",
    "fetch": "tier0",
    "decode_control": "tier0",
    "csr": "tier0",
    "trap_debug": "tier0",
    "pipeline_state": "tier0",
    "generated_control": "tier0",
    "execute_alu": "tier1",
    "multdiv": "tier1",
    "load_store": "tier1",
    "register_file": "tier1",
    "generated_datapath": "tier1",
}


@dataclass(frozen=True)
class Instance:
    module: str
    instance: str
    cell_type: str
    cell_category: str
    architecture_class: str
    confidence: int
    net_count: int
    nets: tuple[str, ...]

    @property
    def weight(self) -> int:
        # A small proxy for instance importance. This is intentionally simple:
        # stable and available from the current feature CSV without Liberty area.
        base = 2 if self.cell_category == "sequential" else 1
        return base + min(self.net_count, 8)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_instances(features_dir: Path) -> list[Instance]:
    arch_rows = read_csv(features_dir / "architecture_instance_classes.csv")
    feature_rows = {
        row["instance"]: row
        for row in read_csv(features_dir / "instance_features.csv")
    }

    instances: list[Instance] = []
    for row in arch_rows:
        feature = feature_rows.get(row["instance"], {})
        nets = tuple(net for net in feature.get("nets", "").split(";") if net)
        instances.append(
            Instance(
                module=row["module"],
                instance=row["instance"],
                cell_type=row["cell_type"],
                cell_category=row["cell_category"],
                architecture_class=row["architecture_class"],
                confidence=int(row["confidence"] or 0),
                net_count=int(row["net_count"] or feature.get("net_count") or 0),
                nets=nets,
            )
        )
    return instances


def generic_balance(instances: list[Instance]) -> dict[str, str]:
    loads = {"tier0": 0, "tier1": 0}
    assignment: dict[str, str] = {}

    # Sort by descending weight for stable first-fit decreasing behavior.
    for inst in sorted(instances, key=lambda item: (-item.weight, item.instance)):
        tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight
    return assignment


def architecture_aware(instances: list[Instance]) -> dict[str, str]:
    loads = {"tier0": 0, "tier1": 0}
    assignment: dict[str, str] = {}

    for inst in sorted(instances, key=lambda item: (-item.confidence, item.architecture_class, item.instance)):
        tier = ARCH_TIER_POLICY.get(inst.architecture_class)
        if tier is None:
            tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight

    return assignment


def summarize_assignment(strategy: str, instances: list[Instance], assignment: dict[str, str]) -> dict[str, object]:
    tier_counts = Counter(assignment.values())
    tier_weights = Counter()
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    arch_counts: dict[str, Counter[str]] = defaultdict(Counter)
    net_tiers: dict[str, Counter[str]] = defaultdict(Counter)

    for inst in instances:
        tier = assignment[inst.instance]
        tier_weights[tier] += inst.weight
        category_counts[tier][inst.cell_category] += 1
        arch_counts[tier][inst.architecture_class] += 1
        for net in inst.nets:
            net_tiers[net][tier] += 1

    crossing_nets = 0
    crossing_connections = 0
    total_net_connections = 0
    for counts in net_tiers.values():
        total_net_connections += sum(counts.values())
        if len([tier for tier, count in counts.items() if count > 0]) > 1:
            crossing_nets += 1
            crossing_connections += min(counts["tier0"], counts["tier1"])

    total_instances = len(instances)
    total_weight = sum(tier_weights.values())
    count_balance = min(tier_counts["tier0"], tier_counts["tier1"]) / max(tier_counts["tier0"], tier_counts["tier1"])
    weight_balance = min(tier_weights["tier0"], tier_weights["tier1"]) / max(tier_weights["tier0"], tier_weights["tier1"])

    return {
        "strategy": strategy,
        "total_instances": total_instances,
        "tier0_instances": tier_counts["tier0"],
        "tier1_instances": tier_counts["tier1"],
        "instance_balance_ratio": f"{count_balance:.6f}",
        "total_weight": total_weight,
        "tier0_weight": tier_weights["tier0"],
        "tier1_weight": tier_weights["tier1"],
        "weight_balance_ratio": f"{weight_balance:.6f}",
        "crossing_nets": crossing_nets,
        "crossing_connections_proxy": crossing_connections,
        "total_net_connections": total_net_connections,
        "crossing_connection_fraction": f"{(crossing_connections / total_net_connections):.6f}" if total_net_connections else "0.000000",
        "tier0_top_arch_class": arch_counts["tier0"].most_common(1)[0][0] if arch_counts["tier0"] else "",
        "tier1_top_arch_class": arch_counts["tier1"].most_common(1)[0][0] if arch_counts["tier1"] else "",
    }


def assignment_rows(strategy: str, instances: list[Instance], assignment: dict[str, str]) -> list[dict[str, object]]:
    return [
        {
            "strategy": strategy,
            "module": inst.module,
            "instance": inst.instance,
            "tier": assignment[inst.instance],
            "weight": inst.weight,
            "cell_category": inst.cell_category,
            "architecture_class": inst.architecture_class,
            "confidence": inst.confidence,
            "net_count": inst.net_count,
        }
        for inst in sorted(instances, key=lambda item: item.instance)
    ]


def class_distribution_rows(strategy: str, instances: list[Instance], assignment: dict[str, str]) -> list[dict[str, object]]:
    counts: dict[tuple[str, str], int] = Counter()
    for inst in instances:
        counts[(inst.architecture_class, assignment[inst.instance])] += 1

    rows = []
    for arch_class in sorted({inst.architecture_class for inst in instances}):
        tier0 = counts[(arch_class, "tier0")]
        tier1 = counts[(arch_class, "tier1")]
        total = tier0 + tier1
        rows.append(
            {
                "strategy": strategy,
                "architecture_class": arch_class,
                "tier0_count": tier0,
                "tier1_count": tier1,
                "total_count": total,
                "tier0_fraction": f"{(tier0 / total):.6f}" if total else "0.000000",
                "tier1_fraction": f"{(tier1 / total):.6f}" if total else "0.000000",
            }
        )
    return rows


def crossing_net_rows(strategy: str, instances: list[Instance], assignment: dict[str, str], limit: int = 200) -> list[dict[str, object]]:
    net_tiers: dict[str, Counter[str]] = defaultdict(Counter)
    for inst in instances:
        tier = assignment[inst.instance]
        for net in inst.nets:
            net_tiers[net][tier] += 1

    rows = []
    for net, counts in net_tiers.items():
        if counts["tier0"] and counts["tier1"]:
            rows.append(
                {
                    "strategy": strategy,
                    "net": net,
                    "tier0_connections": counts["tier0"],
                    "tier1_connections": counts["tier1"],
                    "crossing_connections_proxy": min(counts["tier0"], counts["tier1"]),
                    "total_connections": counts["tier0"] + counts["tier1"],
                }
            )
    rows.sort(key=lambda row: (-int(row["crossing_connections_proxy"]), row["net"]))
    return rows[:limit]


def run(features_dir: Path, output_dir: Path) -> dict[str, object]:
    instances = load_instances(features_dir)
    strategies = {
        "generic_balance": generic_balance(instances),
        "architecture_aware": architecture_aware(instances),
    }

    comparison_rows = []
    all_distribution_rows = []
    manifest: dict[str, object] = {
        "features_dir": str(features_dir),
        "output_dir": str(output_dir),
        "instance_count": len(instances),
        "strategies": sorted(strategies),
        "architecture_tier_policy": ARCH_TIER_POLICY,
        "outputs": [
            "generic_balance_assignment.csv",
            "architecture_aware_assignment.csv",
            "partition_comparison.csv",
            "class_tier_distribution.csv",
            "top_crossing_nets.csv",
            "manifest.json",
        ],
    }

    all_crossing_rows = []
    for strategy, assignment in strategies.items():
        write_csv(
            output_dir / f"{strategy}_assignment.csv",
            assignment_rows(strategy, instances, assignment),
            ["strategy", "module", "instance", "tier", "weight", "cell_category", "architecture_class", "confidence", "net_count"],
        )
        comparison_rows.append(summarize_assignment(strategy, instances, assignment))
        all_distribution_rows.extend(class_distribution_rows(strategy, instances, assignment))
        all_crossing_rows.extend(crossing_net_rows(strategy, instances, assignment))

    write_csv(
        output_dir / "partition_comparison.csv",
        comparison_rows,
        [
            "strategy",
            "total_instances",
            "tier0_instances",
            "tier1_instances",
            "instance_balance_ratio",
            "total_weight",
            "tier0_weight",
            "tier1_weight",
            "weight_balance_ratio",
            "crossing_nets",
            "crossing_connections_proxy",
            "total_net_connections",
            "crossing_connection_fraction",
            "tier0_top_arch_class",
            "tier1_top_arch_class",
        ],
    )
    write_csv(
        output_dir / "class_tier_distribution.csv",
        all_distribution_rows,
        ["strategy", "architecture_class", "tier0_count", "tier1_count", "total_count", "tier0_fraction", "tier1_fraction"],
    )
    write_csv(
        output_dir / "top_crossing_nets.csv",
        all_crossing_rows,
        ["strategy", "net", "tier0_connections", "tier1_connections", "crossing_connections_proxy", "total_connections"],
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, default=Path("results") / "ibex_features")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "partition_v1")
    args = parser.parse_args()

    manifest = run(args.features_dir.resolve(), args.output_dir.resolve())
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
