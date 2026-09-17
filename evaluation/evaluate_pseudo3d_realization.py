#!/usr/bin/env python3
"""Evaluate a pseudo-3D realization proxy for ASA-RV3D tier assignments.

This script is intentionally a proxy evaluator, not a 3D place-and-route tool.
It asks whether a 2-tier assignment looks plausible once interpreted as a
pseudo-3D stack:

  - how many nets become inter-tier links,
  - how many endpoint connections those links represent,
  - how much timing/physical/architecture risk is carried by those links,
  - whether ASA-RV3D reduces those risks relative to TritonPart.

Default mode evaluates the current four-core ASA-RV3D suite:
  riscv32i, ibex, picorv32, scr1_core_tuned
across:
  control_datapath_split, memory_near_logic, state_and_clock_protected
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]

FOUR_CORE_DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]

CONTROL_UNITS = {
    "clock_reset",
    "csr",
    "decode_control",
    "fetch",
    "generated_control",
    "pipeline_state",
    "trap_debug",
}

DATAPATH_UNITS = {
    "execute_alu",
    "generated_datapath",
    "load_store",
    "multdiv",
    "register_file",
}

DEFAULT_CRITICALITY = {
    "clock_reset": 5.0,
    "register_file": 4.0,
    "load_store": 3.5,
    "pipeline_state": 3.0,
    "csr": 2.5,
    "decode_control": 2.0,
    "execute_alu": 2.0,
    "fetch": 2.0,
    "multdiv": 2.0,
    "trap_debug": 2.0,
    "generated_datapath": 1.5,
    "generated_control": 1.2,
    "unclassified": 1.0,
}


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


def infer_semantic_group(unit: str) -> str:
    if unit in CONTROL_UNITS:
        return "control"
    if unit in DATAPATH_UNITS:
        return "datapath"
    if unit in {"", "unknown", "unclassified"}:
        return "unknown"
    return "other"


def norm_name(name: str) -> str:
    name = name.strip()
    return name[1:] if name.startswith("\\") else name


def load_assignment(path: Path) -> dict[str, str]:
    return {norm_name(row["instance"]): row["tier"] for row in read_csv(path)}


def load_instance_base(features_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    rows = read_csv(features_dir / "instance_features.csv")
    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = norm_name(row["instance"])
        out = dict(row)
        out["instance"] = inst
        instances[inst] = out
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return instances, dict(net_to_instances)


def merge_architecture(features_dir: Path, instances: dict[str, dict[str, str]]) -> None:
    path = features_dir / "architecture_mapping_instances.csv"
    alt_path = features_dir / "architecture_instance_classes.csv"
    if path.exists():
        for row in read_csv(path):
            inst = norm_name(row["instance"])
            if inst not in instances:
                continue
            unit = row.get("architecture_unit") or row.get("architecture_class") or "unclassified"
            instances[inst]["architecture_unit"] = unit
            instances[inst]["semantic_group"] = row.get("semantic_group") or infer_semantic_group(unit)
            instances[inst]["criticality_weight"] = row.get("criticality_weight") or str(DEFAULT_CRITICALITY.get(unit, 1.0))
    elif alt_path.exists():
        for row in read_csv(alt_path):
            inst = norm_name(row["instance"])
            if inst not in instances:
                continue
            unit = row.get("architecture_class") or "unclassified"
            instances[inst]["architecture_unit"] = unit
            instances[inst]["semantic_group"] = infer_semantic_group(unit)
            instances[inst]["criticality_weight"] = str(DEFAULT_CRITICALITY.get(unit, 1.0))

    for row in instances.values():
        unit = row.get("architecture_unit") or row.get("arch_class") or "unclassified"
        row["architecture_unit"] = unit
        row["semantic_group"] = row.get("semantic_group") or infer_semantic_group(unit)
        row["criticality_weight"] = row.get("criticality_weight") or str(DEFAULT_CRITICALITY.get(unit, 1.0))


def merge_score_file(
    features_dir: Path,
    instances: dict[str, dict[str, str]],
    filename: str,
    source_col_candidates: Iterable[str],
    target_col: str,
) -> None:
    path = features_dir / filename
    if not path.exists():
        return
    for row in read_csv(path):
        inst = norm_name(row.get("instance", ""))
        if inst not in instances:
            continue
        value = ""
        for key in source_col_candidates:
            if row.get(key, "") != "":
                value = row[key]
                break
        instances[inst][target_col] = value


def load_net_hpwl(features_dir: Path) -> dict[str, float]:
    path = features_dir / "physical_net_features.csv"
    if not path.exists():
        return {}
    hpwl: dict[str, float] = {}
    for row in read_csv(path):
        net = row.get("net", "")
        if not net:
            continue
        for key in ("hpwl_um", "net_hpwl_um", "mean_net_hpwl_um", "max_net_hpwl_um"):
            if key in row:
                hpwl[net] = f(row[key])
                break
    return hpwl


def load_features(features_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]], dict[str, float]]:
    instances, net_to_instances = load_instance_base(features_dir)
    merge_architecture(features_dir, instances)
    merge_score_file(
        features_dir,
        instances,
        "timing_context_scores.csv",
        ("timing_context_score", "score"),
        "timing_context_score",
    )
    merge_score_file(
        features_dir,
        instances,
        "physical_context_scores.csv",
        ("physical_context_score", "raw_physical_score"),
        "physical_context_score",
    )
    return instances, net_to_instances, load_net_hpwl(features_dir)


def ratio(low: int | float, high: int | float) -> float:
    high = max(float(high), 1.0)
    return float(low) / high


def reduction(old: float, new: float) -> float:
    return (old - new) / old if old else 0.0


def assignment_weight(instances: dict[str, dict[str, str]], inst: str) -> int:
    return max(1, int(f(instances.get(inst, {}).get("weight", instances.get(inst, {}).get("net_count", 1)), 1)))


def evaluate_case(
    design: str,
    scenario: str,
    case: str,
    assignment_path: Path,
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
    net_hpwl: dict[str, float],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    assignment = load_assignment(assignment_path)
    tier_counts = Counter()
    tier_weights = Counter()
    for inst, tier in assignment.items():
        if inst not in instances:
            continue
        tier_counts[tier] += 1
        tier_weights[tier] += assignment_weight(instances, inst)

    total_connections = 0
    crossing_rows: list[dict[str, object]] = []
    totals = Counter()
    numeric_totals = defaultdict(float)

    for net, raw_connected in sorted(net_to_instances.items()):
        connected = [inst for inst in raw_connected if inst in assignment and inst in instances]
        if not connected:
            continue
        tiers = Counter(assignment[inst] for inst in connected)
        total_connections += len(connected)
        if len(tiers) <= 1:
            continue

        tier0 = tiers.get("tier0", 0)
        tier1 = tiers.get("tier1", 0)
        vertical_proxy = min(tier0, tier1)
        units = sorted({instances[inst].get("architecture_unit", "unclassified") for inst in connected})
        groups = sorted({instances[inst].get("semantic_group", "unknown") for inst in connected})
        timing_scores = [f(instances[inst].get("timing_context_score")) for inst in connected]
        physical_scores = [f(instances[inst].get("physical_context_score")) for inst in connected]
        criticalities = [f(instances[inst].get("criticality_weight"), 1.0) for inst in connected]

        mean_timing = sum(timing_scores) / len(timing_scores)
        max_timing = max(timing_scores) if timing_scores else 0.0
        mean_physical = sum(physical_scores) / len(physical_scores)
        max_criticality = max(criticalities) if criticalities else 1.0
        hpwl = net_hpwl.get(net, 0.0)
        has_control_datapath_boundary = int("control" in groups and "datapath" in groups)
        has_clock_reset = int("clock_reset" in units)

        timing_weighted = vertical_proxy * mean_timing
        physical_weighted = vertical_proxy * mean_physical
        criticality_weighted = vertical_proxy * max_criticality
        cross_tier_hpwl_exposure = hpwl * min(1.0, vertical_proxy / max(len(connected), 1))

        totals["crossing_nets"] += 1
        totals["vertical_connection_proxy"] += vertical_proxy
        totals["timing_crossing_nets"] += int(mean_timing > 0.0)
        totals["high_timing_crossing_nets"] += int(max_timing >= 0.02)
        totals["control_datapath_crossing_nets"] += has_control_datapath_boundary
        totals["clock_reset_crossing_nets"] += has_clock_reset
        numeric_totals["timing_weighted_vertical_proxy"] += timing_weighted
        numeric_totals["physical_weighted_vertical_proxy"] += physical_weighted
        numeric_totals["criticality_weighted_vertical_proxy"] += criticality_weighted
        numeric_totals["crossing_hpwl_um"] += hpwl
        numeric_totals["cross_tier_hpwl_exposure_proxy_um"] += cross_tier_hpwl_exposure

        crossing_rows.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "net": net,
                "fanout": len(connected),
                "tier0_connections": tier0,
                "tier1_connections": tier1,
                "vertical_connection_proxy": vertical_proxy,
                "architecture_units": ";".join(units),
                "semantic_groups": ";".join(groups),
                "has_control_datapath_boundary": has_control_datapath_boundary,
                "has_clock_reset_unit": has_clock_reset,
                "mean_timing_context_score": f"{mean_timing:.6f}",
                "max_timing_context_score": f"{max_timing:.6f}",
                "timing_weighted_vertical_proxy": f"{timing_weighted:.6f}",
                "mean_physical_context_score": f"{mean_physical:.6f}",
                "physical_weighted_vertical_proxy": f"{physical_weighted:.6f}",
                "max_arch_criticality": f"{max_criticality:.3f}",
                "criticality_weighted_vertical_proxy": f"{criticality_weighted:.6f}",
                "hpwl_um": f"{hpwl:.3f}",
                "cross_tier_hpwl_exposure_proxy_um": f"{cross_tier_hpwl_exposure:.3f}",
            }
        )

    summary = {
        "design": design,
        "scenario": scenario,
        "case": case,
        "assignment_file": str(assignment_path),
        "tier0_instances": tier_counts.get("tier0", 0),
        "tier1_instances": tier_counts.get("tier1", 0),
        "instance_balance": f"{ratio(min(tier_counts.get('tier0', 0), tier_counts.get('tier1', 0)), max(tier_counts.get('tier0', 0), tier_counts.get('tier1', 0))):.6f}",
        "tier0_weight": tier_weights.get("tier0", 0),
        "tier1_weight": tier_weights.get("tier1", 0),
        "weight_balance": f"{ratio(min(tier_weights.get('tier0', 0), tier_weights.get('tier1', 0)), max(tier_weights.get('tier0', 0), tier_weights.get('tier1', 0))):.6f}",
        "crossing_nets": totals["crossing_nets"],
        "vertical_connection_proxy": totals["vertical_connection_proxy"],
        "total_net_connections": total_connections,
        "vertical_connection_fraction": f"{ratio(totals['vertical_connection_proxy'], total_connections):.6f}",
        "timing_crossing_nets": totals["timing_crossing_nets"],
        "high_timing_crossing_nets": totals["high_timing_crossing_nets"],
        "timing_weighted_vertical_proxy": f"{numeric_totals['timing_weighted_vertical_proxy']:.6f}",
        "physical_weighted_vertical_proxy": f"{numeric_totals['physical_weighted_vertical_proxy']:.6f}",
        "criticality_weighted_vertical_proxy": f"{numeric_totals['criticality_weighted_vertical_proxy']:.6f}",
        "control_datapath_crossing_nets": totals["control_datapath_crossing_nets"],
        "clock_reset_crossing_nets": totals["clock_reset_crossing_nets"],
        "crossing_hpwl_um": f"{numeric_totals['crossing_hpwl_um']:.3f}",
        "cross_tier_hpwl_exposure_proxy_um": f"{numeric_totals['cross_tier_hpwl_exposure_proxy_um']:.3f}",
    }
    return summary, crossing_rows


def default_assignment(design: str, scenario: str, case: str) -> Path:
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


def evaluate_design_scenario(
    design: str,
    scenario: str,
    output_root: Path,
    cases: list[str],
) -> list[dict[str, object]]:
    features_dir = Path("results") / f"{design}_features"
    if not features_dir.exists():
        raise FileNotFoundError(features_dir)
    instances, net_to_instances, net_hpwl = load_features(features_dir)

    out_dir = output_root / f"{design}_pseudo3d" / scenario
    rows: list[dict[str, object]] = []
    all_crossings: list[dict[str, object]] = []
    by_case: dict[str, dict[str, object]] = {}

    for case in cases:
        assignment_path = default_assignment(design, scenario, case)
        if not assignment_path.exists():
            raise FileNotFoundError(assignment_path)
        summary, crossings = evaluate_case(
            design,
            scenario,
            case,
            assignment_path,
            instances,
            net_to_instances,
            net_hpwl,
        )
        by_case[case] = summary
        rows.append(summary)
        all_crossings.extend(crossings)

    baseline = by_case.get("tritonpart")
    if baseline:
        base_vertical = f(baseline["vertical_connection_proxy"])
        base_timing = f(baseline["timing_weighted_vertical_proxy"])
        base_physical = f(baseline["physical_weighted_vertical_proxy"])
        base_criticality = f(baseline["criticality_weighted_vertical_proxy"])
        for row in rows:
            row["vertical_connection_reduction_vs_tritonpart"] = f"{reduction(base_vertical, f(row['vertical_connection_proxy'])):.6f}"
            row["timing_weighted_reduction_vs_tritonpart"] = f"{reduction(base_timing, f(row['timing_weighted_vertical_proxy'])):.6f}"
            row["physical_weighted_reduction_vs_tritonpart"] = f"{reduction(base_physical, f(row['physical_weighted_vertical_proxy'])):.6f}"
            row["criticality_weighted_reduction_vs_tritonpart"] = f"{reduction(base_criticality, f(row['criticality_weighted_vertical_proxy'])):.6f}"

    summary_fields = [
        "design",
        "scenario",
        "case",
        "assignment_file",
        "tier0_instances",
        "tier1_instances",
        "instance_balance",
        "tier0_weight",
        "tier1_weight",
        "weight_balance",
        "crossing_nets",
        "vertical_connection_proxy",
        "total_net_connections",
        "vertical_connection_fraction",
        "timing_crossing_nets",
        "high_timing_crossing_nets",
        "timing_weighted_vertical_proxy",
        "physical_weighted_vertical_proxy",
        "criticality_weighted_vertical_proxy",
        "control_datapath_crossing_nets",
        "clock_reset_crossing_nets",
        "crossing_hpwl_um",
        "cross_tier_hpwl_exposure_proxy_um",
        "vertical_connection_reduction_vs_tritonpart",
        "timing_weighted_reduction_vs_tritonpart",
        "physical_weighted_reduction_vs_tritonpart",
        "criticality_weighted_reduction_vs_tritonpart",
    ]
    crossing_fields = [
        "design",
        "scenario",
        "case",
        "net",
        "fanout",
        "tier0_connections",
        "tier1_connections",
        "vertical_connection_proxy",
        "architecture_units",
        "semantic_groups",
        "has_control_datapath_boundary",
        "has_clock_reset_unit",
        "mean_timing_context_score",
        "max_timing_context_score",
        "timing_weighted_vertical_proxy",
        "mean_physical_context_score",
        "physical_weighted_vertical_proxy",
        "max_arch_criticality",
        "criticality_weighted_vertical_proxy",
        "hpwl_um",
        "cross_tier_hpwl_exposure_proxy_um",
    ]
    write_csv(out_dir / "pseudo3d_comparison.csv", rows, summary_fields)
    write_csv(out_dir / "pseudo3d_crossing_nets.csv", all_crossings, crossing_fields)
    return rows


def summarize_suite(rows: list[dict[str, object]], output_dir: Path) -> None:
    asa_rows = [row for row in rows if row["case"] == "asa_rv3d"]
    reductions = [f(row.get("timing_weighted_reduction_vs_tritonpart")) for row in asa_rows]
    summary = [
        {
            "metric": "cases",
            "value": len(asa_rows),
        },
        {
            "metric": "designs",
            "value": ",".join(sorted({str(row["design"]) for row in asa_rows})),
        },
        {
            "metric": "timing_weighted_reduction_min",
            "value": f"{min(reductions) if reductions else 0.0:.6f}",
        },
        {
            "metric": "timing_weighted_reduction_mean",
            "value": f"{sum(reductions) / len(reductions) if reductions else 0.0:.6f}",
        },
        {
            "metric": "timing_weighted_reduction_max",
            "value": f"{max(reductions) if reductions else 0.0:.6f}",
        },
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "pseudo3d_realization_summary.csv", rows, list(rows[0].keys()) if rows else ["design"])
    write_csv(output_dir / "pseudo3d_realization_rollup.csv", summary, ["metric", "value"])
    manifest = {
        "note": "Pseudo-3D proxy evaluation. This is not a replacement for true 3D P&R. Cross-tier HPWL exposure is a lower-is-better proxy for planar wirelength carried by inter-tier links.",
        "cases": len(asa_rows),
        "outputs": [
            str(output_dir / "pseudo3d_realization_summary.csv"),
            str(output_dir / "pseudo3d_realization_rollup.csv"),
        ],
    }
    (output_dir / "pseudo3d_realization_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", help="Design to evaluate. Repeatable. Defaults to four-core suite.")
    parser.add_argument("--scenario", action="append", help="Scenario to evaluate. Repeatable. Defaults to all three scenarios.")
    parser.add_argument("--output-root", type=Path, default=Path("results"))
    parser.add_argument("--summary-dir", type=Path, default=Path("results/benchmark_summary"))
    args = parser.parse_args()

    designs = args.design or FOUR_CORE_DESIGNS
    scenarios = args.scenario or SCENARIOS
    cases = ["tritonpart", "asa_rv3d"]

    all_rows: list[dict[str, object]] = []
    for design in designs:
        for scenario in scenarios:
            all_rows.extend(evaluate_design_scenario(design, scenario, args.output_root, cases))

    summarize_suite(all_rows, args.summary_dir)
    print(args.summary_dir / "pseudo3d_realization_summary.csv")
    print(args.summary_dir / "pseudo3d_realization_rollup.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
