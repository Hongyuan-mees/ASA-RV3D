#!/usr/bin/env python3
"""Evaluate partition assignments with multiple lightweight metrics.

The script reads an instance feature directory and one or more assignment CSVs
produced by the partition scripts. It reports crossing, balance, and semantic
separation metrics in a single summary table.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


CONTROL_CLASSES = {
    "clock_reset",
    "csr",
    "decode_control",
    "decoder_control",
    "fetch",
    "instruction_fetch",
    "generated_control",
    "pipeline_state",
    "trap_debug",
}

DATAPATH_CLASSES = {
    "execute_alu",
    "execute_multdiv",
    "generated_datapath",
    "load_store",
    "multdiv",
    "register_file",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def semantic_group(arch_class: str) -> str:
    if arch_class in CONTROL_CLASSES:
        return "control"
    if arch_class in DATAPATH_CLASSES:
        return "datapath"
    if arch_class in {"unclassified", "other", ""}:
        return "unknown"
    return "other"


def balance_ratio(a: int, b: int) -> float:
    high = max(a, b)
    low = min(a, b)
    return low / high if high else 1.0


def load_features(features_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    feature_rows = read_csv(features_dir / "instance_features.csv")
    arch_path = features_dir / "architecture_instance_classes.csv"
    arch_by_instance: dict[str, dict[str, str]] = {}
    if arch_path.exists():
        arch_by_instance = {row["instance"]: row for row in read_csv(arch_path)}

    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)

    for row in feature_rows:
        inst = row["instance"]
        arch = arch_by_instance.get(inst)
        architecture_class = arch.get("architecture_class", row.get("arch_class", "unknown")) if arch else row.get("arch_class", "unknown")
        confidence = arch.get("confidence", "") if arch else ""
        enriched = dict(row)
        enriched["architecture_class"] = architecture_class
        enriched["architecture_confidence"] = confidence
        enriched["semantic_group"] = semantic_group(architecture_class)
        instances[inst] = enriched

        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)

    return instances, net_to_instances


def load_assignment(path: Path) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for row in read_csv(path):
        assignment[row["instance"]] = row["tier"]
    return assignment


def evaluate_assignment(
    design: str,
    case: str,
    assignment_path: Path,
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
) -> dict[str, object]:
    assignment = load_assignment(assignment_path)

    tier_counts = Counter()
    tier_weights = Counter()
    tier_group_counts: dict[str, Counter[str]] = defaultdict(Counter)
    tier_arch_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for inst, tier in assignment.items():
        row = instances[inst]
        weight = max(1, int(row.get("net_count", "0") or 0))
        tier_counts[tier] += 1
        tier_weights[tier] += weight
        tier_group_counts[tier][row["semantic_group"]] += 1
        tier_arch_counts[tier][row["architecture_class"]] += 1

    crossing_nets = 0
    crossing_connections_proxy = 0
    total_net_connections = 0
    weighted_crossing_proxy = 0
    control_datapath_crossing_nets = 0

    for net, connected in net_to_instances.items():
        tiers = Counter(assignment[inst] for inst in connected if inst in assignment)
        if not tiers:
            continue
        total = sum(tiers.values())
        total_net_connections += total
        if len(tiers) > 1:
            crossing_nets += 1
            minority = min(tiers.values())
            crossing_connections_proxy += minority
            weighted_crossing_proxy += minority * max(1, total - 1)

            groups = {instances[inst]["semantic_group"] for inst in connected if inst in assignment}
            if "control" in groups and "datapath" in groups:
                control_datapath_crossing_nets += 1

    control_total = sum(tier_group_counts[tier]["control"] for tier in tier_group_counts)
    datapath_total = sum(tier_group_counts[tier]["datapath"] for tier in tier_group_counts)
    control_tier0 = tier_group_counts["tier0"]["control"]
    control_tier1 = tier_group_counts["tier1"]["control"]
    datapath_tier0 = tier_group_counts["tier0"]["datapath"]
    datapath_tier1 = tier_group_counts["tier1"]["datapath"]

    control_dominance = abs(control_tier0 - control_tier1) / control_total if control_total else 0.0
    datapath_dominance = abs(datapath_tier0 - datapath_tier1) / datapath_total if datapath_total else 0.0

    # A high score means control and datapath are preferentially separated
    # across tiers. It is not a universal objective, but it helps quantify
    # whether a partition preserves a functional structure rather than only a
    # numeric cut.
    architecture_separation_score = (control_dominance + datapath_dominance) / 2

    tier0_top_arch = tier_arch_counts["tier0"].most_common(1)[0][0] if tier_arch_counts["tier0"] else "none"
    tier1_top_arch = tier_arch_counts["tier1"].most_common(1)[0][0] if tier_arch_counts["tier1"] else "none"

    return {
        "design": design,
        "case": case,
        "assignment_file": str(assignment_path),
        "total_instances": tier_counts["tier0"] + tier_counts["tier1"],
        "tier0_instances": tier_counts["tier0"],
        "tier1_instances": tier_counts["tier1"],
        "instance_balance_ratio": f"{balance_ratio(tier_counts['tier0'], tier_counts['tier1']):.6f}",
        "tier0_weight": tier_weights["tier0"],
        "tier1_weight": tier_weights["tier1"],
        "weight_balance_ratio": f"{balance_ratio(tier_weights['tier0'], tier_weights['tier1']):.6f}",
        "crossing_nets": crossing_nets,
        "crossing_connections_proxy": crossing_connections_proxy,
        "weighted_crossing_proxy": weighted_crossing_proxy,
        "total_net_connections": total_net_connections,
        "crossing_connection_fraction": f"{crossing_connections_proxy / total_net_connections if total_net_connections else 0.0:.6f}",
        "control_datapath_crossing_nets": control_datapath_crossing_nets,
        "control_dominance": f"{control_dominance:.6f}",
        "datapath_dominance": f"{datapath_dominance:.6f}",
        "architecture_separation_score": f"{architecture_separation_score:.6f}",
        "tier0_top_arch_class": tier0_top_arch,
        "tier1_top_arch_class": tier1_top_arch,
    }


def parse_assignment_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        path = Path(spec)
        return path.stem, path
    name, path = spec.split("=", 1)
    return name, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--assignment", action="append", required=True, help="CASE=assignment.csv")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    instances, net_to_instances = load_features(args.features_dir)
    rows = []
    for spec in args.assignment:
        case, path = parse_assignment_spec(spec)
        rows.append(evaluate_assignment(args.design, case, path, instances, net_to_instances))

    fields = [
        "design",
        "case",
        "assignment_file",
        "total_instances",
        "tier0_instances",
        "tier1_instances",
        "instance_balance_ratio",
        "tier0_weight",
        "tier1_weight",
        "weight_balance_ratio",
        "crossing_nets",
        "crossing_connections_proxy",
        "weighted_crossing_proxy",
        "total_net_connections",
        "crossing_connection_fraction",
        "control_datapath_crossing_nets",
        "control_dominance",
        "datapath_dominance",
        "architecture_separation_score",
        "tier0_top_arch_class",
        "tier1_top_arch_class",
    ]
    write_csv(args.output, rows, fields)

    manifest = {
        "design": args.design,
        "features_dir": str(args.features_dir),
        "assignments": args.assignment,
        "output": str(args.output),
        "metric_note": "Metrics are lightweight proxies for partition comparison, not full 3D PPA signoff.",
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(args.output)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
