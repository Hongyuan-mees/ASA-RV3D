#!/usr/bin/env python3
"""Evaluate downstream timing impact from pseudo-3D vertical-link delay.

This script supports the paper's Section 5.2 downstream validation.  It does
not rerun STA and does not claim signoff 3D timing.  Instead, it reads OpenSTA
critical-path reports, maps path instances to tier assignments, and estimates
how much slack would degrade if each tier transition on a reported path paid a
fixed vertical-link delay.

The metric is deliberately independent from the ASA-RV3D repair objective:
it is path-level, OpenSTA-report-driven, and compares TritonPart against the
final ASA-RV3D assignment.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]


START_RE = re.compile(r"^Startpoint:\s+(.+)$")
END_RE = re.compile(r"^Endpoint:\s+(.+)$")
SLACK_RE = re.compile(r"([-+]?\d+(?:\.\d+)?)\s+slack\s+\((?:MET|VIOLATED)\)", re.IGNORECASE)


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


def f(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def norm_name(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        name = name[1:]
    return name


def basic_name_variants(name: str) -> set[str]:
    """Generate lightweight variants for matching OpenSTA path names."""

    name = norm_name(name)
    variants = {name}
    variants.add(name.replace("$*", "$_").replace("*", "_"))
    variants.add(name.replace("[", "\\[").replace("]", "\\]"))
    variants.add(name.replace("\\[", "[").replace("\\]", "]"))
    variants.add(name.replace("/", "."))
    variants.add(name.replace(".", "/"))
    return {v for v in variants if v}


def load_assignment(path: Path) -> dict[str, str]:
    return {norm_name(row["instance"]): row["tier"] for row in read_csv(path)}


def load_instance_names(features_dir: Path) -> set[str]:
    return {norm_name(row["instance"]) for row in read_csv(features_dir / "instance_features.csv")}


def assignment_path(design: str, scenario: str, case: str) -> Path:
    if case == "tritonpart":
        return Path("results") / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv"
    if case == "asa_rv3d":
        return (
            Path("results")
            / f"{design}_tritonpart_timing_regret_guarded_repair"
            / scenario
            / "tritonpart_timing_regret_guarded_repair_assignment.csv"
        )
    raise ValueError(case)


def timing_report_path(design: str, timing_dir: Path) -> Path:
    direct = timing_dir / f"{design}_report_checks_max.rpt"
    if direct.exists():
        return direct
    legacy = timing_dir / f"{design}_report_checks.rpt"
    if legacy.exists():
        return legacy
    raise FileNotFoundError(direct)


def split_path_blocks(report_path: Path, max_paths: int) -> list[str]:
    blocks: list[list[str]] = []
    current: list[str] = []
    with report_path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if START_RE.match(line):
                if current:
                    blocks.append(current)
                    if len(blocks) >= max_paths:
                        break
                current = [line]
            elif current:
                current.append(line)
                if SLACK_RE.search(line):
                    blocks.append(current)
                    current = []
                    if len(blocks) >= max_paths:
                        break
    if current and len(blocks) < max_paths:
        blocks.append(current)
    return ["\n".join(block) for block in blocks]


def parse_path_metadata(block: str) -> tuple[str, str, float | None]:
    start = ""
    end = ""
    slack: float | None = None
    for line in block.splitlines():
        m = START_RE.match(line)
        if m:
            start = m.group(1).strip()
        m = END_RE.match(line)
        if m:
            end = m.group(1).strip()
        m = SLACK_RE.search(line)
        if m:
            slack = float(m.group(1))
    return start, end, slack


def build_match_index(instances: set[str]) -> dict[str, str]:
    """Map likely report tokens back to canonical instance names."""

    index: dict[str, str] = {}
    for inst in instances:
        for variant in basic_name_variants(inst):
            index.setdefault(variant, inst)
    return index


def token_candidates_from_line(line: str) -> list[str]:
    """Extract likely instance tokens from one OpenSTA path line."""

    tokens: list[str] = []
    # The description usually appears before a library cell in parentheses.
    if "(" in line:
        desc = line.rsplit("(", 1)[0].strip()
    else:
        desc = line.strip()
    if not desc:
        return tokens

    parts = desc.split()
    if not parts:
        return tokens
    raw = parts[-1].lstrip("^v")
    raw = raw.strip()
    if not raw or raw in {"clock", "data", "library"}:
        return tokens

    tokens.append(raw)
    if "/" in raw:
        tokens.append(raw.rsplit("/", 1)[0])
    if "." in raw:
        tokens.append(raw.rsplit(".", 1)[0])
    return [norm_name(token) for token in tokens if token]


def extract_path_instances(block: str, match_index: dict[str, str]) -> list[str]:
    seen_sequence: list[str] = []
    last = None
    for line in block.splitlines():
        matched = None
        for token in token_candidates_from_line(line):
            variants = basic_name_variants(token)
            for variant in variants:
                if variant in match_index:
                    matched = match_index[variant]
                    break
            if matched:
                break
        if matched and matched != last:
            seen_sequence.append(matched)
            last = matched
    return seen_sequence


def tier_transitions(path_instances: list[str], assignment: dict[str, str]) -> int:
    tiers = [assignment[inst] for inst in path_instances if inst in assignment]
    if len(tiers) < 2:
        return 0
    transitions = 0
    prev = tiers[0]
    for tier in tiers[1:]:
        if tier != prev:
            transitions += 1
        prev = tier
    return transitions


def evaluate_assignment(
    design: str,
    scenario: str,
    case: str,
    assignment: dict[str, str],
    path_rows: list[dict[str, object]],
    vertical_delay_ns: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    out_paths: list[dict[str, object]] = []
    slacks = []
    estimated_slacks = []
    transition_counts = []
    matched_counts = []
    for idx, row in enumerate(path_rows):
        path_instances = row["path_instances"]
        assert isinstance(path_instances, list)
        slack = row["slack"]
        if slack is None:
            continue
        slack_f = float(slack)
        transitions = tier_transitions(path_instances, assignment)
        degradation = transitions * vertical_delay_ns
        estimated_slack = slack_f - degradation
        matched_count = sum(1 for inst in path_instances if inst in assignment)
        slacks.append(slack_f)
        estimated_slacks.append(estimated_slack)
        transition_counts.append(transitions)
        matched_counts.append(matched_count)
        out_paths.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "path_index": idx,
                "startpoint": row["startpoint"],
                "endpoint": row["endpoint"],
                "reported_slack_ns": f"{slack_f:.6f}",
                "matched_instance_count": matched_count,
                "tier_transition_count": transitions,
                "vertical_delay_ns": f"{vertical_delay_ns:.6f}",
                "estimated_vertical_delay_degradation_ns": f"{degradation:.6f}",
                "estimated_slack_with_vertical_delay_ns": f"{estimated_slack:.6f}",
            }
        )

    path_count = len(out_paths)
    crossing_paths = sum(1 for value in transition_counts if value > 0)
    tns = sum(value for value in estimated_slacks if value < 0)
    original_tns = sum(value for value in slacks if value < 0)
    summary = {
        "design": design,
        "scenario": scenario,
        "case": case,
        "path_count": path_count,
        "matched_path_fraction": f"{sum(1 for value in matched_counts if value > 0) / path_count if path_count else 0.0:.6f}",
        "crossing_path_count": crossing_paths,
        "crossing_path_fraction": f"{crossing_paths / path_count if path_count else 0.0:.6f}",
        "mean_tier_transitions_per_path": f"{sum(transition_counts) / path_count if path_count else 0.0:.6f}",
        "max_tier_transitions_on_path": max(transition_counts) if transition_counts else 0,
        "vertical_delay_ns": f"{vertical_delay_ns:.6f}",
        "original_wns_ns": f"{min(slacks) if slacks else 0.0:.6f}",
        "estimated_wns_ns": f"{min(estimated_slacks) if estimated_slacks else 0.0:.6f}",
        "estimated_wns_degradation_ns": f"{(min(slacks) - min(estimated_slacks)) if slacks and estimated_slacks else 0.0:.6f}",
        "original_tns_ns": f"{original_tns:.6f}",
        "estimated_tns_ns": f"{tns:.6f}",
        "estimated_tns_degradation_ns": f"{original_tns - tns:.6f}",
    }
    return summary, out_paths


def add_reductions(rows: list[dict[str, object]]) -> None:
    by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        if row["case"] == "tritonpart":
            by_key[(str(row["design"]), str(row["scenario"]))] = row
    for row in rows:
        base = by_key.get((str(row["design"]), str(row["scenario"])))
        if not base:
            continue
        base_cross = f(base["crossing_path_fraction"])
        base_wns_deg = f(base["estimated_wns_degradation_ns"])
        base_tns_deg = f(base["estimated_tns_degradation_ns"])
        row_cross = f(row["crossing_path_fraction"])
        row_wns_deg = f(row["estimated_wns_degradation_ns"])
        row_tns_deg = f(row["estimated_tns_degradation_ns"])
        row["crossing_path_fraction_reduction_vs_tritonpart"] = f"{(base_cross - row_cross) / base_cross if base_cross else 0.0:.6f}"
        row["wns_degradation_reduction_vs_tritonpart"] = f"{(base_wns_deg - row_wns_deg) / base_wns_deg if base_wns_deg else 0.0:.6f}"
        row["tns_degradation_reduction_vs_tritonpart"] = f"{(base_tns_deg - row_tns_deg) / base_tns_deg if base_tns_deg else 0.0:.6f}"


def evaluate_design_scenario(
    design: str,
    scenario: str,
    timing_dir: Path,
    max_paths: int,
    vertical_delay_ns: float,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    features_dir = Path("results") / f"{design}_features"
    instance_names = load_instance_names(features_dir)
    match_index = build_match_index(instance_names)
    report_path = timing_report_path(design, timing_dir)
    blocks = split_path_blocks(report_path, max_paths)
    path_rows: list[dict[str, object]] = []
    for block in blocks:
        start, end, slack = parse_path_metadata(block)
        instances = extract_path_instances(block, match_index)
        path_rows.append(
            {
                "startpoint": start,
                "endpoint": end,
                "slack": slack,
                "path_instances": instances,
            }
        )

    summaries = []
    path_details = []
    for case in ["tritonpart", "asa_rv3d"]:
        assignment = load_assignment(assignment_path(design, scenario, case))
        summary, details = evaluate_assignment(design, scenario, case, assignment, path_rows, vertical_delay_ns)
        summaries.append(summary)
        path_details.extend(details)
    return summaries, path_details


def summarize_rollup(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    asa = [row for row in rows if row["case"] == "asa_rv3d"]
    wns_reductions = [f(row.get("wns_degradation_reduction_vs_tritonpart")) for row in asa]
    crossing_reductions = [f(row.get("crossing_path_fraction_reduction_vs_tritonpart")) for row in asa]
    positive_wns = sum(1 for value in wns_reductions if value > 0)
    return [
        {"metric": "cases", "value": len(asa)},
        {"metric": "designs", "value": ",".join(sorted({str(row["design"]) for row in asa}))},
        {"metric": "positive_wns_degradation_reduction_cases", "value": positive_wns},
        {"metric": "wns_degradation_reduction_min", "value": f"{min(wns_reductions) if wns_reductions else 0.0:.6f}"},
        {"metric": "wns_degradation_reduction_mean", "value": f"{sum(wns_reductions) / len(wns_reductions) if wns_reductions else 0.0:.6f}"},
        {"metric": "wns_degradation_reduction_max", "value": f"{max(wns_reductions) if wns_reductions else 0.0:.6f}"},
        {"metric": "crossing_path_fraction_reduction_mean", "value": f"{sum(crossing_reductions) / len(crossing_reductions) if crossing_reductions else 0.0:.6f}"},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", help="Design to evaluate. Repeatable. Defaults to four-core suite.")
    parser.add_argument("--scenario", action="append", help="Scenario to evaluate. Repeatable. Defaults to all three scenarios.")
    parser.add_argument("--timing-dir", type=Path, default=Path("results/timing_reports"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--vertical-delay-ns", type=float, default=0.05)
    parser.add_argument("--max-paths", type=int, default=200)
    args = parser.parse_args()

    designs = args.design or DESIGNS
    scenarios = args.scenario or SCENARIOS
    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    for design in designs:
        for scenario in scenarios:
            summaries, details = evaluate_design_scenario(
                design,
                scenario,
                args.timing_dir,
                args.max_paths,
                args.vertical_delay_ns,
            )
            summary_rows.extend(summaries)
            detail_rows.extend(details)

    add_reductions(summary_rows)
    summary_fields = [
        "design",
        "scenario",
        "case",
        "path_count",
        "matched_path_fraction",
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
        "crossing_path_fraction_reduction_vs_tritonpart",
        "wns_degradation_reduction_vs_tritonpart",
        "tns_degradation_reduction_vs_tritonpart",
    ]
    detail_fields = [
        "design",
        "scenario",
        "case",
        "path_index",
        "startpoint",
        "endpoint",
        "reported_slack_ns",
        "matched_instance_count",
        "tier_transition_count",
        "vertical_delay_ns",
        "estimated_vertical_delay_degradation_ns",
        "estimated_slack_with_vertical_delay_ns",
    ]
    rollup_fields = ["metric", "value"]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / "downstream_vertical_delay_summary.csv"
    detail_path = args.output_dir / "downstream_vertical_delay_paths.csv"
    rollup_path = args.output_dir / "downstream_vertical_delay_rollup.csv"
    manifest_path = args.output_dir / "downstream_vertical_delay_manifest.json"
    write_csv(summary_path, summary_rows, summary_fields)
    write_csv(detail_path, detail_rows, detail_fields)
    write_csv(rollup_path, summarize_rollup(summary_rows), rollup_fields)
    manifest = {
        "note": "Estimated downstream validation. Uses OpenSTA path reports plus a fixed per-tier-transition vertical delay; not signoff 3D STA.",
        "vertical_delay_ns": args.vertical_delay_ns,
        "max_paths": args.max_paths,
        "designs": designs,
        "scenarios": scenarios,
        "outputs": [str(summary_path), str(detail_path), str(rollup_path), str(manifest_path)],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(summary_path)
    print(rollup_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
