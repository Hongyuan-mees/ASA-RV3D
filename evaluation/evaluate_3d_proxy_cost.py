#!/usr/bin/env python3
"""Evaluate RISC-V-aware 3D proxy cost for tier assignments.

This script upgrades the simple crossing metric into an architecture-aware
3D proxy cost. It does not claim to compute real TSV count, timing, power, or
thermal behavior. Instead, it asks a more useful early-stage question:

    Which architecture-relevant nets cross tiers, and how expensive do those
    crossings look under a lightweight RISC-V-aware proxy model?

The model is intentionally transparent. Each crossing net receives a base
crossing cost, plus interpretable penalties for high fanout, clock/reset,
register/pipeline state, load/store, and control-datapath boundaries. Optional
graph-context scores add an uncertainty term for semantically weak regions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


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

ARCH_CLASS_WEIGHTS = {
    "clock_reset": 5.0,
    "register_file": 4.0,
    "load_store": 3.5,
    "pipeline_state": 3.0,
    "csr": 2.5,
    "fetch": 2.0,
    "decode_control": 2.0,
    "trap_debug": 2.0,
    "execute_alu": 2.0,
    "multdiv": 2.0,
    "generated_datapath": 1.5,
    "generated_control": 1.2,
    "unclassified": 1.0,
}

DEFAULT_WEIGHTS = {
    "base_crossing": 1.0,
    "high_fanout": 0.25,
    "control_datapath_boundary": 2.0,
    "arch_criticality": 1.0,
    "semantic_uncertainty": 1.0,
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
    if arch_class in {"unclassified", "other", "", "unknown"}:
        return "unknown"
    return "other"


def balance_ratio(a: int, b: int) -> float:
    high = max(a, b)
    low = min(a, b)
    return low / high if high else 1.0


def float_or_default(value: str | None, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def load_context_scores(features_dir: Path) -> dict[str, float]:
    path = features_dir / "graph_context_scores.csv"
    if not path.exists():
        return {}
    scores: dict[str, float] = {}
    for row in read_csv(path):
        scores[row["instance"]] = float_or_default(row.get("semantic_context_score"), 0.5)
    return scores


def load_features(
    features_dir: Path,
) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], dict[str, float]]:
    feature_rows = read_csv(features_dir / "instance_features.csv")
    arch_path = features_dir / "architecture_instance_classes.csv"
    arch_by_instance: dict[str, dict[str, str]] = {}
    if arch_path.exists():
        arch_by_instance = {row["instance"]: row for row in read_csv(arch_path)}

    context_scores = load_context_scores(features_dir)
    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)

    for row in feature_rows:
        inst = row["instance"]
        arch = arch_by_instance.get(inst, {})
        architecture_class = arch.get("architecture_class") or row.get("architecture_class") or row.get("arch_class") or "unclassified"
        enriched = dict(row)
        enriched["architecture_class"] = architecture_class
        enriched["semantic_group"] = semantic_group(architecture_class)
        enriched["semantic_context_score"] = f"{context_scores.get(inst, 0.5):.6f}"
        instances[inst] = enriched

        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)

    return instances, net_to_instances, context_scores


def load_assignment(path: Path) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for row in read_csv(path):
        assignment[row["instance"]] = row["tier"]
    return assignment


def parse_assignment_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        path = Path(spec)
        return path.stem, path
    name, path = spec.split("=", 1)
    return name, Path(path)


def max_arch_weight(classes: Iterable[str]) -> float:
    return max((ARCH_CLASS_WEIGHTS.get(cls, 1.0) for cls in classes), default=1.0)


def evaluate_assignment(
    design: str,
    case: str,
    assignment_path: Path,
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
    weights: dict[str, float],
) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
    assignment = load_assignment(assignment_path)

    tier_counts = Counter()
    tier_weights = Counter()
    for inst, tier in assignment.items():
        row = instances.get(inst)
        if not row:
            continue
        inst_weight = max(1, int(row.get("net_count", "0") or 0))
        tier_counts[tier] += 1
        tier_weights[tier] += inst_weight

    totals = Counter()
    class_cost = Counter()
    net_rows: list[dict[str, object]] = []

    for net, connected_all in net_to_instances.items():
        connected = [inst for inst in connected_all if inst in assignment and inst in instances]
        if not connected:
            continue

        tiers = Counter(assignment[inst] for inst in connected)
        total_connections = len(connected)
        totals["total_net_connections"] += total_connections

        if len(tiers) <= 1:
            continue

        minority = min(tiers.values())
        classes = {instances[inst]["architecture_class"] for inst in connected}
        groups = {instances[inst]["semantic_group"] for inst in connected}
        context_values = [float_or_default(instances[inst].get("semantic_context_score"), 0.5) for inst in connected]
        mean_context = sum(context_values) / len(context_values) if context_values else 0.5

        base_cost = minority * weights["base_crossing"]
        high_fanout_cost = minority * max(0, total_connections - 8) * weights["high_fanout"]
        boundary_cost = minority * weights["control_datapath_boundary"] if {"control", "datapath"}.issubset(groups) else 0.0
        arch_cost = minority * max_arch_weight(classes) * weights["arch_criticality"]
        uncertainty_cost = minority * (1.0 - mean_context) * weights["semantic_uncertainty"]
        total_cost = base_cost + high_fanout_cost + boundary_cost + arch_cost + uncertainty_cost

        totals["crossing_nets"] += 1
        totals["crossing_connections_proxy"] += minority
        totals["base_crossing_cost"] += base_cost
        totals["high_fanout_cost"] += high_fanout_cost
        totals["control_datapath_boundary_cost"] += boundary_cost
        totals["arch_criticality_cost"] += arch_cost
        totals["semantic_uncertainty_cost"] += uncertainty_cost
        totals["riscv_3d_proxy_cost"] += total_cost

        for cls in classes:
            class_cost[cls] += total_cost / max(1, len(classes))

        net_rows.append(
            {
                "design": design,
                "case": case,
                "net": net,
                "total_connections": total_connections,
                "crossing_connections_proxy": minority,
                "tier0_connections": tiers["tier0"],
                "tier1_connections": tiers["tier1"],
                "architecture_classes": ";".join(sorted(classes)),
                "semantic_groups": ";".join(sorted(groups)),
                "mean_semantic_context_score": f"{mean_context:.6f}",
                "base_crossing_cost": f"{base_cost:.6f}",
                "high_fanout_cost": f"{high_fanout_cost:.6f}",
                "control_datapath_boundary_cost": f"{boundary_cost:.6f}",
                "arch_criticality_cost": f"{arch_cost:.6f}",
                "semantic_uncertainty_cost": f"{uncertainty_cost:.6f}",
                "riscv_3d_proxy_cost": f"{total_cost:.6f}",
            }
        )

    top_net_rows = sorted(
        net_rows,
        key=lambda row: float(row["riscv_3d_proxy_cost"]),
        reverse=True,
    )[:50]

    class_rows = [
        {
            "design": design,
            "case": case,
            "architecture_class": cls,
            "riscv_3d_proxy_cost": f"{cost:.6f}",
        }
        for cls, cost in class_cost.most_common()
    ]

    total_connections = totals["total_net_connections"]
    summary = {
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
        "crossing_nets": totals["crossing_nets"],
        "crossing_connections_proxy": totals["crossing_connections_proxy"],
        "crossing_connection_fraction": f"{totals['crossing_connections_proxy'] / total_connections if total_connections else 0.0:.6f}",
        "base_crossing_cost": f"{totals['base_crossing_cost']:.6f}",
        "high_fanout_cost": f"{totals['high_fanout_cost']:.6f}",
        "control_datapath_boundary_cost": f"{totals['control_datapath_boundary_cost']:.6f}",
        "arch_criticality_cost": f"{totals['arch_criticality_cost']:.6f}",
        "semantic_uncertainty_cost": f"{totals['semantic_uncertainty_cost']:.6f}",
        "riscv_3d_proxy_cost": f"{totals['riscv_3d_proxy_cost']:.6f}",
        "normalized_riscv_3d_proxy_cost": f"{totals['riscv_3d_proxy_cost'] / total_connections if total_connections else 0.0:.6f}",
    }

    return summary, class_rows, top_net_rows


def add_reductions(rows: list[dict[str, object]]) -> None:
    by_design: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["case"] in {"generic", "generic_balance"}:
            by_design[str(row["design"])] = row

    for row in rows:
        generic = by_design.get(str(row["design"]))
        if not generic:
            row["reduction_vs_generic_3d_proxy"] = ""
            continue
        base = float(generic["riscv_3d_proxy_cost"])
        current = float(row["riscv_3d_proxy_cost"])
        row["reduction_vs_generic_3d_proxy"] = f"{(base - current) / base if base else 0.0:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--assignment", action="append", required=True, help="CASE=assignment.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-crossing-weight", type=float, default=DEFAULT_WEIGHTS["base_crossing"])
    parser.add_argument("--high-fanout-weight", type=float, default=DEFAULT_WEIGHTS["high_fanout"])
    parser.add_argument("--boundary-weight", type=float, default=DEFAULT_WEIGHTS["control_datapath_boundary"])
    parser.add_argument("--arch-criticality-weight", type=float, default=DEFAULT_WEIGHTS["arch_criticality"])
    parser.add_argument("--semantic-uncertainty-weight", type=float, default=DEFAULT_WEIGHTS["semantic_uncertainty"])
    args = parser.parse_args()

    weights = {
        "base_crossing": args.base_crossing_weight,
        "high_fanout": args.high_fanout_weight,
        "control_datapath_boundary": args.boundary_weight,
        "arch_criticality": args.arch_criticality_weight,
        "semantic_uncertainty": args.semantic_uncertainty_weight,
    }

    instances, net_to_instances, context_scores = load_features(args.features_dir)
    summary_rows: list[dict[str, object]] = []
    class_rows: list[dict[str, object]] = []
    top_net_rows: list[dict[str, object]] = []

    for spec in args.assignment:
        case, assignment_path = parse_assignment_spec(spec)
        summary, class_breakdown, top_nets = evaluate_assignment(
            args.design,
            case,
            assignment_path,
            instances,
            net_to_instances,
            weights,
        )
        summary_rows.append(summary)
        class_rows.extend(class_breakdown)
        top_net_rows.extend(top_nets)

    add_reductions(summary_rows)

    summary_fields = [
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
        "crossing_connection_fraction",
        "base_crossing_cost",
        "high_fanout_cost",
        "control_datapath_boundary_cost",
        "arch_criticality_cost",
        "semantic_uncertainty_cost",
        "riscv_3d_proxy_cost",
        "normalized_riscv_3d_proxy_cost",
        "reduction_vs_generic_3d_proxy",
    ]
    class_fields = ["design", "case", "architecture_class", "riscv_3d_proxy_cost"]
    net_fields = [
        "design",
        "case",
        "net",
        "total_connections",
        "crossing_connections_proxy",
        "tier0_connections",
        "tier1_connections",
        "architecture_classes",
        "semantic_groups",
        "mean_semantic_context_score",
        "base_crossing_cost",
        "high_fanout_cost",
        "control_datapath_boundary_cost",
        "arch_criticality_cost",
        "semantic_uncertainty_cost",
        "riscv_3d_proxy_cost",
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / f"{args.design}_3d_proxy_cost_summary.csv"
    class_path = args.output_dir / f"{args.design}_3d_proxy_class_breakdown.csv"
    top_net_path = args.output_dir / f"{args.design}_3d_proxy_top_crossing_nets.csv"

    write_csv(summary_path, summary_rows, summary_fields)
    write_csv(class_path, class_rows, class_fields)
    write_csv(top_net_path, top_net_rows, net_fields)

    manifest = {
        "design": args.design,
        "features_dir": str(args.features_dir),
        "assignments": args.assignment,
        "outputs": [str(summary_path), str(class_path), str(top_net_path)],
        "weights": weights,
        "context_scores_found": bool(context_scores),
        "metric_note": "RISC-V-aware 3D proxy cost is an early-stage heuristic, not physical signoff.",
    }
    manifest_path = args.output_dir / f"{args.design}_3d_proxy_cost_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(summary_path)
    print(class_path)
    print(top_net_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
