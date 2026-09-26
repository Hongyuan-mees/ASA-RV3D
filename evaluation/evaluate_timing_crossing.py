#!/usr/bin/env python3
"""Evaluate timing-sensitive crossing nets with the shared Phase-3 net graph.

This evaluator keeps the existing command-line interface used by the RV3D
scripts while using `evaluation/net_graph_utils.py` for feature-net loading,
instance normalization, and crossing counts.  The goal is for paper-facing
crossing numbers to match the optimizer cut guard.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.net_graph_utils import (  # noqa: E402
    assignment_tiers,
    build_assignment_aliases,
    crossing_stats,
    load_feature_net_graph,
    net_is_crossing,
    normalize_instance_name,
    read_csv,
    resolve_instance,
)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "design",
        "case",
        "crossing_nets",
        "timing_crossing_nets",
        "timing_crossing_net_fraction",
        "high_timing_crossing_nets",
        "timing_weighted_crossing",
        "top_timing_crossing_unit",
        "top_timing_crossing_unit_hits",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def as_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_assignment_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--assignment must be label=path")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("assignment label cannot be empty")
    return label, Path(path)


def exact_assignment_instances(path: Path) -> set[str]:
    instances: set[str] = set()
    for row in read_csv(path):
        inst = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        if inst:
            instances.add(normalize_instance_name(inst))
    return instances


def load_timing_context(path: Path, assignment_instances: set[str]) -> tuple[dict[str, float], dict[str, str]]:
    aliases = build_assignment_aliases(assignment_instances)
    scores: dict[str, float] = {}
    units: dict[str, str] = {}
    score_columns = [
        "timing_context_score",
        "mean_timing_context_score",
        "score",
        "timing_score",
    ]
    unit_columns = [
        "architecture_unit",
        "arch_unit",
        "semantic_unit",
        "architecture_group",
        "unit",
        "category",
        "arch_class",
    ]
    for row in read_csv(path):
        raw = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        inst = resolve_instance(raw, aliases)
        if not inst:
            continue
        score = 0.0
        for column in score_columns:
            if row.get(column) not in (None, ""):
                score = as_float(row.get(column))
                break
        unit = "unclassified"
        for column in unit_columns:
            if row.get(column):
                unit = str(row[column])
                break
        scores[inst] = score
        units[inst] = unit
    return scores, units


def summarize_assignment(
    *,
    design: str,
    case: str,
    assignment: Path,
    features_dir: Path,
    timing: Path,
) -> dict[str, object]:
    instances = exact_assignment_instances(assignment)
    tiers = assignment_tiers(assignment)
    graph = load_feature_net_graph(features_dir / "instance_features.csv", instances)
    timing_scores, timing_units = load_timing_context(timing, instances)
    crossing_nets, _crossing_connections = crossing_stats(tiers, graph.net_to_instances)

    timing_crossing = 0
    high_timing_crossing = 0
    weighted = 0.0
    unit_hits: Counter[str] = Counter()

    positive_scores = [score for score in timing_scores.values() if score > 0.0]
    high_threshold = sorted(positive_scores)[int(0.9 * (len(positive_scores) - 1))] if positive_scores else 0.0

    for insts in graph.net_to_instances.values():
        if not net_is_crossing(tiers, insts):
            continue
        net_scores = [timing_scores.get(inst, 0.0) for inst in insts]
        net_weight = max(net_scores) if net_scores else 0.0
        if net_weight <= 0.0:
            continue
        timing_crossing += 1
        weighted += net_weight
        if high_threshold > 0.0 and net_weight >= high_threshold:
            high_timing_crossing += 1
        for inst in insts:
            if timing_scores.get(inst, 0.0) > 0.0:
                unit_hits[timing_units.get(inst, "unclassified") or "unclassified"] += 1

    top_unit = ""
    top_hits = 0
    if unit_hits:
        top_unit, top_hits = unit_hits.most_common(1)[0]

    return {
        "design": design,
        "case": case,
        "crossing_nets": crossing_nets,
        "timing_crossing_nets": timing_crossing,
        "timing_crossing_net_fraction": f"{timing_crossing / crossing_nets if crossing_nets else 0.0:.6f}",
        "high_timing_crossing_nets": high_timing_crossing,
        "timing_weighted_crossing": f"{weighted:.6f}",
        "top_timing_crossing_unit": top_unit,
        "top_timing_crossing_unit_hits": top_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", required=True, type=Path)
    parser.add_argument("--timing", required=True, type=Path)
    parser.add_argument("--assignment", action="append", required=True, type=parse_assignment_arg)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = [
        summarize_assignment(
            design=args.design,
            case=label,
            assignment=path,
            features_dir=args.features_dir,
            timing=args.timing,
        )
        for label, path in args.assignment
    ]
    write_csv(args.output, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
