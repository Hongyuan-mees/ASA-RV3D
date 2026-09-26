#!/usr/bin/env python3
"""Report crossing counts using the shared Phase-3 net graph loader."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.net_graph_utils import assignment_tiers, crossing_stats, load_feature_net_graph, normalize_instance_name, read_csv  # noqa: E402


def parse_assignment(value: str) -> tuple[str, Path]:
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


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--assignment", action="append", required=True, type=parse_assignment)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for label, assignment in args.assignment:
        tiers = assignment_tiers(assignment)
        graph = load_feature_net_graph(args.features, exact_assignment_instances(assignment))
        crossing_nets, crossing_connections = crossing_stats(tiers, graph.net_to_instances)
        rows.append(
            {
                "design": args.design,
                "case": label,
                "assignment_file": str(assignment),
                "feature_nets": len(graph.net_to_instances),
                "feature_instances_with_nets": len(graph.inst_to_nets),
                "crossing_nets": crossing_nets,
                "crossing_connections_proxy": crossing_connections,
            }
        )
    write_csv(args.output, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
