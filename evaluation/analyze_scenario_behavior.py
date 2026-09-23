#!/usr/bin/env python3
"""Analyze scenario-dependent tier-assignment behavior for ASA-RV3D.

This script supports the paper-facing scenario analysis section.  It compares
the strong TritonPart baseline against ASA-RV3D timing-regret guarded repair
for each design/scenario and reports:

- per-architecture-unit tier distribution,
- ASA-RV3D changes relative to TritonPart,
- pairwise assignment differences between scenarios,
- compact rollup metrics.

The analysis is descriptive.  It does not claim that every scenario should move
every architecture unit in a specific direction.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean


DEFAULT_DESIGNS = ("riscv32i", "ibex", "picorv32", "scr1_core_tuned")
DEFAULT_SCENARIOS = (
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
)

UNIT_ORDER = (
    "clock_reset",
    "fetch",
    "decode_control",
    "generated_control",
    "csr",
    "pipeline_state",
    "register_file",
    "execute_alu",
    "load_store",
    "multdiv",
    "generated_datapath",
    "trap_debug",
    "unclassified",
)


def read_assignment(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError(f"empty assignment file: {path}")
    required = {"instance", "tier", "architecture_unit", "semantic_group", "weight"}
    missing = required - set(rows[0])
    if missing:
        raise RuntimeError(f"{path} missing required columns: {sorted(missing)}")
    return {row["instance"]: row for row in rows}


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def fmt(value: float) -> str:
    return f"{value:.6f}"


def assignment_paths(results_dir: Path, design: str, scenario: str) -> tuple[Path, Path]:
    tritonpart = results_dir / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv"
    asa = (
        results_dir
        / f"{design}_tritonpart_timing_regret_guarded_repair"
        / scenario
        / "tritonpart_timing_regret_guarded_repair_assignment.csv"
    )
    return tritonpart, asa


def unit_sort_key(unit: str) -> tuple[int, str]:
    try:
        return (UNIT_ORDER.index(unit), unit)
    except ValueError:
        return (len(UNIT_ORDER), unit)


def summarize_units(
    design: str,
    scenario: str,
    case: str,
    assignment_file: Path,
    assignment: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    by_unit: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignment.values():
        by_unit[row["architecture_unit"]].append(row)

    rows: list[dict[str, object]] = []
    for unit in sorted(by_unit, key=unit_sort_key):
        items = by_unit[unit]
        tier_counts = Counter(row["tier"] for row in items)
        total_instances = len(items)
        total_weight = sum(int(row["weight"]) for row in items)
        tier0_weight = sum(int(row["weight"]) for row in items if row["tier"] == "tier0")
        tier1_weight = sum(int(row["weight"]) for row in items if row["tier"] == "tier1")
        semantic_group = Counter(row["semantic_group"] for row in items).most_common(1)[0][0]
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "architecture_unit": unit,
                "semantic_group": semantic_group,
                "instance_count": total_instances,
                "tier0_instances": tier_counts["tier0"],
                "tier1_instances": tier_counts["tier1"],
                "tier0_instance_fraction": fmt(tier_counts["tier0"] / total_instances),
                "tier1_instance_fraction": fmt(tier_counts["tier1"] / total_instances),
                "total_weight": total_weight,
                "tier0_weight": tier0_weight,
                "tier1_weight": tier1_weight,
                "tier0_weight_fraction": fmt(tier0_weight / total_weight if total_weight else 0.0),
                "assignment_file": str(assignment_file),
            }
        )
    return rows


def semantic_summary(
    design: str,
    scenario: str,
    case: str,
    assignment_file: Path,
    assignment: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in assignment.values():
        by_group[row["semantic_group"]].append(row)

    rows: list[dict[str, object]] = []
    for group in sorted(by_group):
        items = by_group[group]
        total = len(items)
        tier0 = sum(1 for row in items if row["tier"] == "tier0")
        weight = sum(int(row["weight"]) for row in items)
        tier0_weight = sum(int(row["weight"]) for row in items if row["tier"] == "tier0")
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "semantic_group": group,
                "instance_count": total,
                "tier0_instances": tier0,
                "tier1_instances": total - tier0,
                "tier0_instance_fraction": fmt(tier0 / total),
                "tier0_weight_fraction": fmt(tier0_weight / weight if weight else 0.0),
                "assignment_file": str(assignment_file),
            }
        )
    return rows


def build_delta_rows(
    unit_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in unit_rows:
        key = (str(row["design"]), str(row["scenario"]), str(row["architecture_unit"]))
        by_key[key][str(row["case"])] = row

    delta_rows: list[dict[str, object]] = []
    for (design, scenario, unit), cases in sorted(by_key.items()):
        base = cases.get("tritonpart")
        asa = cases.get("asa_rv3d")
        if not base or not asa:
            continue
        base_frac = float(base["tier0_instance_fraction"])
        asa_frac = float(asa["tier0_instance_fraction"])
        base_weight_frac = float(base["tier0_weight_fraction"])
        asa_weight_frac = float(asa["tier0_weight_fraction"])
        delta_rows.append(
            {
                "design": design,
                "scenario": scenario,
                "architecture_unit": unit,
                "semantic_group": asa["semantic_group"],
                "instance_count": asa["instance_count"],
                "tritonpart_tier0_instance_fraction": fmt(base_frac),
                "asa_rv3d_tier0_instance_fraction": fmt(asa_frac),
                "delta_tier0_instance_fraction": fmt(asa_frac - base_frac),
                "abs_delta_tier0_instance_fraction": fmt(abs(asa_frac - base_frac)),
                "tritonpart_tier0_weight_fraction": fmt(base_weight_frac),
                "asa_rv3d_tier0_weight_fraction": fmt(asa_weight_frac),
                "delta_tier0_weight_fraction": fmt(asa_weight_frac - base_weight_frac),
                "abs_delta_tier0_weight_fraction": fmt(abs(asa_weight_frac - base_weight_frac)),
            }
        )
    return delta_rows


def pairwise_scenario_rows(
    design: str,
    asa_by_scenario: dict[str, dict[str, dict[str, str]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    scenarios = sorted(asa_by_scenario)
    for i, left in enumerate(scenarios):
        for right in scenarios[i + 1 :]:
            a = asa_by_scenario[left]
            b = asa_by_scenario[right]
            common = sorted(set(a) & set(b))
            if not common:
                continue
            changed = sum(1 for inst in common if a[inst]["tier"] != b[inst]["tier"])
            unit_changed = Counter(a[inst]["architecture_unit"] for inst in common if a[inst]["tier"] != b[inst]["tier"])
            top_unit, top_unit_count = ("", 0)
            if unit_changed:
                top_unit, top_unit_count = unit_changed.most_common(1)[0]
            rows.append(
                {
                    "design": design,
                    "scenario_a": left,
                    "scenario_b": right,
                    "common_instances": len(common),
                    "changed_instances": changed,
                    "changed_fraction": fmt(changed / len(common)),
                    "top_changed_architecture_unit": top_unit,
                    "top_changed_architecture_unit_instances": top_unit_count,
                }
            )
    return rows


def scenario_metric_rows(
    semantic_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in semantic_rows:
        key = (str(row["design"]), str(row["scenario"]), str(row["case"]))
        by_key[key][str(row["semantic_group"])] = row

    rows: list[dict[str, object]] = []
    for (design, scenario, case), groups in sorted(by_key.items()):
        control = float(groups.get("control", {}).get("tier0_instance_fraction", 0.0))
        datapath = float(groups.get("datapath", {}).get("tier0_instance_fraction", 0.0))
        infrastructure = float(groups.get("infrastructure", {}).get("tier0_instance_fraction", 0.0))
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "case": case,
                "control_tier0_fraction": fmt(control),
                "datapath_tier0_fraction": fmt(datapath),
                "infrastructure_tier0_fraction": fmt(infrastructure),
                "control_datapath_tier0_gap": fmt(abs(control - datapath)),
                "control_infrastructure_tier0_gap": fmt(abs(control - infrastructure)),
                "datapath_infrastructure_tier0_gap": fmt(abs(datapath - infrastructure)),
            }
        )
    return rows


def rollup_rows(
    delta_rows: list[dict[str, object]],
    pairwise_rows: list[dict[str, object]],
    metric_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    deltas = [float(row["abs_delta_tier0_instance_fraction"]) for row in delta_rows]
    pairwise = [float(row["changed_fraction"]) for row in pairwise_rows]
    gaps = [float(row["control_datapath_tier0_gap"]) for row in metric_rows if row["case"] == "asa_rv3d"]
    rows = [
        {"metric": "cases", "value": len({(row["design"], row["scenario"]) for row in metric_rows})},
        {"metric": "designs", "value": ",".join(sorted({str(row["design"]) for row in metric_rows}))},
        {"metric": "mean_abs_unit_tier0_delta_vs_tritonpart", "value": fmt(mean(deltas) if deltas else 0.0)},
        {"metric": "max_abs_unit_tier0_delta_vs_tritonpart", "value": fmt(max(deltas) if deltas else 0.0)},
        {"metric": "mean_pairwise_scenario_changed_fraction", "value": fmt(mean(pairwise) if pairwise else 0.0)},
        {"metric": "max_pairwise_scenario_changed_fraction", "value": fmt(max(pairwise) if pairwise else 0.0)},
        {"metric": "mean_asa_control_datapath_tier0_gap", "value": fmt(mean(gaps) if gaps else 0.0)},
    ]
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    args = parser.parse_args()

    designs = tuple(args.designs or DEFAULT_DESIGNS)
    scenarios = tuple(args.scenarios or DEFAULT_SCENARIOS)

    unit_rows: list[dict[str, object]] = []
    semantic_rows: list[dict[str, object]] = []
    pairwise_rows: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []

    for design in designs:
        asa_by_scenario: dict[str, dict[str, dict[str, str]]] = {}
        for scenario in scenarios:
            tritonpart_path, asa_path = assignment_paths(args.results_dir, design, scenario)
            if not tritonpart_path.exists() or not asa_path.exists():
                missing_rows.append(
                    {
                        "design": design,
                        "scenario": scenario,
                        "missing_tritonpart_assignment": "" if tritonpart_path.exists() else str(tritonpart_path),
                        "missing_asa_assignment": "" if asa_path.exists() else str(asa_path),
                    }
                )
                continue

            tritonpart = read_assignment(tritonpart_path)
            asa = read_assignment(asa_path)
            asa_by_scenario[scenario] = asa

            unit_rows.extend(summarize_units(design, scenario, "tritonpart", tritonpart_path, tritonpart))
            unit_rows.extend(summarize_units(design, scenario, "asa_rv3d", asa_path, asa))
            semantic_rows.extend(semantic_summary(design, scenario, "tritonpart", tritonpart_path, tritonpart))
            semantic_rows.extend(semantic_summary(design, scenario, "asa_rv3d", asa_path, asa))

        pairwise_rows.extend(pairwise_scenario_rows(design, asa_by_scenario))

    delta_rows = build_delta_rows(unit_rows)
    metric_rows = scenario_metric_rows(semantic_rows)
    rollup = rollup_rows(delta_rows, pairwise_rows, metric_rows)

    write_csv(
        args.output_dir / "scenario_behavior_unit_tier_summary.csv",
        [
            "design",
            "scenario",
            "case",
            "architecture_unit",
            "semantic_group",
            "instance_count",
            "tier0_instances",
            "tier1_instances",
            "tier0_instance_fraction",
            "tier1_instance_fraction",
            "total_weight",
            "tier0_weight",
            "tier1_weight",
            "tier0_weight_fraction",
            "assignment_file",
        ],
        unit_rows,
    )
    write_csv(
        args.output_dir / "scenario_behavior_semantic_tier_summary.csv",
        [
            "design",
            "scenario",
            "case",
            "semantic_group",
            "instance_count",
            "tier0_instances",
            "tier1_instances",
            "tier0_instance_fraction",
            "tier0_weight_fraction",
            "assignment_file",
        ],
        semantic_rows,
    )
    write_csv(
        args.output_dir / "scenario_behavior_delta_summary.csv",
        [
            "design",
            "scenario",
            "architecture_unit",
            "semantic_group",
            "instance_count",
            "tritonpart_tier0_instance_fraction",
            "asa_rv3d_tier0_instance_fraction",
            "delta_tier0_instance_fraction",
            "abs_delta_tier0_instance_fraction",
            "tritonpart_tier0_weight_fraction",
            "asa_rv3d_tier0_weight_fraction",
            "delta_tier0_weight_fraction",
            "abs_delta_tier0_weight_fraction",
        ],
        delta_rows,
    )
    write_csv(
        args.output_dir / "scenario_behavior_pairwise_summary.csv",
        [
            "design",
            "scenario_a",
            "scenario_b",
            "common_instances",
            "changed_instances",
            "changed_fraction",
            "top_changed_architecture_unit",
            "top_changed_architecture_unit_instances",
        ],
        pairwise_rows,
    )
    write_csv(
        args.output_dir / "scenario_behavior_semantic_gap_summary.csv",
        [
            "design",
            "scenario",
            "case",
            "control_tier0_fraction",
            "datapath_tier0_fraction",
            "infrastructure_tier0_fraction",
            "control_datapath_tier0_gap",
            "control_infrastructure_tier0_gap",
            "datapath_infrastructure_tier0_gap",
        ],
        metric_rows,
    )
    write_csv(args.output_dir / "scenario_behavior_rollup.csv", ["metric", "value"], rollup)
    write_csv(
        args.output_dir / "scenario_behavior_missing_inputs.csv",
        ["design", "scenario", "missing_tritonpart_assignment", "missing_asa_assignment"],
        missing_rows,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
