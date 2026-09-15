#!/usr/bin/env python3
"""Diagnose instance-to-DEF component matching quality.

Physical-aware features are only useful if feature CSV instance names can be
matched to DEF component names.  This script audits the matching problem before
physical features are used by partitioning.

Outputs:
  results/<design>_features/def_matching_diagnosis_summary.csv
  results/<design>_features/def_matching_unmatched_by_unit.csv
  results/<design>_features/def_matching_unmatched_patterns.csv
  results/<design>_features/def_matching_candidate_examples.csv
  results/<design>_features/def_matching_diagnosis_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


GENERATED_ESCAPED_RE = re.compile(r"^\*\d+\*$")
DIGIT_ONLY_RE = re.compile(r"^\d+$")
CLOCK_LOAD_RE = re.compile(r"clk|clock|rst|reset", re.IGNORECASE)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def normalize_basic(name: str) -> str:
    out = name.strip()
    if out.startswith("\\"):
        out = out[1:]
    return out


def normalize_brackets(name: str) -> str:
    out = normalize_basic(name)
    out = out.replace("[", "_").replace("]", "_")
    out = out.replace("/", "_").replace(".", "_")
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def basename(name: str) -> str:
    out = normalize_basic(name)
    return re.split(r"[/.]", out)[-1]


def parse_def_components(def_path: Path) -> dict[str, str]:
    components: dict[str, str] = {}
    in_components = False
    current = ""
    comp_start_re = re.compile(r"^\s*-\s+(\S+)\s+(\S+)")

    with def_path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if line.startswith("COMPONENTS "):
                in_components = True
                current = ""
                continue
            if in_components and line.startswith("END COMPONENTS"):
                break
            if not in_components:
                continue
            if line.startswith("- "):
                current = line
            else:
                current += " " + line
            if ";" not in line:
                continue
            m = comp_start_re.search(current)
            if m:
                components[normalize_basic(m.group(1))] = normalize_basic(m.group(2))
            current = ""
    return components


def pattern_class(name: str) -> str:
    n = normalize_basic(name)
    b = basename(n)
    if GENERATED_ESCAPED_RE.match(n) or GENERATED_ESCAPED_RE.match(b):
        return "escaped_generated_number"
    if DIGIT_ONLY_RE.match(n) or DIGIT_ONLY_RE.match(b):
        return "digit_only"
    if CLOCK_LOAD_RE.search(n):
        return "clock_reset_name"
    if "[" in n or "]" in n:
        return "bracketed_bus_name"
    if "/" in n or "." in n:
        return "hierarchical_name"
    if n.startswith("_") or n.startswith("$"):
        return "synthetic_symbol_name"
    if re.search(r"\d", n):
        return "contains_digits"
    return "plain_name"


def best_substring_candidates(name: str, def_names: list[str], limit: int = 5) -> list[str]:
    """Return simple substring candidates for diagnosis only."""

    b = basename(name)
    norm = normalize_brackets(b)
    if len(norm) < 4:
        return []
    candidates = []
    for def_name in def_names:
        dbase = basename(def_name)
        dnorm = normalize_brackets(dbase)
        if norm == dnorm:
            candidates.append(def_name)
        elif norm in dnorm or dnorm in norm:
            candidates.append(def_name)
        if len(candidates) >= limit:
            break
    return candidates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--platform", default="sky130hd")
    parser.add_argument("--orfs-flow-dir", type=Path, default=Path("~/openroad-flow-scripts/flow"))
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--def-file", type=Path)
    args = parser.parse_args()

    flow_dir = args.orfs_flow_dir.expanduser().resolve()
    features_dir = (args.features_dir or Path("results") / f"{args.design}_features").resolve()
    def_path = (
        args.def_file.expanduser().resolve()
        if args.def_file
        else flow_dir / "results" / args.platform / args.design / "base" / "6_final.def"
    )

    feature_rows = read_csv(features_dir / "instance_features.csv")
    mapping_rows = read_csv(features_dir / "architecture_mapping_instances.csv")
    mapping = {normalize_basic(row["instance"]): row for row in mapping_rows}
    def_components = parse_def_components(def_path)
    def_names = sorted(def_components)

    exact_set = set(def_names)
    basic_set = {normalize_basic(name): name for name in def_names}
    bracket_set = {normalize_brackets(name): name for name in def_names}
    basename_set = {basename(name): name for name in def_names}
    basename_bracket_set = {normalize_brackets(basename(name)): name for name in def_names}

    summary = Counter()
    unmatched_by_unit = Counter()
    total_by_unit = Counter()
    pattern_counts = Counter()
    pattern_by_unit: dict[tuple[str, str], int] = Counter()
    examples: list[dict[str, object]] = []

    for row in feature_rows:
        inst = normalize_basic(row["instance"])
        unit = mapping.get(inst, {}).get("architecture_unit", "unclassified")
        total_by_unit[unit] += 1
        summary["total_feature_instances"] += 1

        matched_stage = ""
        if inst in exact_set:
            matched_stage = "exact"
        elif normalize_basic(inst) in basic_set:
            matched_stage = "basic"
        elif normalize_brackets(inst) in bracket_set:
            matched_stage = "bracket_normalized"
        elif basename(inst) in basename_set:
            matched_stage = "basename"
        elif normalize_brackets(basename(inst)) in basename_bracket_set:
            matched_stage = "basename_bracket_normalized"

        if matched_stage:
            summary[f"matched_{matched_stage}"] += 1
            summary["matched_any"] += 1
            continue

        unmatched_by_unit[unit] += 1
        pclass = pattern_class(inst)
        pattern_counts[pclass] += 1
        pattern_by_unit[(unit, pclass)] += 1

        if len(examples) < 200:
            candidates = best_substring_candidates(inst, def_names)
            examples.append(
                {
                    "instance": inst,
                    "architecture_unit": unit,
                    "pattern_class": pclass,
                    "cell_type": row.get("cell_type", ""),
                    "net_count": row.get("net_count", ""),
                    "candidate_count": len(candidates),
                    "candidate_examples": ";".join(candidates),
                }
            )

    unmatched_total = summary["total_feature_instances"] - summary["matched_any"]
    summary_rows = [
        {
            "design": args.design,
            "def_file": str(def_path),
            "feature_instance_count": summary["total_feature_instances"],
            "def_component_count": len(def_components),
            "matched_any": summary["matched_any"],
            "matched_fraction": f"{summary['matched_any'] / summary['total_feature_instances'] if summary['total_feature_instances'] else 0.0:.6f}",
            "unmatched_count": unmatched_total,
            "unmatched_fraction": f"{unmatched_total / summary['total_feature_instances'] if summary['total_feature_instances'] else 0.0:.6f}",
            "matched_exact": summary["matched_exact"],
            "matched_basic": summary["matched_basic"],
            "matched_bracket_normalized": summary["matched_bracket_normalized"],
            "matched_basename": summary["matched_basename"],
            "matched_basename_bracket_normalized": summary["matched_basename_bracket_normalized"],
        }
    ]

    unit_rows = []
    for unit, total in sorted(total_by_unit.items(), key=lambda kv: (-unmatched_by_unit[kv[0]], kv[0])):
        unmatched = unmatched_by_unit[unit]
        unit_rows.append(
            {
                "design": args.design,
                "architecture_unit": unit,
                "total_instances": total,
                "unmatched_instances": unmatched,
                "unmatched_fraction": f"{unmatched / total if total else 0.0:.6f}",
            }
        )

    pattern_rows = []
    for pclass, count in pattern_counts.most_common():
        pattern_rows.append(
            {
                "design": args.design,
                "pattern_class": pclass,
                "unmatched_instances": count,
                "unmatched_fraction": f"{count / unmatched_total if unmatched_total else 0.0:.6f}",
            }
        )
    for (unit, pclass), count in sorted(pattern_by_unit.items(), key=lambda kv: (-kv[1], kv[0])):
        pattern_rows.append(
            {
                "design": args.design,
                "pattern_class": f"{unit}::{pclass}",
                "unmatched_instances": count,
                "unmatched_fraction": f"{count / unmatched_by_unit[unit] if unmatched_by_unit[unit] else 0.0:.6f}",
            }
        )

    summary_path = features_dir / "def_matching_diagnosis_summary.csv"
    unit_path = features_dir / "def_matching_unmatched_by_unit.csv"
    pattern_path = features_dir / "def_matching_unmatched_patterns.csv"
    examples_path = features_dir / "def_matching_candidate_examples.csv"
    manifest_path = features_dir / "def_matching_diagnosis_manifest.json"

    write_csv(
        summary_path,
        summary_rows,
        [
            "design",
            "def_file",
            "feature_instance_count",
            "def_component_count",
            "matched_any",
            "matched_fraction",
            "unmatched_count",
            "unmatched_fraction",
            "matched_exact",
            "matched_basic",
            "matched_bracket_normalized",
            "matched_basename",
            "matched_basename_bracket_normalized",
        ],
    )
    write_csv(
        unit_path,
        unit_rows,
        ["design", "architecture_unit", "total_instances", "unmatched_instances", "unmatched_fraction"],
    )
    write_csv(
        pattern_path,
        pattern_rows,
        ["design", "pattern_class", "unmatched_instances", "unmatched_fraction"],
    )
    write_csv(
        examples_path,
        examples,
        ["instance", "architecture_unit", "pattern_class", "cell_type", "net_count", "candidate_count", "candidate_examples"],
    )

    manifest = {
        "design": args.design,
        "platform": args.platform,
        "orfs_flow_dir": str(flow_dir),
        "features_dir": str(features_dir),
        "def_file": str(def_path),
        "outputs": [
            str(summary_path),
            str(unit_path),
            str(pattern_path),
            str(examples_path),
            str(manifest_path),
        ],
        "note": "Diagnostic only. No matching repair is applied by this script.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(summary_path)
    print(unit_path)
    print(pattern_path)
    print(examples_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
