#!/usr/bin/env python3
"""Evaluate TritonPart-style timing-path cut metrics for tier assignments.

This is a read-only evaluator.  It parses an OpenSTA max-path report and
computes, for each assignment:

* P_avg_cut: average tier transitions per matched timing path
* P_wst_cut: worst tier transitions on any matched timing path

These are proxy equivalents of the timing-path cut metrics used by timing-aware
partitioning papers.  They complement, but do not replace, signoff STA.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
STD_CELL_RE = re.compile(r"\((sky130[^)]*|[A-Za-z0-9_]+__[^)]*)\)")
EDGE_MARKERS = {"^", "v", "r", "f"}


@dataclass
class TimingPath:
    index: int
    startpoint: str
    endpoint: str
    slack: float | None
    instances: list[str]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "design",
        "case",
        "assignment_file",
        "path_count",
        "matched_path_count",
        "matched_path_fraction",
        "cut_path_count",
        "cut_path_fraction",
        "P_avg_cut",
        "P_wst_cut",
        "total_tier_transitions",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def normalize_name(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        name = name[1:]
    return name


def load_assignment(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    rows = read_csv(path)
    tier: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        tier[inst] = row["tier"]
        variants = {
            inst,
            inst.replace("\\[", "[").replace("\\]", "]"),
            inst.replace("[", "\\[").replace("]", "\\]"),
            inst.replace("/", "."),
            inst.replace(".", "/"),
        }
        for alias in variants:
            aliases[normalize_name(alias)] = inst
    return tier, aliases


def strip_numeric_columns(line: str) -> str:
    parts = line.strip().split()
    while parts and FLOAT_RE.fullmatch(parts[0]):
        parts.pop(0)
    while parts and parts[0] in EDGE_MARKERS:
        parts.pop(0)
    return " ".join(parts)


def candidate_from_description(desc: str) -> str | None:
    if not desc:
        return None
    if desc.startswith(("clock ", "data ", "library ", "external ", "input ", "output ", "#")):
        return None
    if "slack" in desc or "arrival" in desc or "required" in desc or "uncertainty" in desc:
        return None
    if STD_CELL_RE.search(desc):
        desc = STD_CELL_RE.sub("", desc).strip()
    parts = desc.split()
    while parts and parts[0] in EDGE_MARKERS:
        parts.pop(0)
    if not parts:
        return None
    token = parts[0].strip(",").lstrip("^v")
    if "/" not in token:
        return None
    return normalize_name(token.rsplit("/", 1)[0])


def resolve_instance(token: str, aliases: dict[str, str]) -> str | None:
    token = normalize_name(token)
    candidates = [
        token,
        token.replace("\\[", "[").replace("\\]", "]"),
        token.replace("[", "\\[").replace("]", "\\]"),
        token.replace("/", "."),
        token.replace(".", "/"),
    ]
    for cand in candidates:
        if cand in aliases:
            return aliases[cand]
    suffix = token.split("/")[-1].split(".")[-1]
    if suffix:
        matches = sorted({inst for alias, inst in aliases.items() if alias.endswith(suffix)})
        if len(matches) == 1:
            return matches[0]
    return None


def finish_path(raw: dict[str, object], aliases: dict[str, str], index: int) -> TimingPath:
    raw_instances = list(dict.fromkeys(raw["instances"]))  # type: ignore[arg-type]
    instances: list[str] = []
    for token in raw_instances:
        inst = resolve_instance(str(token), aliases)
        if inst:
            instances.append(inst)
    return TimingPath(
        index=index,
        startpoint=str(raw.get("startpoint", "")),
        endpoint=str(raw.get("endpoint", "")),
        slack=raw.get("slack"),  # type: ignore[arg-type]
        instances=list(dict.fromkeys(instances)),
    )


def parse_timing_paths(report: Path, aliases: dict[str, str], max_paths: int) -> list[TimingPath]:
    paths: list[TimingPath] = []
    current: dict[str, object] | None = None
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Startpoint:"):
            if current is not None:
                paths.append(finish_path(current, aliases, len(paths)))
                if len(paths) >= max_paths:
                    return paths
            current = {"startpoint": line.split("Startpoint:", 1)[1].strip(), "endpoint": "", "slack": None, "instances": []}
            continue
        if current is None:
            continue
        if line.startswith("Endpoint:"):
            current["endpoint"] = line.split("Endpoint:", 1)[1].strip()
            continue
        if " slack " in f" {line} " or line.strip().endswith(" slack (VIOLATED)") or line.strip().endswith(" slack (MET)"):
            nums = FLOAT_RE.findall(line)
            if nums:
                current["slack"] = float(nums[-1])
            continue
        token = candidate_from_description(strip_numeric_columns(line))
        if token:
            current["instances"].append(token)  # type: ignore[index]
    if current is not None and len(paths) < max_paths:
        paths.append(finish_path(current, aliases, len(paths)))
    return paths


def transition_count(path: TimingPath, tier: dict[str, str]) -> int:
    seq = [inst for inst in path.instances if inst in tier]
    return sum(1 for a, b in zip(seq, seq[1:]) if tier[a] != tier[b])


def summarize_assignment(
    design: str,
    case: str,
    assignment: Path,
    timing_report: Path,
    max_paths: int,
) -> dict[str, object]:
    tier, aliases = load_assignment(assignment)
    paths = parse_timing_paths(timing_report, aliases, max_paths)
    transitions = [transition_count(path, tier) for path in paths]
    matched = sum(1 for path in paths if path.instances)
    cut_paths = sum(1 for count in transitions if count > 0)
    path_count = len(paths)
    total_transitions = sum(transitions)
    return {
        "design": design,
        "case": case,
        "assignment_file": str(assignment),
        "path_count": path_count,
        "matched_path_count": matched,
        "matched_path_fraction": f"{matched / path_count:.6f}" if path_count else "0.000000",
        "cut_path_count": cut_paths,
        "cut_path_fraction": f"{cut_paths / path_count:.6f}" if path_count else "0.000000",
        "P_avg_cut": f"{total_transitions / path_count:.6f}" if path_count else "0.000000",
        "P_wst_cut": max(transitions) if transitions else 0,
        "total_tier_transitions": total_transitions,
    }


def parse_assignment_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--assignment must be label=path")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("assignment label cannot be empty")
    return label, Path(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--timing-report", required=True, type=Path)
    parser.add_argument("--assignment", action="append", required=True, type=parse_assignment_arg)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    rows = [
        summarize_assignment(args.design, label, path, args.timing_report, args.max_paths)
        for label, path in args.assignment
    ]
    write_csv(args.output, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
