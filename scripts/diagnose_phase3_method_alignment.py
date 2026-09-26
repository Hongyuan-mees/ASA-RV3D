#!/usr/bin/env python3
"""Diagnose Phase-3 method alignment before running more experiments.

Outputs three lightweight diagnostic tables:

1. objective contribution scale: architecture / physical / timing contribution
   magnitudes in the current dynamic objective.
2. architecture label consistency: whether assignment labels, timing-context
   labels, and feature fallback labels agree.
3. scenario eligibility: whether each design has observable structures for each
   Phase-3 scenario before using that case as main evidence.

This script does not change assignments or rerun partitioning.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median


DESIGNS = ["picorv32", "riscv32i"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]

SCENARIO_TARGETS = {
    "control_datapath_split": {"control", "generated_control", "datapath", "generated_datapath", "execute_alu"},
    "memory_near_logic": {"register_file", "load_store", "lsu", "memory"},
    "state_and_clock_protected": {"clock_reset", "pipeline_state", "register_state", "csr", "trap_debug"},
}

CONTROL_WORDS = ("control", "decoder", "decode", "branch", "fetch")
DATAPATH_WORDS = (
    "datapath",
    "alu",
    "operand",
    "writedata",
    "readdata",
    "cpuregs",
    "regfile",
    "register_file",
    "load",
    "store",
    "mem",
    "lsu",
)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def normalize_name(name: str) -> str:
    out = (name or "").strip()
    if out.startswith("\\"):
        out = out[1:]
    return out


def split_nets(value: str) -> list[str]:
    if not value:
        return []
    return [x for x in re.split(r"[;|,\s]+", value.strip()) if x and x.lower() not in {"nan", "none", "null"}]


def as_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def scenario_unit_weight(unit: str, group: str, scenario: str) -> float:
    if scenario == "state_and_clock_protected":
        if unit == "clock_reset":
            return 8.0
        if unit == "pipeline_state":
            return 6.0
        if unit in {"csr", "trap_debug"}:
            return 4.0
        if group == "control":
            return 2.0
        if group == "datapath":
            return 1.5
        return 1.0
    if scenario == "memory_near_logic":
        if unit in {"register_file", "load_store"}:
            return 7.0
        if unit in {"execute_alu", "multdiv"}:
            return 3.0
        if group == "datapath":
            return 2.0
        return 1.0
    if scenario == "control_datapath_split":
        if group in {"control", "datapath"}:
            return 3.0
        return 1.0
    return 1.0


def load_assignment_labels(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    unit: dict[str, str] = {}
    group: dict[str, str] = {}
    for row in read_rows(path):
        inst = normalize_name(row.get("instance", ""))
        if not inst:
            continue
        unit[inst] = row.get("architecture_unit", "unclassified") or "unclassified"
        group[inst] = row.get("semantic_group", "infrastructure") or "infrastructure"
    return unit, group


def load_score(path: Path, names: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in read_rows(path):
        inst = normalize_name(row.get("instance", ""))
        if not inst:
            continue
        value = 0.0
        for name in names:
            if row.get(name) not in (None, ""):
                value = as_float(row.get(name))
                break
        scores[inst] = value
    return scores


def load_context_units(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in read_rows(path):
        inst = normalize_name(row.get("instance", ""))
        if not inst:
            continue
        labels[inst] = row.get("architecture_unit", "") or row.get("arch_unit", "") or "unclassified"
    return labels


def infer_feature_unit(row: dict[str, str]) -> str:
    text = " ".join(
        [
            row.get("module", ""),
            row.get("instance", ""),
            row.get("cell_type", ""),
            row.get("category", ""),
            row.get("arch_class", ""),
            row.get("nets", ""),
        ]
    ).lower()
    if "clock" in text or "clk" in text or "reset" in text or "rst" in text:
        return "clock_reset"
    if re.search(r"(dff|dffe|dfxtp|sdff)", text) or "pipeline" in text or "state" in text:
        return "pipeline_state"
    if "csr" in text:
        return "csr"
    if "cpuregs" in text or "register_file" in text or "regfile" in text:
        return "register_file"
    if "mem" in text or "load" in text or "store" in text or "lsu" in text:
        return "load_store"
    if any(word in text for word in CONTROL_WORDS):
        return "generated_control"
    if "alu" in text:
        return "execute_alu"
    if any(word in text for word in DATAPATH_WORDS):
        return "generated_datapath"
    return "unclassified"


def load_feature_units(path: Path) -> dict[str, str]:
    units: dict[str, str] = {}
    for row in read_rows(path):
        inst = normalize_name(row.get("instance", ""))
        if inst:
            units[inst] = infer_feature_unit(row)
    return units


def load_net_graph(path: Path, instances: set[str]) -> dict[str, list[str]]:
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in read_rows(path):
        inst = normalize_name(row.get("instance", ""))
        if inst not in instances:
            continue
        for net in split_nets(row.get("nets", "")):
            net_to_instances[net].append(inst)
    return {net: insts for net, insts in net_to_instances.items() if len(insts) > 1}


def summarize_values(values: list[float]) -> dict[str, str]:
    if not values:
        return {"mean": "0.000000", "median": "0.000000", "max": "0.000000"}
    return {
        "mean": f"{mean(values):.6f}",
        "median": f"{median(values):.6f}",
        "max": f"{max(values):.6f}",
    }


def contribution_rows(root: Path, designs: list[str], scenarios: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for design in designs:
        assignment = root / "results" / f"{design}_tritonpart_design_timing_aware" / "tritonpart_design_timing_aware_assignment.csv"
        arch_unit, semantic_group = load_assignment_labels(assignment)
        physical = load_score(
            root / "results" / f"{design}_features" / "physical_context_scores.csv",
            ["physical_context_score", "raw_physical_score", "mean_physical_context_score"],
        )
        timing = load_score(
            root / "results" / f"{design}_features" / "timing_context_scores.csv",
            ["timing_context_score", "mean_timing_context_score"],
        )
        instances = sorted(arch_unit)
        for scenario in scenarios:
            arch_values = [scenario_unit_weight(arch_unit.get(i, "unclassified"), semantic_group.get(i, "infrastructure"), scenario) for i in instances]
            physical_values = [physical.get(i, 0.0) for i in instances]
            timing_values = [2.0 * timing.get(i, 0.0) for i in instances]
            total_arch = sum(arch_values)
            total_physical = sum(physical_values)
            total_timing = sum(timing_values)
            total = total_arch + total_physical + total_timing
            a = summarize_values(arch_values)
            p = summarize_values(physical_values)
            t = summarize_values(timing_values)
            rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "instances": len(instances),
                    "arch_sum": f"{total_arch:.6f}",
                    "physical_sum": f"{total_physical:.6f}",
                    "timing2x_sum": f"{total_timing:.6f}",
                    "arch_fraction": f"{total_arch / total if total else 0.0:.6f}",
                    "physical_fraction": f"{total_physical / total if total else 0.0:.6f}",
                    "timing2x_fraction": f"{total_timing / total if total else 0.0:.6f}",
                    "arch_mean": a["mean"],
                    "physical_mean": p["mean"],
                    "timing2x_mean": t["mean"],
                    "arch_max": a["max"],
                    "physical_max": p["max"],
                    "timing2x_max": t["max"],
                }
            )
    return rows


def label_consistency_rows(root: Path, designs: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for design in designs:
        assignment = root / "results" / f"{design}_tritonpart_design_timing_aware" / "tritonpart_design_timing_aware_assignment.csv"
        assignment_units, _groups = load_assignment_labels(assignment)
        timing_units = load_context_units(root / "results" / f"{design}_features" / "timing_context_scores.csv")
        feature_units = load_feature_units(root / "results" / f"{design}_features" / "instance_features.csv")
        all_instances = sorted(set(assignment_units) | set(timing_units) | set(feature_units))
        assign_timing_same = 0
        assign_feature_same = 0
        timing_feature_same = 0
        missing_timing = 0
        missing_feature = 0
        for inst in all_instances:
            au = assignment_units.get(inst, "")
            tu = timing_units.get(inst, "")
            fu = feature_units.get(inst, "")
            if not tu:
                missing_timing += 1
            if not fu:
                missing_feature += 1
            if au and tu and au == tu:
                assign_timing_same += 1
            if au and fu and au == fu:
                assign_feature_same += 1
            if tu and fu and tu == fu:
                timing_feature_same += 1
        denom = len(all_instances) or 1
        rows.append(
            {
                "design": design,
                "instances_union": len(all_instances),
                "assignment_labels": len(assignment_units),
                "timing_context_labels": len(timing_units),
                "feature_fallback_labels": len(feature_units),
                "missing_timing_context": missing_timing,
                "missing_feature": missing_feature,
                "assignment_timing_exact_match_fraction": f"{assign_timing_same / denom:.6f}",
                "assignment_feature_exact_match_fraction": f"{assign_feature_same / denom:.6f}",
                "timing_feature_exact_match_fraction": f"{timing_feature_same / denom:.6f}",
                "top_assignment_units": ";".join(f"{k}:{v}" for k, v in Counter(assignment_units.values()).most_common(8)),
                "top_timing_units": ";".join(f"{k}:{v}" for k, v in Counter(timing_units.values()).most_common(8)),
                "top_feature_units": ";".join(f"{k}:{v}" for k, v in Counter(feature_units.values()).most_common(8)),
            }
        )
    return rows


def scenario_eligibility_rows(root: Path, designs: list[str], scenarios: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for design in designs:
        assignment = root / "results" / f"{design}_tritonpart_design_timing_aware" / "tritonpart_design_timing_aware_assignment.csv"
        assignment_units, _groups = load_assignment_labels(assignment)
        feature_path = root / "results" / f"{design}_features" / "instance_features.csv"
        net_graph = load_net_graph(feature_path, set(assignment_units))
        unit_counts = Counter(assignment_units.values())
        for scenario in scenarios:
            targets = SCENARIO_TARGETS[scenario]
            target_instances = {inst for inst, unit in assignment_units.items() if unit in targets}
            target_nets = 0
            for insts in net_graph.values():
                if any(inst in target_instances for inst in insts):
                    target_nets += 1
            target_count = len(target_instances)
            observable_fraction = target_count / len(assignment_units) if assignment_units else 0.0
            eligible = target_count >= 10 and target_nets >= 10
            rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "target_instance_count": target_count,
                    "target_instance_fraction": f"{observable_fraction:.6f}",
                    "target_net_count": target_nets,
                    "eligible_for_main_result": str(eligible).lower(),
                    "target_units": ";".join(sorted(targets)),
                    "target_unit_counts": ";".join(f"{unit}:{unit_counts.get(unit, 0)}" for unit in sorted(targets)),
                    "note": "main_candidate" if eligible else "weak_semantic_coverage",
                }
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/benchmark_summary"),
    )
    args = parser.parse_args()

    designs = args.designs or DESIGNS
    scenarios = args.scenarios or SCENARIOS
    out_dir = args.root / args.out_dir

    contribution = contribution_rows(args.root, designs, scenarios)
    consistency = label_consistency_rows(args.root, designs)
    eligibility = scenario_eligibility_rows(args.root, designs, scenarios)

    write_csv(out_dir / "phase3_objective_contribution_diagnostic.csv", contribution)
    write_csv(out_dir / "phase3_architecture_label_consistency_diagnostic.csv", consistency)
    write_csv(out_dir / "phase3_scenario_eligibility_diagnostic.csv", eligibility)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
