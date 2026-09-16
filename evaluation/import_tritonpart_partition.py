#!/usr/bin/env python3
"""Convert TritonPart .part.2 output to an ASA-RV3D assignment CSV."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--baseline-dir", type=Path)
    parser.add_argument("--part-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    baseline_dir = args.baseline_dir or Path("results") / f"{args.design}_tritonpart_baseline"
    vertex_map_path = baseline_dir / "vertex_map.csv"
    part_path = args.part_file or baseline_dir / f"{args.design}.hgr.part.2"
    output_path = args.output or baseline_dir / "tritonpart_assignment.csv"

    vertex_rows = read_csv(vertex_map_path)
    parts = [line.strip() for line in part_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(parts) != len(vertex_rows):
        raise ValueError(f"part line count {len(parts)} does not match vertex count {len(vertex_rows)}")

    assignment_rows = []
    counts = Counter()
    for row, part in zip(vertex_rows, parts):
        tier = "tier0" if part == "0" else "tier1"
        counts[tier] += 1
        assignment_rows.append(
            {
                "instance": row["instance"],
                "tier": tier,
                "architecture_unit": row["architecture_unit"],
                "semantic_group": row["semantic_group"],
                "weight": row["weight"],
            }
        )

    write_csv(output_path, assignment_rows, ["instance", "tier", "architecture_unit", "semantic_group", "weight"])
    manifest = {
        "design": args.design,
        "vertex_map": str(vertex_map_path),
        "part_file": str(part_path),
        "output": str(output_path),
        "tier0_instances": counts["tier0"],
        "tier1_instances": counts["tier1"],
    }
    (baseline_dir / "tritonpart_assignment_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
