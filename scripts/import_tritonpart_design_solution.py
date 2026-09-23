#!/usr/bin/env python3
"""Import an OpenROAD triton_part_design solution as an RV3D assignment.

The OpenROAD `triton_part_design` solution file uses design-object names and a
partition id. RV3D evaluation scripts expect assignment rows keyed by the
instances from the existing feature/assignment CSVs. This importer maps the
OpenROAD names back to a reference RV3D assignment and preserves the reference
metadata columns such as architecture_unit, semantic_group, and weight.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path


def normalize_variants(name: str) -> set[str]:
    out = {name}
    if "$" in name:
        out.add(name.split("$", 1)[0])

    for item in list(out):
        out.add(item.replace("\\", ""))
        out.add(item.replace("/", "."))
        out.add(item.replace(".", "/"))
        out.add(item.replace("[", "_").replace("]", ""))
        out.add(item.replace(".", "_").replace("[", "_").replace("]", ""))

    more = set()
    for item in out:
        more.add(re.sub(r"\$.*$", "", item))
        more.add(re.sub(r"[^A-Za-z0-9]+", "_", item).strip("_"))
    out |= more
    return {x for x in out if x}


def read_solution(path: Path) -> dict[str, str]:
    solution: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                solution[parts[0]] = parts[1]
    return solution


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def part_to_tier(part: str, ordered_parts: list[str]) -> str:
    if part == "0":
        return "tier0"
    if part == "1":
        return "tier1"
    if part in ordered_parts:
        return f"tier{ordered_parts.index(part)}"
    raise RuntimeError(f"Unexpected partition id: {part}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", required=True, type=Path)
    parser.add_argument("--reference-assignment", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mapping-report", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--allow-reference-fallback",
        action="store_true",
        help="Use the reference tier for ambiguous or unmatched rows.",
    )
    args = parser.parse_args()

    solution = read_solution(args.solution)
    reference_rows = read_csv(args.reference_assignment)
    if not reference_rows or "instance" not in reference_rows[0]:
        raise RuntimeError("reference assignment must contain an instance column")

    ordered_parts = sorted(set(solution.values()), key=lambda x: (len(x), x))
    solution_names = set(solution)

    variant_index: dict[str, list[str]] = {}
    for sol_name in solution_names:
        for key in normalize_variants(sol_name):
            variant_index.setdefault(key, []).append(sol_name)

    output_rows: list[dict[str, str]] = []
    report_rows: list[dict[str, str]] = []
    status_counts: Counter[str] = Counter()

    for row in reference_rows:
        instance = row["instance"]
        matched_name = ""
        part = ""
        status = ""

        if instance in solution:
            matched_name = instance
            part = solution[matched_name]
            status = "exact"
        else:
            hits: list[str] = []
            for key in normalize_variants(instance):
                hits.extend(variant_index.get(key, []))
            hits = sorted(set(hits))
            if len(hits) == 1:
                matched_name = hits[0]
                part = solution[matched_name]
                status = "normalized_unique"
            elif len(hits) > 1:
                exact_like = [hit for hit in hits if hit == instance]
                if len(exact_like) == 1:
                    matched_name = exact_like[0]
                    part = solution[matched_name]
                    status = "ambiguous_exact_like"
                elif args.allow_reference_fallback:
                    status = "fallback_reference_ambiguous"
                else:
                    raise RuntimeError(
                        f"Ambiguous mapping for {instance}: {', '.join(hits[:8])}"
                    )
            elif args.allow_reference_fallback:
                status = "fallback_reference_unmatched"
            else:
                raise RuntimeError(f"No mapping for {instance}")

        out = dict(row)
        if part:
            out["tier"] = part_to_tier(part, ordered_parts)
        else:
            out["tier"] = row.get("tier", "")
        output_rows.append(out)

        report_rows.append(
            {
                "instance": instance,
                "matched_solution_name": matched_name,
                "solution_part": part,
                "imported_tier": out["tier"],
                "reference_tier": row.get("tier", ""),
                "status": status,
            }
        )
        status_counts[status] += 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    if args.mapping_report:
        args.mapping_report.parent.mkdir(parents=True, exist_ok=True)
        with args.mapping_report.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            writer.writeheader()
            writer.writerows(report_rows)

    manifest = {
        "solution": str(args.solution),
        "reference_assignment": str(args.reference_assignment),
        "output": str(args.output),
        "solution_rows": len(solution),
        "reference_rows": len(reference_rows),
        "solution_partition_ids": ordered_parts,
        "status_counts": dict(status_counts),
        "fallback_rows": sum(
            count for status, count in status_counts.items() if status.startswith("fallback")
        ),
        "note": (
            "OpenROAD triton_part_design solution imported into RV3D assignment "
            "space. Fallback rows retain the reference tier and should be "
            "reported if nonzero."
        ),
    }
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(args.output)
    if args.mapping_report:
        print(args.mapping_report)
    if args.manifest:
        print(args.manifest)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
