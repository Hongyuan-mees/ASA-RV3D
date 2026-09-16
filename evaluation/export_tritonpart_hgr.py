#!/usr/bin/env python3
"""Export ASA-RV3D feature CSVs to a TritonPart hypergraph baseline.

The output hypergraph uses the simple hMETIS-style format accepted by
OpenROAD/TritonPart:

  <num_hyperedges> <num_vertices>
  <vertex_id> <vertex_id> ...

Vertex ids are one-based. The emitted vertex_map.csv preserves the mapping from
TritonPart vertex order back to gate-level instance names.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def instance_weight(row: dict[str, str]) -> int:
    category = row.get("cell_category", row.get("category", ""))
    try:
        net_count = int(row.get("net_count", "0") or 0)
    except ValueError:
        net_count = 0
    base = 2 if category == "sequential" else 1
    return base + min(net_count, 8)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--min-net-size", type=int, default=2)
    parser.add_argument("--max-net-size", type=int, default=0, help="0 means no upper bound")
    args = parser.parse_args()

    features_dir = args.features_dir or Path("results") / f"{args.design}_features"
    output_dir = args.output_dir or Path("results") / f"{args.design}_tritonpart_baseline"
    rows = read_csv(features_dir / "instance_features.csv")
    mapping_path = features_dir / "architecture_mapping_instances.csv"
    mapping = {row["instance"]: row for row in read_csv(mapping_path)} if mapping_path.exists() else {}

    instances = sorted(row["instance"] for row in rows)
    vertex_id = {name: idx + 1 for idx, name in enumerate(instances)}
    feature_by_name = {row["instance"]: row for row in rows}

    nets: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        name = row["instance"]
        for net in row.get("nets", "").split(";"):
            if net:
                nets[net].add(vertex_id[name])

    hyperedges = []
    for net, vertices in sorted(nets.items()):
        size = len(vertices)
        if size < args.min_net_size:
            continue
        if args.max_net_size and size > args.max_net_size:
            continue
        hyperedges.append((net, sorted(vertices)))

    output_dir.mkdir(parents=True, exist_ok=True)
    hgr_path = output_dir / f"{args.design}.hgr"
    with hgr_path.open("w", encoding="utf-8") as handle:
        handle.write(f"{len(hyperedges)} {len(instances)}\n")
        for _, vertices in hyperedges:
            handle.write(" ".join(str(v) for v in vertices) + "\n")

    map_rows = []
    for name in instances:
        feature = feature_by_name[name]
        mapped = mapping.get(name, {})
        map_rows.append(
            {
                "vertex_id": vertex_id[name],
                "instance": name,
                "architecture_unit": mapped.get("architecture_unit", "unclassified"),
                "semantic_group": mapped.get("semantic_group", "infrastructure"),
                "weight": instance_weight(feature),
            }
        )
    write_csv(
        output_dir / "vertex_map.csv",
        map_rows,
        ["vertex_id", "instance", "architecture_unit", "semantic_group", "weight"],
    )

    tcl_path = output_dir / "run_tritonpart.tcl"
    tcl_path.write_text(
        "\n".join(
            [
                f"triton_part_hypergraph -hypergraph_file /work/rv3d_tritonpart/{args.design}.hgr -num_parts 2 -balance_constraint 2 -seed 0",
                "exit",
                "",
            ]
        ),
        encoding="utf-8",
    )

    manifest = {
        "design": args.design,
        "features_dir": str(features_dir),
        "output_dir": str(output_dir),
        "instance_count": len(instances),
        "hyperedge_count": len(hyperedges),
        "min_net_size": args.min_net_size,
        "max_net_size": args.max_net_size,
        "outputs": [str(hgr_path), str(output_dir / "vertex_map.csv"), str(tcl_path)],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(hgr_path)
    print(output_dir / "vertex_map.csv")
    print(tcl_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
