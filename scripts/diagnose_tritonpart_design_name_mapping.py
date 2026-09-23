#!/usr/bin/env python3
"""Diagnose name mapping between OpenROAD triton_part_design and RV3D.

This script is intentionally read-only. It helps decide whether a native
OpenROAD TritonPart solution can be imported fairly into RV3D assignment CSVs.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter
from pathlib import Path


def read_solution_names(path: Path) -> set[str]:
    names: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                names.add(parts[0])
    return names


def read_instances(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "instance" not in (reader.fieldnames or []):
            raise RuntimeError(f"{path} has no instance column")
        return [row["instance"] for row in reader if row.get("instance")]


def variants(name: str) -> set[str]:
    out = {name}
    base = name

    if "$" in base:
        out.add(base.split("$", 1)[0])

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


def classify(name: str) -> str:
    if name in {"VDD", "VSS", "VPWR", "VGND"}:
        return "power_or_ground"
    if name.startswith("ANTENNA"):
        return "antenna"
    if "$" in name:
        return "generated_cell"
    if "[" in name and "]" in name and "." not in name and "/" not in name:
        return "bus_signal_or_port"
    if "." in name or "/" in name:
        return "hierarchical_name"
    return "flat_name"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", required=True, type=Path)
    parser.add_argument("--reference-assignment", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    solution_names = read_solution_names(args.solution)
    reference_names = read_instances(args.reference_assignment)
    reference_set = set(reference_names)

    solution_variant_index: dict[str, list[str]] = {}
    for name in solution_names:
        for key in variants(name):
            solution_variant_index.setdefault(key, []).append(name)

    exact = reference_set & solution_names
    normalized_matches: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for ref in reference_names:
        if ref in solution_names:
            normalized_matches[ref] = ref
            continue
        hits: list[str] = []
        for key in variants(ref):
            hits.extend(solution_variant_index.get(key, []))
        hits = sorted(set(hits))
        if len(hits) == 1:
            normalized_matches[ref] = hits[0]
        elif len(hits) > 1:
            ambiguous[ref] = hits

    unmatched = [name for name in reference_names if name not in normalized_matches]
    solution_extra = sorted(solution_names - reference_set)

    print("solution_rows", len(solution_names))
    print("reference_rows", len(reference_names))
    print("exact_matches", len(exact))
    print("exact_match_fraction", f"{len(exact) / max(len(reference_names), 1):.6f}")
    print("normalized_unique_matches", len(normalized_matches))
    print(
        "normalized_unique_match_fraction",
        f"{len(normalized_matches) / max(len(reference_names), 1):.6f}",
    )
    print("ambiguous_reference_names", len(ambiguous))
    print("unmatched_reference_names", len(unmatched))
    print()
    print("solution_extra_category_counts")
    for category, count in Counter(classify(name) for name in solution_extra).most_common():
        print(category, count)
    print()
    print("sample_normalized_matches")
    for ref, sol in list(normalized_matches.items())[:20]:
        if ref != sol:
            print(f"{ref} -> {sol}")
    print()
    print("sample_unmatched_reference_names")
    for name in unmatched[:30]:
        print(name)
    print()
    print("sample_ambiguous_reference_names")
    for ref, hits in list(ambiguous.items())[:10]:
        print(f"{ref} -> {', '.join(hits[:5])}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["reference_instance", "matched_solution_name", "status"],
            )
            writer.writeheader()
            for ref in reference_names:
                if ref in normalized_matches:
                    writer.writerow(
                        {
                            "reference_instance": ref,
                            "matched_solution_name": normalized_matches[ref],
                            "status": "unique",
                        }
                    )
                elif ref in ambiguous:
                    writer.writerow(
                        {
                            "reference_instance": ref,
                            "matched_solution_name": ";".join(ambiguous[ref]),
                            "status": "ambiguous",
                        }
                    )
                else:
                    writer.writerow(
                        {
                            "reference_instance": ref,
                            "matched_solution_name": "",
                            "status": "unmatched",
                        }
                    )
        print()
        print(args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
