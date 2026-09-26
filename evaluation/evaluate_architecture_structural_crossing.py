#!/usr/bin/env python3
"""Evaluate architecture-structural crossing metrics for Phase-3 assignments.

This evaluator answers a different question from generic cutsize or
timing-weighted crossing:

    Does architecture-aware refinement reduce crossings involving the
    architecture structures that a scenario claims to protect?

It compares native timing-aware TritonPart, architecture-OFF constrained
refinement, and architecture-ON constrained refinement using one fixed
structural metric implementation.

Architecture labels are evaluated from the original recovered mapping
(`timing_context_scores.csv` and feature tables), not from the repair objective
used by a particular assignment.  This keeps architecture-ON/OFF evaluation
fair: architecture-OFF assignments are still scored against the same recovered
RISC-V structures as architecture-ON assignments.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.net_graph_utils import (  # noqa: E402
    assignment_tiers,
    load_feature_net_graph,
    net_is_crossing,
    normalize_lookup_name,
    tier_for_instance as shared_tier_for_instance,
)


DEFAULT_DESIGNS = ["picorv32", "riscv32i"]
DEFAULT_SCENARIOS = ["state_and_clock_protected"]


SCENARIO_TARGETS = {
    "state_and_clock_protected": {
        "clock_reset",
        "pipeline_state",
        "csr",
        "state",
        "register_state",
    },
    "memory_near_logic": {
        "register_file",
        "load_store",
        "lsu",
        "memory",
        "mem",
    },
    "control_datapath_split": {
        "generated_control",
        "control",
        "generated_datapath",
        "datapath",
        "execute_alu",
    },
}


CONTROL_UNITS = {
    "generated_control",
    "control",
    "decoder_control",
    "fetch",
    "decode",
    "branch",
}
DATAPATH_UNITS = {
    "generated_datapath",
    "datapath",
    "execute_alu",
    "register_file",
    "load_store",
    "lsu",
    "memory",
    "pipeline_state",
    "register_state",
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


def normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    # Match the lightweight normalization used elsewhere in the project:
    # OpenROAD/Yosys names often differ around escaped generated-cell suffixes.
    return (
        name.replace("\\", "")
        .replace("$", "")
        .replace("*", "")
        .replace("/", ".")
        .strip()
    )


def split_nets(value: str) -> list[str]:
    if not value:
        return []
    raw = re.split(r"[;|,\s]+", value.strip())
    return [x for x in raw if x and x.lower() not in {"nan", "none", "null"}]


def read_rows(path: Path) -> list[dict[str, str]]:
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


def first_existing(row: dict[str, str], names: list[str]) -> str:
    for name in names:
        value = row.get(name, "")
        if value != "":
            return value
    return ""


def load_assignment(path: Path) -> dict[str, str]:
    return assignment_tiers(path)


def unit_aliases(value: str) -> set[str]:
    units = {x.lower() for x in split_nets(value.replace(" ", "_")) if x}
    expanded = set(units)
    text = " ".join(units)
    if any(word in text for word in CONTROL_WORDS):
        expanded.update({"control", "generated_control"})
    if any(word in text for word in DATAPATH_WORDS):
        expanded.update({"datapath", "generated_datapath"})
    if "decoder_control" in text:
        expanded.update({"control", "generated_control"})
    if "clock" in text or "clk" in text or "reset" in text or "rst" in text:
        expanded.add("clock_reset")
    if "pipeline_state" in text or "register_state" in text or "state" in text:
        expanded.update({"pipeline_state", "register_state"})
    if "csr" in text:
        expanded.add("csr")
    if "register_file" in text or "regfile" in text or "cpuregs" in text:
        expanded.add("register_file")
    if "load_store" in text or "lsu" in text or "memory" in text or "mem" in text:
        expanded.update({"load_store", "memory"})
    if "alu" in text:
        expanded.add("execute_alu")
    return {u for u in expanded if u}


def load_context_units(path: Path) -> dict[str, set[str]]:
    if not path.exists():
        return {}
    inst_to_units: dict[str, set[str]] = defaultdict(set)
    unit_columns = [
        "architecture_unit",
        "arch_unit",
        "semantic_unit",
        "architecture_group",
        "unit",
        "category",
        "arch_class",
    ]
    for row in read_rows(path):
        inst = first_existing(row, ["instance", "inst", "name", "cell"])
        if not inst:
            continue
        units: set[str] = set()
        for col in unit_columns:
            units.update(unit_aliases(row.get(col, "")))
        units.discard("unclassified")
        units.discard("infrastructure")
        if units:
            inst_to_units[inst].update(units)
            inst_to_units[normalize_name(inst)].update(units)
    return dict(inst_to_units)


def load_feature_graph(
    features_path: Path,
    base_units: dict[str, set[str]],
    assignment_instances: set[str],
) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    rows = read_rows(features_path)
    graph = load_feature_net_graph(features_path, assignment_instances)
    inst_to_units: dict[str, set[str]] = defaultdict(set)
    for inst, units in base_units.items():
        inst_to_units[inst].update(units)
    for row in rows:
        inst = first_existing(row, ["instance", "inst", "name", "cell"])
        if not inst:
            continue
        fallback_units = infer_units(row)
        names = {inst, normalize_name(inst)}
        for name in names:
            if not inst_to_units.get(name):
                inst_to_units[name].update(fallback_units)

    return graph.net_to_instances, dict(inst_to_units)


def infer_units(row: dict[str, str]) -> set[str]:
    """Infer architecture-structural tags from the public feature columns.

    Current feature tables expose `category` and `arch_class` rather than the
    older `architecture_unit` column.  Keep raw labels and add coarse tags used
    by the structural evaluator.
    """

    labels = {
        first_existing(
            row,
            [
                "architecture_unit",
                "arch_unit",
                "semantic_unit",
                "architecture_group",
                "unit",
                "category",
                "arch_class",
            ],
        )
    }
    labels.update(split_nets(row.get("category", "")))
    labels.update(split_nets(row.get("arch_class", "")))
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

    units = {label for label in labels if label}
    if "clock" in text or "clk" in text or "reset" in text or "rst" in text:
        units.add("clock_reset")
    if "clock_buffer" in text:
        units.add("clock_reset")
    if re.search(r"(dff|dffe|dfxtp|sdff)", text) or "pipeline" in text or "state" in text:
        units.add("pipeline_state")
        units.add("register_state")
    if "csr" in text:
        units.add("csr")
    if "cpuregs" in text or "register_file" in text or re.search(r"\brf\b", text) or "regfile" in text:
        units.add("register_file")
    if "mem" in text or "load" in text or "store" in text or "lsu" in text:
        units.add("load_store")
        units.add("memory")
    if any(word in text for word in CONTROL_WORDS):
        units.add("control")
        units.add("generated_control")
    if any(word in text for word in DATAPATH_WORDS):
        units.add("datapath")
        units.add("generated_datapath")
    if "alu" in text:
        units.add("execute_alu")
    return units or {"unclassified"}


def units_for_instances(instances: list[str], inst_to_units: dict[str, set[str]]) -> set[str]:
    units: set[str] = set()
    for inst in instances:
        units.update(inst_to_units.get(inst, set()))
        units.update(inst_to_units.get(normalize_name(inst), set()))
        units.update(inst_to_units.get(normalize_lookup_name(inst), set()))
    return units


def crossing_for_net(instances: list[str], tiers: dict[str, str]) -> bool:
    return net_is_crossing(tiers, instances)


def tier_for_instance(inst: str, tiers: dict[str, str]) -> str:
    return shared_tier_for_instance(inst, tiers)


def net_has_control_datapath_boundary(
    instances: list[str],
    tiers: dict[str, str],
    inst_to_units: dict[str, set[str]],
) -> bool:
    """Return true for crossing nets connecting control-side and datapath-side cells.

    This is intentionally instance-based rather than net-union based.  A net
    counts only when it has at least one control-like endpoint and at least one
    datapath-like endpoint, and those endpoint classes are observed on opposite
    tiers.  That makes `control_datapath_boundary_crossing_nets` a direct
    structural metric for the control/datapath scenario instead of a generic
    "important architecture unit touched this net" proxy.
    """

    control_tiers: set[str] = set()
    datapath_tiers: set[str] = set()
    for inst in instances:
        tier = tier_for_instance(inst, tiers)
        if not tier:
            continue
        units = inst_to_units.get(inst, set()) | inst_to_units.get(normalize_name(inst), set())
        units.update(inst_to_units.get(normalize_lookup_name(inst), set()))
        if units & CONTROL_UNITS:
            control_tiers.add(tier)
        if units & DATAPATH_UNITS:
            datapath_tiers.add(tier)
    return bool(control_tiers and datapath_tiers and (control_tiers - datapath_tiers or datapath_tiers - control_tiers))


def summarize_assignment(
    *,
    design: str,
    scenario: str,
    case: str,
    assignment: Path,
    features: Path,
    context_units: dict[str, set[str]],
) -> dict[str, object]:
    tiers = load_assignment(assignment)
    assignment_instances = {
        normalize_name(first_existing(row, ["instance", "inst", "name", "cell"]))
        for row in read_rows(assignment)
        if first_existing(row, ["instance", "inst", "name", "cell"])
    }
    net_to_instances, inst_to_units = load_feature_graph(features, context_units, assignment_instances)
    targets = SCENARIO_TARGETS.get(scenario, set())

    crossing = 0
    scenario_sensitive = 0
    clock_reset = 0
    pipeline_state = 0
    csr = 0
    register_file = 0
    load_store = 0
    control_datapath_boundary = 0

    for net, instances in net_to_instances.items():
        if not crossing_for_net(instances, tiers):
            continue
        crossing += 1
        units = units_for_instances(instances, inst_to_units)
        boundary = net_has_control_datapath_boundary(instances, tiers, inst_to_units)
        if scenario == "control_datapath_split":
            is_scenario_sensitive = boundary
        else:
            is_scenario_sensitive = bool(units & targets)
        if is_scenario_sensitive:
            scenario_sensitive += 1
        if "clock_reset" in units:
            clock_reset += 1
        if "pipeline_state" in units:
            pipeline_state += 1
        if "csr" in units:
            csr += 1
        if "register_file" in units:
            register_file += 1
        if units & {"load_store", "lsu"}:
            load_store += 1
        if boundary:
            control_datapath_boundary += 1

    return {
        "design": design,
        "scenario": scenario,
        "case": case,
        "assignment_file": str(assignment),
        "structural_crossing_nets": crossing,
        "scenario_sensitive_crossing_nets": scenario_sensitive,
        "scenario_sensitive_crossing_fraction": f"{(scenario_sensitive / crossing) if crossing else 0.0:.6f}",
        "clock_reset_crossing_nets": clock_reset,
        "pipeline_state_crossing_nets": pipeline_state,
        "csr_crossing_nets": csr,
        "register_file_crossing_nets": register_file,
        "load_store_crossing_nets": load_store,
        "control_datapath_boundary_crossing_nets": control_datapath_boundary,
    }


def assignment_paths(root: Path, design: str, scenario: str) -> dict[str, Path]:
    return {
        "native_timing_aware": root
        / "results"
        / f"{design}_tritonpart_design_timing_aware"
        / "tritonpart_design_timing_aware_assignment.csv",
        "architecture_off": root
        / "results"
        / f"{design}_tritonpart_compatible_dynamic_architecture_off_canonical_checkpoint"
        / scenario
        / "dynamic_canonical_selected_checkpoint_assignment.csv",
        "architecture_on": root
        / "results"
        / f"{design}_tritonpart_compatible_dynamic_canonical_checkpoint"
        / scenario
        / "dynamic_canonical_selected_checkpoint_assignment.csv",
    }


def pct_reduction(before: float, after: float) -> float:
    return (before - after) / before if before else 0.0


def infer_design_from_path(path: Path) -> str:
    text = str(path)
    candidates = ["picorv32", "riscv32i", "ibex", "scr1_core_tuned", "serv"]
    for design in candidates:
        if design in text:
            return design
    raise SystemExit(
        "could not infer design from assignment path; pass --design <design> "
        "when using explicit assignment mode"
    )


def build_rollup(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rollup: list[dict[str, object]] = []
    grouped: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in rows:
        if row.get("status") == "missing_assignment":
            continue
        grouped[(str(row["design"]), str(row["scenario"]))][str(row["case"])] = row
    for (design, scenario), cases in sorted(grouped.items()):
        native = cases.get("native_timing_aware")
        off = cases.get("architecture_off")
        on = cases.get("architecture_on")
        if not native or not off or not on:
            continue
        metric = "scenario_sensitive_crossing_nets"
        native_v = float(native[metric])
        off_v = float(off[metric])
        on_v = float(on[metric])
        rollup.append(
            {
                "design": design,
                "scenario": scenario,
                "native_scenario_sensitive_crossing_nets": f"{native_v:.0f}",
                "architecture_off_scenario_sensitive_crossing_nets": f"{off_v:.0f}",
                "architecture_on_scenario_sensitive_crossing_nets": f"{on_v:.0f}",
                "architecture_on_reduction_vs_native": f"{pct_reduction(native_v, on_v):.6f}",
                "architecture_on_reduction_vs_off": f"{pct_reduction(off_v, on_v):.6f}",
                "architecture_on_better_than_off": str(on_v < off_v).lower(),
            }
        )
    return rollup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--native-assignment", type=Path)
    parser.add_argument("--architecture-off-assignment", type=Path)
    parser.add_argument("--architecture-on-assignment", type=Path)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        help=(
            "Explicit-assignment mode output prefix. Writes "
            "<prefix>_summary.csv and <prefix>_rollup.csv."
        ),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_architecture_structural_phase3_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_architecture_structural_phase3_rollup.csv"),
    )
    args = parser.parse_args()

    explicit_paths = [
        args.native_assignment,
        args.architecture_off_assignment,
        args.architecture_on_assignment,
    ]
    if any(explicit_paths):
        if not all(explicit_paths):
            raise SystemExit(
                "explicit assignment mode requires --native-assignment, "
                "--architecture-off-assignment, and --architecture-on-assignment"
            )
        if not args.output_prefix:
            raise SystemExit("explicit assignment mode requires --output-prefix")
        scenarios = args.scenarios or []
        if len(scenarios) != 1:
            raise SystemExit("explicit assignment mode requires exactly one --scenario")
        design = args.designs[0] if args.designs else infer_design_from_path(args.native_assignment)
        scenario = scenarios[0]
        features = args.root / "results" / f"{design}_features" / "instance_features.csv"
        context_units = load_context_units(args.root / "results" / f"{design}_features" / "timing_context_scores.csv")
        rows = [
            summarize_assignment(
                design=design,
                scenario=scenario,
                case="native_timing_aware",
                assignment=args.root / args.native_assignment,
                features=features,
                context_units=context_units,
            ),
            summarize_assignment(
                design=design,
                scenario=scenario,
                case="architecture_off",
                assignment=args.root / args.architecture_off_assignment,
                features=features,
                context_units=context_units,
            ),
            summarize_assignment(
                design=design,
                scenario=scenario,
                case="architecture_on",
                assignment=args.root / args.architecture_on_assignment,
                features=features,
                context_units=context_units,
            ),
        ]
        summary = args.root / args.output_prefix.with_name(args.output_prefix.name + "_summary.csv")
        rollup = args.root / args.output_prefix.with_name(args.output_prefix.name + "_rollup.csv")
        write_csv(summary, rows)
        write_csv(rollup, build_rollup(rows))
        return 0

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    rows: list[dict[str, object]] = []
    for design in designs:
        features = args.root / "results" / f"{design}_features" / "instance_features.csv"
        context_units = load_context_units(args.root / "results" / f"{design}_features" / "timing_context_scores.csv")
        for scenario in scenarios:
            for case, assignment in assignment_paths(args.root, design, scenario).items():
                if not assignment.exists():
                    rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "case": case,
                            "status": "missing_assignment",
                            "assignment_file": str(assignment),
                        }
                    )
                    continue
                rows.append(
                    summarize_assignment(
                        design=design,
                        scenario=scenario,
                        case=case,
                        assignment=assignment,
                        features=features,
                        context_units=context_units,
                    )
                )
    write_csv(args.root / args.summary, rows)

    write_csv(args.root / args.rollup, build_rollup(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
