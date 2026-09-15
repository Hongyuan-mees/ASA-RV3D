#!/usr/bin/env python3
"""Compute lightweight graph-context semantic scores for netlist instances.

This script is intentionally dependency-free. It uses the existing feature
extraction and architecture-classification CSV files, reconstructs a simple
instance-neighborhood graph from shared nets, and computes context features
that can later be used by ASA-RV3D or by a future GNN-assisted scorer.

It does not modify partition results.
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

SEQUENTIAL_CATEGORIES = {"sequential", "clock_buffer"}


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
    if arch_class == "unclassified" or arch_class == "other":
        return "unknown"
    return "other"


def safe_fraction(count: int, total: int) -> float:
    return count / total if total else 0.0


def load_instance_rows(features_dir: Path) -> list[dict[str, str]]:
    feature_path = features_dir / "instance_features.csv"
    if not feature_path.exists():
        raise FileNotFoundError(f"Missing feature file: {feature_path}")

    rows = read_csv(feature_path)

    arch_path = features_dir / "architecture_instance_classes.csv"
    if arch_path.exists():
        arch_rows = read_csv(arch_path)
        by_instance = {row["instance"]: row for row in arch_rows}
        for row in rows:
            arch = by_instance.get(row["instance"])
            if arch:
                row["architecture_class"] = arch.get("architecture_class", row.get("arch_class", "unknown"))
                row["architecture_confidence"] = arch.get("confidence", "")
            else:
                row["architecture_class"] = row.get("arch_class", "unknown")
                row["architecture_confidence"] = ""
    else:
        for row in rows:
            row["architecture_class"] = row.get("arch_class", "unknown")
            row["architecture_confidence"] = ""

    return rows


def build_net_index(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = row["instance"]
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return net_to_instances


def compute_context_scores(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    by_instance = {row["instance"]: row for row in rows}
    net_to_instances = build_net_index(rows)

    instance_to_nets: dict[str, list[str]] = defaultdict(list)
    for net, instances in net_to_instances.items():
        for inst in instances:
            instance_to_nets[inst].append(net)

    output_rows: list[dict[str, object]] = []

    for row in rows:
        inst = row["instance"]
        arch_class = row.get("architecture_class", "unknown")
        group = semantic_group(arch_class)
        category = row.get("category", "unknown")
        nets = instance_to_nets.get(inst, [])

        neighbor_counter: Counter[str] = Counter()
        neighbor_category_counter: Counter[str] = Counter()
        neighbor_group_counter: Counter[str] = Counter()
        unique_neighbors: set[str] = set()
        mixed_group_nets = 0
        high_fanout_nets = 0

        for net in nets:
            connected = [other for other in net_to_instances.get(net, []) if other != inst]
            if len(connected) >= 8:
                high_fanout_nets += 1

            groups_on_net = set()
            for other in connected:
                other_row = by_instance[other]
                other_arch = other_row.get("architecture_class", "unknown")
                other_group = semantic_group(other_arch)
                groups_on_net.add(other_group)
                unique_neighbors.add(other)
                neighbor_counter[other_arch] += 1
                neighbor_category_counter[other_row.get("category", "unknown")] += 1
                neighbor_group_counter[other_group] += 1

            if "control" in groups_on_net and "datapath" in groups_on_net:
                mixed_group_nets += 1

        total_neighbor_hits = sum(neighbor_group_counter.values())
        unique_neighbor_count = len(unique_neighbors)
        net_count = len(nets)

        control_fraction = safe_fraction(neighbor_group_counter["control"], total_neighbor_hits)
        datapath_fraction = safe_fraction(neighbor_group_counter["datapath"], total_neighbor_hits)
        unknown_fraction = safe_fraction(neighbor_group_counter["unknown"], total_neighbor_hits)
        sequential_fraction = safe_fraction(
            sum(neighbor_category_counter[item] for item in SEQUENTIAL_CATEGORIES),
            total_neighbor_hits,
        )

        same_group_fraction = safe_fraction(neighbor_group_counter[group], total_neighbor_hits)
        opposite_group = "datapath" if group == "control" else "control" if group == "datapath" else ""
        opposite_group_fraction = safe_fraction(neighbor_group_counter[opposite_group], total_neighbor_hits)

        mixed_net_fraction = safe_fraction(mixed_group_nets, net_count)
        high_fanout_fraction = safe_fraction(high_fanout_nets, net_count)

        # A simple explainable score: nodes with many opposite-group neighbors
        # and mixed control/datapath nets are more likely to sit near semantic
        # boundaries and may be important for tier crossing decisions.
        boundary_likelihood_score = (
            0.50 * opposite_group_fraction
            + 0.35 * mixed_net_fraction
            + 0.15 * high_fanout_fraction
        )

        # A context confidence score: high when the local graph neighborhood
        # agrees with the current semantic group and low when it is isolated or
        # surrounded by a different group.
        semantic_context_score = (
            0.70 * same_group_fraction
            + 0.20 * (1.0 - unknown_fraction)
            + 0.10 * min(1.0, unique_neighbor_count / 8.0)
        )

        top_neighbor_arch = neighbor_counter.most_common(1)[0][0] if neighbor_counter else "none"
        top_neighbor_group = neighbor_group_counter.most_common(1)[0][0] if neighbor_group_counter else "none"

        output_rows.append(
            {
                "module": row.get("module", ""),
                "instance": inst,
                "cell_type": row.get("cell_type", ""),
                "cell_category": category,
                "architecture_class": arch_class,
                "semantic_group": group,
                "architecture_confidence": row.get("architecture_confidence", ""),
                "net_count": net_count,
                "unique_neighbor_count": unique_neighbor_count,
                "neighbor_hit_count": total_neighbor_hits,
                "control_neighbor_fraction": f"{control_fraction:.6f}",
                "datapath_neighbor_fraction": f"{datapath_fraction:.6f}",
                "sequential_neighbor_fraction": f"{sequential_fraction:.6f}",
                "same_group_neighbor_fraction": f"{same_group_fraction:.6f}",
                "opposite_group_neighbor_fraction": f"{opposite_group_fraction:.6f}",
                "mixed_group_net_fraction": f"{mixed_net_fraction:.6f}",
                "high_fanout_net_fraction": f"{high_fanout_fraction:.6f}",
                "boundary_likelihood_score": f"{boundary_likelihood_score:.6f}",
                "semantic_context_score": f"{semantic_context_score:.6f}",
                "top_neighbor_architecture_class": top_neighbor_arch,
                "top_neighbor_semantic_group": top_neighbor_group,
            }
        )

    return output_rows


def summarize(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_arch: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_group[str(row["semantic_group"])].append(row)
        by_arch[str(row["architecture_class"])].append(row)

    summary_rows: list[dict[str, object]] = []

    def mean(items: list[dict[str, object]], field: str) -> float:
        return sum(float(item[field]) for item in items) / len(items) if items else 0.0

    for key, items in sorted(by_group.items()):
        summary_rows.append(
            {
                "summary_type": "semantic_group",
                "name": key,
                "instance_count": len(items),
                "mean_boundary_likelihood_score": f"{mean(items, 'boundary_likelihood_score'):.6f}",
                "mean_semantic_context_score": f"{mean(items, 'semantic_context_score'):.6f}",
                "mean_unique_neighbor_count": f"{mean(items, 'unique_neighbor_count'):.3f}",
            }
        )

    for key, items in sorted(by_arch.items()):
        summary_rows.append(
            {
                "summary_type": "architecture_class",
                "name": key,
                "instance_count": len(items),
                "mean_boundary_likelihood_score": f"{mean(items, 'boundary_likelihood_score'):.6f}",
                "mean_semantic_context_score": f"{mean(items, 'semantic_context_score'):.6f}",
                "mean_unique_neighbor_count": f"{mean(items, 'unique_neighbor_count'):.3f}",
            }
        )

    return summary_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    features_dir = args.features_dir.resolve()
    output_dir = (args.output_dir or features_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    instance_rows = load_instance_rows(features_dir)
    context_rows = compute_context_scores(instance_rows)
    summary_rows = summarize(context_rows)

    context_fields = [
        "module",
        "instance",
        "cell_type",
        "cell_category",
        "architecture_class",
        "semantic_group",
        "architecture_confidence",
        "net_count",
        "unique_neighbor_count",
        "neighbor_hit_count",
        "control_neighbor_fraction",
        "datapath_neighbor_fraction",
        "sequential_neighbor_fraction",
        "same_group_neighbor_fraction",
        "opposite_group_neighbor_fraction",
        "mixed_group_net_fraction",
        "high_fanout_net_fraction",
        "boundary_likelihood_score",
        "semantic_context_score",
        "top_neighbor_architecture_class",
        "top_neighbor_semantic_group",
    ]
    summary_fields = [
        "summary_type",
        "name",
        "instance_count",
        "mean_boundary_likelihood_score",
        "mean_semantic_context_score",
        "mean_unique_neighbor_count",
    ]

    write_csv(output_dir / "graph_context_scores.csv", context_rows, context_fields)
    write_csv(output_dir / "graph_context_summary.csv", summary_rows, summary_fields)

    manifest = {
        "features_dir": str(features_dir),
        "output_dir": str(output_dir),
        "instance_count": len(context_rows),
        "outputs": [
            "graph_context_scores.csv",
            "graph_context_summary.csv",
            "graph_context_manifest.json",
        ],
        "description": "Lightweight graph-context semantic scores derived from shared-net neighborhoods.",
    }
    (output_dir / "graph_context_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(output_dir / "graph_context_scores.csv")
    print(output_dir / "graph_context_summary.csv")
    print(output_dir / "graph_context_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
