#!/usr/bin/env python3
"""Evaluate downstream vertical-delay impact for path-aware ASA-RV3D.

This evaluator compares three assignments on the same OpenSTA max-path report:

1. TritonPart connectivity-first baseline
2. ASA-RV3D timing-regret guarded repair
3. Path-aware ASA-RV3D repair

For each timing path, every tier transition adds a fixed vertical-link delay.
This is not signoff 3D STA; it is an independent path-level downstream proxy
for the paper's Section 5.2.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path


SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]
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
    return name


def assignment_paths(design: str, scenario: str) -> dict[str, Path]:
    return {
        "tritonpart": Path("results") / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv",
        "asa_rv3d": (
            Path("results")
            / f"{design}_tritonpart_timing_regret_guarded_repair"
            / scenario
            / "tritonpart_timing_regret_guarded_repair_assignment.csv"
        ),
        "path_aware_asa_rv3d": (
            Path("results")
            / f"{design}_tritonpart_path_aware_guarded_repair"
            / scenario
            / "tritonpart_path_aware_guarded_repair_assignment.csv"
        ),
    }


def load_assignment(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    rows = read_csv(path)
    tier: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        tier[inst] = row["tier"]
        for alias in {
            inst,
            inst.replace("\\[", "[").replace("\\]", "]"),
            inst.replace("[", "\\[").replace("]", "\\]"),
            inst.replace("/", "."),
            inst.replace(".", "/"),
        }:
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


def finite_ratio(num: float, den: float) -> str:
    if abs(den) < 1e-12:
        if abs(num) < 1e-12:
            return "0.000000"
        return ""
    return f"{num / den:.6f}"


def summarize_case(
    design: str,
    scenario: str,
    case: str,
    assignment_file: Path,
    paths: list[TimingPath],
    tier: dict[str, str],
    vertical_delay_ns: float,
) -> dict[str, object]:
    slacks = [p.slack for p in paths if p.slack is not None]
    if not slacks:
        original_wns = 0.0
        original_tns = 0.0
    else:
        original_wns = min(slacks)
        original_tns = sum(s for s in slacks if s < 0)

    transition_counts = [transition_count(path, tier) for path in paths]
    estimated_slacks = [
        (path.slack if path.slack is not None else 0.0) - transitions * vertical_delay_ns
        for path, transitions in zip(paths, transition_counts)
    ]
    estimated_wns = min(estimated_slacks) if estimated_slacks else 0.0
    estimated_tns = sum(s for s in estimated_slacks if s < 0)
    crossing_paths = sum(1 for x in transition_counts if x > 0)
    path_count = len(paths)
    wns_degradation = original_wns - estimated_wns
    tns_degradation = original_tns - estimated_tns
    return {
        "design": design,
        "scenario": scenario,
        "case": case,
        "assignment_file": str(assignment_file),
        "path_count": path_count,
        "crossing_path_count": crossing_paths,
        "crossing_path_fraction": f"{crossing_paths / path_count:.6f}" if path_count else "0.000000",
        "mean_tier_transitions_per_path": f"{sum(transition_counts) / path_count:.6f}" if path_count else "0.000000",
        "max_tier_transitions_on_path": max(transition_counts) if transition_counts else 0,
        "vertical_delay_ns": f"{vertical_delay_ns:.6f}",
        "original_wns_ns": f"{original_wns:.6f}",
        "estimated_wns_ns": f"{estimated_wns:.6f}",
        "estimated_wns_degradation_ns": f"{wns_degradation:.6f}",
        "original_tns_ns": f"{original_tns:.6f}",
        "estimated_tns_ns": f"{estimated_tns:.6f}",
        "estimated_tns_degradation_ns": f"{tns_degradation:.6f}",
    }


def assignment_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--assignment must use label=path")
    label, path = value.split("=", 1)
    if not label:
        raise argparse.ArgumentTypeError("assignment label cannot be empty")
    return label, Path(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    parser.add_argument("--timing-report", type=Path)
    parser.add_argument("--assignment", action="append", type=assignment_arg, help="Custom assignment as label=path; repeatable.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--vertical-delay-ns", type=float, default=0.05)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timing_report = args.timing_report or Path("results") / "timing_reports" / f"{args.design}_report_checks_max.rpt"
    output = args.output or (
        Path("results")
        / "benchmark_summary"
        / f"{args.design}_{args.scenario}_path_aware_downstream_vertical_delay.csv"
    )
    paths_by_case = dict(args.assignment) if args.assignment else assignment_paths(args.design, args.scenario)
    loaded: dict[str, tuple[dict[str, str], dict[str, str], Path]] = {}
    union_aliases: dict[str, str] = {}
    for case, path in paths_by_case.items():
        if not path.exists():
            print(f"[skip] missing assignment: {path}")
            continue
        tier, aliases = load_assignment(path)
        loaded[case] = (tier, aliases, path)
        union_aliases.update(aliases)
    if not loaded:
        raise RuntimeError("No assignment files found.")

    # Parse once with union aliases, then re-resolve per assignment alias set.
    rows: list[dict[str, object]] = []
    for case, (tier, aliases, assignment_file) in loaded.items():
        paths = parse_timing_paths(timing_report, aliases, args.max_paths)
        rows.append(
            summarize_case(
                args.design,
                args.scenario,
                case,
                assignment_file,
                paths,
                tier,
                args.vertical_delay_ns,
            )
        )

    base = next((r for r in rows if r["case"] == "tritonpart"), None)
    asa = next((r for r in rows if r["case"] == "asa_rv3d"), None)
    for row in rows:
        if base:
            base_wns = float(base["estimated_wns_degradation_ns"])
            base_tns = float(base["estimated_tns_degradation_ns"])
            row["wns_degradation_reduction_vs_tritonpart"] = finite_ratio(base_wns - float(row["estimated_wns_degradation_ns"]), base_wns)
            row["tns_degradation_reduction_vs_tritonpart"] = finite_ratio(base_tns - float(row["estimated_tns_degradation_ns"]), base_tns)
        else:
            row["wns_degradation_reduction_vs_tritonpart"] = ""
            row["tns_degradation_reduction_vs_tritonpart"] = ""
        if asa:
            asa_wns = float(asa["estimated_wns_degradation_ns"])
            asa_tns = float(asa["estimated_tns_degradation_ns"])
            row["wns_degradation_reduction_vs_asa_rv3d"] = finite_ratio(asa_wns - float(row["estimated_wns_degradation_ns"]), asa_wns)
            row["tns_degradation_reduction_vs_asa_rv3d"] = finite_ratio(asa_tns - float(row["estimated_tns_degradation_ns"]), asa_tns)
        else:
            row["wns_degradation_reduction_vs_asa_rv3d"] = ""
            row["tns_degradation_reduction_vs_asa_rv3d"] = ""

    write_csv(
        output,
        rows,
        [
            "design",
            "scenario",
            "case",
            "assignment_file",
            "path_count",
            "crossing_path_count",
            "crossing_path_fraction",
            "mean_tier_transitions_per_path",
            "max_tier_transitions_on_path",
            "vertical_delay_ns",
            "original_wns_ns",
            "estimated_wns_ns",
            "estimated_wns_degradation_ns",
            "original_tns_ns",
            "estimated_tns_ns",
            "estimated_tns_degradation_ns",
            "wns_degradation_reduction_vs_tritonpart",
            "tns_degradation_reduction_vs_tritonpart",
            "wns_degradation_reduction_vs_asa_rv3d",
            "tns_degradation_reduction_vs_asa_rv3d",
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
