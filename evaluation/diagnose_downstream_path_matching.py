#!/usr/bin/env python3
"""Diagnose path-level downstream validation matching.

This script does not change any partition result.  It inspects OpenSTA
report_checks output, maps path instances onto TritonPart / ASA-RV3D tier
assignments, and reports whether the downstream vertical-delay evaluator is
seeing real tier-transition differences or suffering from weak path matching.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]
DEFAULT_SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]
STD_CELL_RE = re.compile(r"\((sky130[^)]*|[A-Za-z0-9_]+__[^)]*)\)")
FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
EDGE_MARKERS = {"^", "v", "r", "f"}


@dataclass
class TimingPath:
    index: int
    startpoint: str
    endpoint: str
    slack: float | None
    raw_instances: list[str]
    matched_instances: list[str]
    unmatched_tokens: list[str]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def normalize_name(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        name = name[1:]
    return name.strip()


def assignment_path(results_dir: Path, design: str, scenario: str, case: str) -> Path:
    if case == "tritonpart":
        return results_dir / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv"
    return (
        results_dir
        / f"{design}_tritonpart_timing_regret_guarded_repair"
        / scenario
        / "tritonpart_timing_regret_guarded_repair_assignment.csv"
    )


def load_assignment(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    rows = read_csv(path)
    tier_by_instance: dict[str, str] = {}
    canonical_by_alias: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        tier_by_instance[inst] = row["tier"]
        aliases = {
            inst,
            inst.replace("\\[", "[").replace("\\]", "]"),
            inst.replace("[", "\\[").replace("]", "\\]"),
            inst.replace("/", "."),
            inst.replace(".", "/"),
        }
        for alias in aliases:
            canonical_by_alias[normalize_name(alias)] = inst
    return tier_by_instance, canonical_by_alias


def timing_report_path(timing_dir: Path, design: str) -> Path:
    return timing_dir / f"{design}_report_checks_max.rpt"


def strip_numeric_columns(line: str) -> str:
    # OpenSTA path rows begin with optional numeric columns, then a description.
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
    token = parts[0].strip()
    token = token.strip(",")
    token = token.lstrip("^v")
    if "/" not in token:
        return None
    # Convert pin path to instance path.  Keep hierarchy, drop only final pin.
    inst = token.rsplit("/", 1)[0]
    return normalize_name(inst)


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
    # Some reports include a hierarchy prefix that is absent from synthesized
    # instance names.  Try suffix matching as a last resort, but only when it is
    # unique enough to avoid false positives.
    suffix = token.split("/")[-1].split(".")[-1]
    if suffix:
        matches = [inst for alias, inst in aliases.items() if alias.endswith(suffix)]
        unique = sorted(set(matches))
        if len(unique) == 1:
            return unique[0]
    return None


def parse_timing_paths(path: Path, aliases: dict[str, str], max_paths: int) -> list[TimingPath]:
    paths: list[TimingPath] = []
    current: dict[str, object] | None = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Startpoint:"):
            if current is not None:
                paths.append(finish_path(current, aliases))
                if len(paths) >= max_paths:
                    return paths
            current = {
                "startpoint": line.split("Startpoint:", 1)[1].strip(),
                "endpoint": "",
                "slack": None,
                "raw_instances": [],
                "unmatched_tokens": [],
            }
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
        desc = strip_numeric_columns(line)
        token = candidate_from_description(desc)
        if token:
            current["raw_instances"].append(token)  # type: ignore[index]

    if current is not None and len(paths) < max_paths:
        paths.append(finish_path(current, aliases))
    return paths


def finish_path(current: dict[str, object], aliases: dict[str, str]) -> TimingPath:
    raw_instances = list(dict.fromkeys(current["raw_instances"]))  # type: ignore[arg-type]
    matched: list[str] = []
    unmatched: list[str] = []
    for token in raw_instances:
        resolved = resolve_instance(str(token), aliases)
        if resolved:
            matched.append(resolved)
        else:
            unmatched.append(str(token))
    return TimingPath(
        index=-1,
        startpoint=str(current.get("startpoint", "")),
        endpoint=str(current.get("endpoint", "")),
        slack=current.get("slack"),  # type: ignore[arg-type]
        raw_instances=[str(x) for x in raw_instances],
        matched_instances=list(dict.fromkeys(matched)),
        unmatched_tokens=unmatched,
    )


def transition_stats(path: TimingPath, tiers: dict[str, str]) -> tuple[int, list[str]]:
    sequence = [(inst, tiers[inst]) for inst in path.matched_instances if inst in tiers]
    transitions = 0
    pairs: list[str] = []
    for (a_inst, a_tier), (b_inst, b_tier) in zip(sequence, sequence[1:]):
        if a_tier != b_tier:
            transitions += 1
            pairs.append(f"{a_inst}->{b_inst}")
    return transitions, pairs


def summarize_case(
    design: str,
    scenario: str,
    case: str,
    timing_paths: list[TimingPath],
    tiers: dict[str, str],
) -> tuple[dict[str, object], list[dict[str, object]], Counter[str]]:
    path_rows: list[dict[str, object]] = []
    pair_counter: Counter[str] = Counter()
    matched_fractions: list[float] = []
    crossing_paths = 0
    transition_counts: list[int] = []

    for idx, path in enumerate(timing_paths):
        transitions, pairs = transition_stats(path, tiers)
        pair_counter.update(pairs)
        raw_count = len(path.raw_instances)
        matched_count = len([inst for inst in path.matched_instances if inst in tiers])
        matched_fraction = matched_count / raw_count if raw_count else 0.0
        matched_fractions.append(matched_fraction)
        transition_counts.append(transitions)
        if transitions > 0:
            crossing_paths += 1
        path_rows.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "path_index": idx,
                "slack": "" if path.slack is None else f"{path.slack:.6f}",
                "raw_instance_count": raw_count,
                "matched_instance_count": matched_count,
                "matched_instance_fraction": f"{matched_fraction:.6f}",
                "tier_transitions": transitions,
                "startpoint": path.startpoint,
                "endpoint": path.endpoint,
                "first_unmatched_tokens": ";".join(path.unmatched_tokens[:6]),
                "first_transition_pairs": ";".join(pairs[:6]),
            }
        )

    total_paths = len(timing_paths)
    summary = {
        "design": design,
        "scenario": scenario,
        "case": case,
        "path_count": total_paths,
        "mean_matched_instance_fraction": f"{sum(matched_fractions) / total_paths:.6f}" if total_paths else "0.000000",
        "paths_below_50pct_match": sum(1 for x in matched_fractions if x < 0.5),
        "crossing_path_count": crossing_paths,
        "crossing_path_fraction": f"{crossing_paths / total_paths:.6f}" if total_paths else "0.000000",
        "mean_tier_transitions": f"{sum(transition_counts) / total_paths:.6f}" if total_paths else "0.000000",
        "max_tier_transitions": max(transition_counts) if transition_counts else 0,
        "top_transition_pair": pair_counter.most_common(1)[0][0] if pair_counter else "",
        "top_transition_pair_hits": pair_counter.most_common(1)[0][1] if pair_counter else 0,
    }
    return summary, path_rows, pair_counter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", choices=DEFAULT_DESIGNS)
    parser.add_argument("--scenario", action="append", choices=DEFAULT_SCENARIOS)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--timing-dir", type=Path, default=Path("results/timing_reports"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--max-paths", type=int, default=100)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    designs = args.design or DEFAULT_DESIGNS
    scenarios = args.scenario or DEFAULT_SCENARIOS

    summary_rows: list[dict[str, object]] = []
    example_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []

    for design in designs:
        report = timing_report_path(args.timing_dir, design)
        if not report.exists():
            print(f"[skip] missing timing report: {report}")
            continue
        for scenario in scenarios:
            loaded: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
            for case in ["tritonpart", "asa_rv3d"]:
                path = assignment_path(args.results_dir, design, scenario, case)
                if not path.exists():
                    print(f"[skip] missing assignment: {path}")
                    continue
                loaded[case] = load_assignment(path)
            if not loaded:
                continue

            # Parse once using the union of assignment aliases so raw path
            # extraction is identical across cases.
            union_aliases: dict[str, str] = {}
            for _, aliases in loaded.values():
                union_aliases.update(aliases)
            timing_paths = parse_timing_paths(report, union_aliases, args.max_paths)

            for case, (tiers, aliases) in loaded.items():
                # Re-resolve with this case's aliases for exact diagnostics.
                resolved_paths = parse_timing_paths(report, aliases, args.max_paths)
                summary, path_rows, pair_counter = summarize_case(design, scenario, case, resolved_paths, tiers)
                summary["timing_report"] = str(report)
                summary["assignment_file"] = str(assignment_path(args.results_dir, design, scenario, case))
                summary_rows.append(summary)
                # Keep concise examples: worst matched and highest-transition paths.
                path_rows_sorted = sorted(
                    path_rows,
                    key=lambda r: (float(r["matched_instance_fraction"]), -int(r["tier_transitions"])),
                )
                example_rows.extend(path_rows_sorted[:3])
                path_rows_by_transition = sorted(path_rows, key=lambda r: int(r["tier_transitions"]), reverse=True)
                example_rows.extend(path_rows_by_transition[:3])
                for pair, count in pair_counter.most_common(10):
                    pair_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "case": case,
                            "transition_pair": pair,
                            "hits": count,
                        }
                    )

    write_csv(
        args.output_dir / "downstream_path_matching_diagnosis.csv",
        summary_rows,
        [
            "design",
            "scenario",
            "case",
            "path_count",
            "mean_matched_instance_fraction",
            "paths_below_50pct_match",
            "crossing_path_count",
            "crossing_path_fraction",
            "mean_tier_transitions",
            "max_tier_transitions",
            "top_transition_pair",
            "top_transition_pair_hits",
            "timing_report",
            "assignment_file",
        ],
    )
    write_csv(
        args.output_dir / "downstream_path_matching_examples.csv",
        example_rows,
        [
            "design",
            "scenario",
            "case",
            "path_index",
            "slack",
            "raw_instance_count",
            "matched_instance_count",
            "matched_instance_fraction",
            "tier_transitions",
            "startpoint",
            "endpoint",
            "first_unmatched_tokens",
            "first_transition_pairs",
        ],
    )
    write_csv(
        args.output_dir / "downstream_path_transition_pairs.csv",
        pair_rows,
        ["design", "scenario", "case", "transition_pair", "hits"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
