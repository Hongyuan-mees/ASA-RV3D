#!/usr/bin/env python3
"""Score-based architecture-aware 2-tier partition heuristic.

Partition v1 used a fixed architecture-to-tier policy. Partition v2 keeps that
architecture bias, but adds a simple objective and local refinement loop:

    objective = crossing proxy + balance penalties + architecture penalty

This makes the method easier to explain as an optimization heuristic rather
than only a fixed rule table.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TIERS = ("tier0", "tier1")

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
        base = 2 if self.cell_category == "sequential" else 1
        return base + min(self.net_count, 8)


@dataclass
class State:
    assignment: dict[str, str]
    tier_counts: Counter[str]
    tier_weights: Counter[str]
    net_tiers: dict[str, Counter[str]]


@dataclass(frozen=True)
class ObjectiveWeights:
    crossing: float
    instance_balance: float
    weight_balance: float
    architecture: float


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
    arch_path = features_dir / "architecture_instance_classes.csv"
    feature_path = features_dir / "instance_features.csv"
    arch_rows = read_csv(arch_path)
    feature_rows = {row["instance"]: row for row in read_csv(feature_path)}

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


def make_state(instances: list[Instance], assignment: dict[str, str]) -> State:
    by_name = {inst.instance: inst for inst in instances}
    tier_counts: Counter[str] = Counter()
    tier_weights: Counter[str] = Counter()
    net_tiers: dict[str, Counter[str]] = defaultdict(Counter)

    for instance, tier in assignment.items():
        inst = by_name[instance]
        tier_counts[tier] += 1
        tier_weights[tier] += inst.weight
        for net in inst.nets:
            net_tiers[net][tier] += 1

    return State(assignment=dict(assignment), tier_counts=tier_counts, tier_weights=tier_weights, net_tiers=net_tiers)


def generic_balance(instances: list[Instance]) -> dict[str, str]:
    loads = Counter({"tier0": 0, "tier1": 0})
    assignment: dict[str, str] = {}
    for inst in sorted(instances, key=lambda item: (-item.weight, item.instance)):
        tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight
    return assignment


def architecture_aware_v1(instances: list[Instance]) -> dict[str, str]:
    loads = Counter({"tier0": 0, "tier1": 0})
    assignment: dict[str, str] = {}
    for inst in sorted(instances, key=lambda item: (-item.confidence, item.architecture_class, item.instance)):
        tier = ARCH_TIER_POLICY.get(inst.architecture_class)
        if tier is None:
            tier = "tier0" if loads["tier0"] <= loads["tier1"] else "tier1"
        assignment[inst.instance] = tier
        loads[tier] += inst.weight
    return assignment


def crossing_connection_proxy(net_tiers: dict[str, Counter[str]]) -> int:
    total = 0
    for counts in net_tiers.values():
        total += min(counts["tier0"], counts["tier1"])
    return total


def crossing_net_count(net_tiers: dict[str, Counter[str]]) -> int:
    total = 0
    for counts in net_tiers.values():
        if counts["tier0"] and counts["tier1"]:
            total += 1
    return total


def total_net_connections(net_tiers: dict[str, Counter[str]]) -> int:
    return sum(counts["tier0"] + counts["tier1"] for counts in net_tiers.values())


def architecture_penalty(inst: Instance, tier: str, weights: ObjectiveWeights) -> float:
    preferred = ARCH_TIER_POLICY.get(inst.architecture_class)
    if preferred is None or tier == preferred:
        return 0.0
    confidence_scale = min(max(inst.confidence, 1), 10) / 10.0
    return weights.architecture * inst.weight * confidence_scale


def objective(state: State, instances_by_name: dict[str, Instance], weights: ObjectiveWeights) -> float:
    arch_penalty = 0.0
    for instance, tier in state.assignment.items():
        arch_penalty += architecture_penalty(instances_by_name[instance], tier, weights)
    return (
        weights.crossing * crossing_connection_proxy(state.net_tiers)
        + weights.instance_balance * abs(state.tier_counts["tier0"] - state.tier_counts["tier1"])
        + weights.weight_balance * abs(state.tier_weights["tier0"] - state.tier_weights["tier1"])
        + arch_penalty
    )


def move_delta(state: State, inst: Instance, old_tier: str, new_tier: str, weights: ObjectiveWeights) -> float:
    before_cross = 0
    after_cross = 0
    for net in inst.nets:
        counts = state.net_tiers[net]
        before_cross += min(counts["tier0"], counts["tier1"])
        new_counts = Counter(counts)
        new_counts[old_tier] -= 1
        new_counts[new_tier] += 1
        after_cross += min(new_counts["tier0"], new_counts["tier1"])

    before_count_gap = abs(state.tier_counts["tier0"] - state.tier_counts["tier1"])
    after_counts = Counter(state.tier_counts)
    after_counts[old_tier] -= 1
    after_counts[new_tier] += 1
    after_count_gap = abs(after_counts["tier0"] - after_counts["tier1"])

    before_weight_gap = abs(state.tier_weights["tier0"] - state.tier_weights["tier1"])
    after_weights = Counter(state.tier_weights)
    after_weights[old_tier] -= inst.weight
    after_weights[new_tier] += inst.weight
    after_weight_gap = abs(after_weights["tier0"] - after_weights["tier1"])

    before_arch = architecture_penalty(inst, old_tier, weights)
    after_arch = architecture_penalty(inst, new_tier, weights)

    return (
        weights.crossing * (after_cross - before_cross)
        + weights.instance_balance * (after_count_gap - before_count_gap)
        + weights.weight_balance * (after_weight_gap - before_weight_gap)
        + (after_arch - before_arch)
    )


def balance_ratio(tier_values: Counter[str]) -> float:
    low = min(tier_values["tier0"], tier_values["tier1"])
    high = max(tier_values["tier0"], tier_values["tier1"])
    return low / high if high else 1.0


def move_satisfies_balance(
    state: State,
    inst: Instance,
    old_tier: str,
    new_tier: str,
    min_instance_balance: float,
    min_weight_balance: float,
) -> bool:
    after_counts = Counter(state.tier_counts)
    after_counts[old_tier] -= 1
    after_counts[new_tier] += 1

    after_weights = Counter(state.tier_weights)
    after_weights[old_tier] -= inst.weight
    after_weights[new_tier] += inst.weight

    before_instance = balance_ratio(state.tier_counts)
    before_weight = balance_ratio(state.tier_weights)
    after_instance = balance_ratio(after_counts)
    after_weight = balance_ratio(after_weights)

    if after_instance >= min_instance_balance and after_weight >= min_weight_balance:
        return True

    # If the current assignment is already outside the requested balance
    # region, allow repair moves that monotonically improve balance. This
    # matters for designs where the architecture-aware initial assignment is
    # useful for crossing reduction but too imbalanced to satisfy hard
    # constraints in a single move.
    improves_instance = after_instance >= before_instance
    improves_weight = after_weight >= before_weight
    strictly_improves = after_instance > before_instance or after_weight > before_weight
    return improves_instance and improves_weight and strictly_improves


def apply_move(state: State, inst: Instance, old_tier: str, new_tier: str) -> None:
    state.assignment[inst.instance] = new_tier
    state.tier_counts[old_tier] -= 1
    state.tier_counts[new_tier] += 1
    state.tier_weights[old_tier] -= inst.weight
    state.tier_weights[new_tier] += inst.weight
    for net in inst.nets:
        state.net_tiers[net][old_tier] -= 1
        state.net_tiers[net][new_tier] += 1


def architecture_score_v2(
    instances: list[Instance],
    weights: ObjectiveWeights,
    max_passes: int,
    max_moves_per_pass: int,
    min_gain: float,
    min_instance_balance: float,
    min_weight_balance: float,
) -> tuple[dict[str, str], list[dict[str, object]]]:
    instances_by_name = {inst.instance: inst for inst in instances}
    state = make_state(instances, architecture_aware_v1(instances))
    trace: list[dict[str, object]] = []

    # Low-confidence and large-fanout instances move first; this lets the
    # refinement repair obvious cut penalties without immediately breaking
    # high-confidence architecture placement.
    candidates = sorted(instances, key=lambda item: (item.confidence, -item.net_count, item.instance))

    current_obj = objective(state, instances_by_name, weights)
    for pass_idx in range(1, max_passes + 1):
        moves_this_pass = 0
        best_gain_this_pass = 0.0
        for inst in candidates:
            old_tier = state.assignment[inst.instance]
            new_tier = "tier1" if old_tier == "tier0" else "tier0"
            if not move_satisfies_balance(state, inst, old_tier, new_tier, min_instance_balance, min_weight_balance):
                continue
            delta = move_delta(state, inst, old_tier, new_tier, weights)
            gain = -delta
            if gain <= min_gain:
                continue
            apply_move(state, inst, old_tier, new_tier)
            current_obj += delta
            moves_this_pass += 1
            best_gain_this_pass = max(best_gain_this_pass, gain)
            if moves_this_pass <= 200:
                trace.append(
                    {
                        "pass": pass_idx,
                        "move_index": moves_this_pass,
                        "instance": inst.instance,
                        "architecture_class": inst.architecture_class,
                        "from_tier": old_tier,
                        "to_tier": new_tier,
                        "gain": f"{gain:.6f}",
                        "objective_after": f"{current_obj:.6f}",
                    }
                )
            if moves_this_pass >= max_moves_per_pass:
                break
        if moves_this_pass == 0:
            break
        trace.append(
            {
                "pass": pass_idx,
                "move_index": "summary",
                "instance": "",
                "architecture_class": "",
                "from_tier": "",
                "to_tier": "",
                "gain": f"{best_gain_this_pass:.6f}",
                "objective_after": f"{current_obj:.6f}",
            }
        )

    return state.assignment, trace


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


def summarize_assignment(strategy: str, instances: list[Instance], assignment: dict[str, str]) -> dict[str, object]:
    state = make_state(instances, assignment)
    arch_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for inst in instances:
        arch_counts[assignment[inst.instance]][inst.architecture_class] += 1

    crossing_connections = crossing_connection_proxy(state.net_tiers)
    connections = total_net_connections(state.net_tiers)
    instance_balance = min(state.tier_counts["tier0"], state.tier_counts["tier1"]) / max(state.tier_counts["tier0"], state.tier_counts["tier1"])
    weight_balance = min(state.tier_weights["tier0"], state.tier_weights["tier1"]) / max(state.tier_weights["tier0"], state.tier_weights["tier1"])

    return {
        "strategy": strategy,
        "total_instances": len(instances),
        "tier0_instances": state.tier_counts["tier0"],
        "tier1_instances": state.tier_counts["tier1"],
        "instance_balance_ratio": f"{instance_balance:.6f}",
        "total_weight": state.tier_weights["tier0"] + state.tier_weights["tier1"],
        "tier0_weight": state.tier_weights["tier0"],
        "tier1_weight": state.tier_weights["tier1"],
        "weight_balance_ratio": f"{weight_balance:.6f}",
        "crossing_nets": crossing_net_count(state.net_tiers),
        "crossing_connections_proxy": crossing_connections,
        "total_net_connections": connections,
        "crossing_connection_fraction": f"{(crossing_connections / connections):.6f}" if connections else "0.000000",
        "tier0_top_arch_class": arch_counts["tier0"].most_common(1)[0][0] if arch_counts["tier0"] else "",
        "tier1_top_arch_class": arch_counts["tier1"].most_common(1)[0][0] if arch_counts["tier1"] else "",
    }


def class_distribution_rows(strategy: str, instances: list[Instance], assignment: dict[str, str]) -> list[dict[str, object]]:
    counts: Counter[tuple[str, str]] = Counter()
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
    state = make_state(instances, assignment)
    rows = []
    for net, counts in state.net_tiers.items():
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


def run(args: argparse.Namespace) -> dict[str, object]:
    features_dir = args.features_dir.resolve()
    output_dir = args.output_dir.resolve()
    instances = load_instances(features_dir)
    weights = ObjectiveWeights(
        crossing=args.crossing_weight,
        instance_balance=args.instance_balance_weight,
        weight_balance=args.weight_balance_weight,
        architecture=args.architecture_weight,
    )

    v2_assignment, trace = architecture_score_v2(
        instances=instances,
        weights=weights,
        max_passes=args.max_passes,
        max_moves_per_pass=args.max_moves_per_pass,
        min_gain=args.min_gain,
        min_instance_balance=args.min_instance_balance,
        min_weight_balance=args.min_weight_balance,
    )
    strategies = {
        "generic_balance": generic_balance(instances),
        "architecture_aware_v1": architecture_aware_v1(instances),
        "architecture_score_v2": v2_assignment,
    }

    comparison_rows = []
    distribution_rows = []
    crossing_rows = []
    for strategy, assignment in strategies.items():
        write_csv(
            output_dir / f"{strategy}_assignment.csv",
            assignment_rows(strategy, instances, assignment),
            ["strategy", "module", "instance", "tier", "weight", "cell_category", "architecture_class", "confidence", "net_count"],
        )
        comparison_rows.append(summarize_assignment(strategy, instances, assignment))
        distribution_rows.extend(class_distribution_rows(strategy, instances, assignment))
        crossing_rows.extend(crossing_net_rows(strategy, instances, assignment))

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
        distribution_rows,
        ["strategy", "architecture_class", "tier0_count", "tier1_count", "total_count", "tier0_fraction", "tier1_fraction"],
    )
    write_csv(
        output_dir / "top_crossing_nets.csv",
        crossing_rows,
        ["strategy", "net", "tier0_connections", "tier1_connections", "crossing_connections_proxy", "total_connections"],
    )
    write_csv(
        output_dir / "local_refinement_trace.csv",
        trace,
        ["pass", "move_index", "instance", "architecture_class", "from_tier", "to_tier", "gain", "objective_after"],
    )

    manifest = {
        "features_dir": str(features_dir),
        "output_dir": str(output_dir),
        "instance_count": len(instances),
        "objective_weights": weights.__dict__,
        "max_passes": args.max_passes,
        "max_moves_per_pass": args.max_moves_per_pass,
        "min_gain": args.min_gain,
        "min_instance_balance": args.min_instance_balance,
        "min_weight_balance": args.min_weight_balance,
        "architecture_tier_policy": ARCH_TIER_POLICY,
        "outputs": [
            "generic_balance_assignment.csv",
            "architecture_aware_v1_assignment.csv",
            "architecture_score_v2_assignment.csv",
            "partition_comparison.csv",
            "class_tier_distribution.csv",
            "top_crossing_nets.csv",
            "local_refinement_trace.csv",
            "manifest.json",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, default=Path("results") / "ibex_features")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "partition_v2")
    parser.add_argument("--crossing-weight", type=float, default=1.0)
    parser.add_argument("--instance-balance-weight", type=float, default=0.4)
    parser.add_argument("--weight-balance-weight", type=float, default=0.02)
    parser.add_argument("--architecture-weight", type=float, default=0.4)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--min-instance-balance", type=float, default=0.80)
    parser.add_argument("--min-weight-balance", type=float, default=0.95)
    args = parser.parse_args()

    manifest = run(args)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
