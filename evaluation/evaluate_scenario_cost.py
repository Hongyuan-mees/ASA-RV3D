#!/usr/bin/env python3
"""Evaluate tier assignments under RISC-V 3D integration scenarios.

Stage 3 of the ASA-RV3D plan:

  architecture template
  + gate-level architecture mapping
  + scenario-specific 3D cost model
  -> scenario cost comparison

This script evaluates existing assignments under multiple scenario definitions
from configs/3d_integration_scenarios.yaml. It does not create a new partition.
That comes later in scenario-aware partitioning.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_SCENARIOS = {
    "logic_on_logic": {
        "cost_weights": {
            "base_crossing": 1.0,
            "high_fanout": 0.35,
            "control_datapath_boundary": 1.5,
            "architecture_criticality": 1.0,
            "semantic_uncertainty": 1.0,
            "instance_balance": 0.5,
            "weight_balance": 0.08,
        },
        "architecture_unit_multipliers": {
            "clock_reset": 2.0,
            "pipeline_state": 1.4,
            "register_file": 1.3,
            "load_store": 1.2,
            "generated_control": 1.0,
            "generated_datapath": 1.0,
        },
    },
    "memory_near_logic": {
        "cost_weights": {
            "base_crossing": 1.0,
            "high_fanout": 0.25,
            "control_datapath_boundary": 1.2,
            "architecture_criticality": 1.4,
            "semantic_uncertainty": 1.0,
            "instance_balance": 0.45,
            "weight_balance": 0.08,
        },
        "architecture_unit_multipliers": {
            "load_store": 2.5,
            "register_file": 2.0,
            "generated_datapath": 1.5,
            "execute_alu": 1.3,
            "clock_reset": 1.5,
            "generated_control": 0.9,
        },
    },
    "control_datapath_split": {
        "cost_weights": {
            "base_crossing": 1.0,
            "high_fanout": 0.20,
            "control_datapath_boundary": 4.0,
            "architecture_criticality": 1.1,
            "semantic_uncertainty": 1.3,
            "instance_balance": 0.40,
            "weight_balance": 0.07,
        },
        "architecture_unit_multipliers": {
            "decode_control": 1.8,
            "csr": 1.6,
            "fetch": 1.5,
            "execute_alu": 1.5,
            "generated_datapath": 1.4,
            "register_file": 1.3,
            "clock_reset": 1.5,
        },
    },
    "state_and_clock_protected": {
        "cost_weights": {
            "base_crossing": 1.0,
            "high_fanout": 0.30,
            "control_datapath_boundary": 1.5,
            "architecture_criticality": 1.8,
            "semantic_uncertainty": 1.2,
            "instance_balance": 0.50,
            "weight_balance": 0.10,
        },
        "architecture_unit_multipliers": {
            "clock_reset": 3.0,
            "pipeline_state": 2.4,
            "register_file": 2.2,
            "csr": 2.0,
            "trap_debug": 1.8,
            "generated_control": 1.0,
            "generated_datapath": 1.0,
        },
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_scenarios(path: Path) -> dict[str, dict[str, dict[str, float]]]:
    """Parse the project scenario YAML without requiring PyYAML."""
    if not path.exists():
        return DEFAULT_SCENARIOS

    scenarios: dict[str, dict[str, dict[str, float]]] = {}
    in_scenarios = False
    current: str | None = None
    current_map: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "scenarios:":
            in_scenarios = True
            continue
        if not in_scenarios:
            continue

        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            scenarios[current] = {
                "cost_weights": {},
                "architecture_unit_multipliers": {},
            }
            current_map = None
            continue

        if current is None:
            continue

        if line.startswith("    ") and not line.startswith("      ") and stripped.endswith(":"):
            key = stripped[:-1]
            current_map = key if key in {"cost_weights", "architecture_unit_multipliers"} else None
            continue

        if current_map and line.startswith("      ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            try:
                scenarios[current][current_map][key.strip()] = float(scalar(value))
            except ValueError:
                pass

    return scenarios or DEFAULT_SCENARIOS


def load_assignment(path: Path) -> dict[str, str]:
    return {row["instance"]: row["tier"] for row in read_csv(path)}


def parse_assignment_spec(spec: str) -> tuple[str, Path]:
    if "=" not in spec:
        path = Path(spec)
        return path.stem, path
    case, path = spec.split("=", 1)
    return case, Path(path)


def load_design(features_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    feature_rows = read_csv(features_dir / "instance_features.csv")
    mapping_path = features_dir / "architecture_mapping_instances.csv"
    mapping = {row["instance"]: row for row in read_csv(mapping_path)} if mapping_path.exists() else {}

    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)

    for row in feature_rows:
        inst = row["instance"]
        mapped = mapping.get(inst, {})
        enriched = dict(row)
        enriched["architecture_unit"] = mapped.get("architecture_unit", "unclassified")
        enriched["semantic_group"] = mapped.get("semantic_group", "infrastructure")
        enriched["criticality_weight"] = mapped.get("criticality_weight", "1.0")
        enriched["mapping_confidence"] = mapped.get("mapping_confidence", "0.5")
        instances[inst] = enriched
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return instances, net_to_instances


def balance_ratio(a: int, b: int) -> float:
    high = max(a, b)
    low = min(a, b)
    return low / high if high else 1.0


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        return float(row.get(key, default))
    except ValueError:
        return default


def scenario_arch_weight(
    units: set[str],
    instances: list[str],
    instance_rows: dict[str, dict[str, str]],
    multipliers: dict[str, float],
) -> float:
    weights = []
    for inst in instances:
        row = instance_rows[inst]
        unit = row["architecture_unit"]
        base = f(row, "criticality_weight", 1.0)
        mult = multipliers.get(unit, 1.0)
        weights.append(base * mult)
    return max(weights, default=1.0)


def evaluate(
    design: str,
    scenario_name: str,
    scenario: dict[str, dict[str, float]],
    case: str,
    assignment_path: Path,
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    assignment = load_assignment(assignment_path)
    weights = scenario["cost_weights"]
    multipliers = scenario["architecture_unit_multipliers"]

    tier_counts = Counter()
    tier_weights = Counter()
    for inst, tier in assignment.items():
        if inst not in instances:
            continue
        tier_counts[tier] += 1
        tier_weights[tier] += max(1, int(instances[inst].get("net_count", "0") or 0))

    totals = Counter()
    unit_cost = Counter()

    for net, connected_all in net_to_instances.items():
        connected = [inst for inst in connected_all if inst in assignment and inst in instances]
        if not connected:
            continue
        tiers = Counter(assignment[inst] for inst in connected)
        total_conn = len(connected)
        totals["total_net_connections"] += total_conn
        if len(tiers) <= 1:
            continue

        crossing = min(tiers.values())
        units = {instances[inst]["architecture_unit"] for inst in connected}
        groups = {instances[inst]["semantic_group"] for inst in connected}
        confidence = [f(instances[inst], "mapping_confidence", 0.5) for inst in connected]
        mean_confidence = sum(confidence) / len(confidence) if confidence else 0.5

        base_cost = crossing * weights.get("base_crossing", 1.0)
        high_fanout_cost = crossing * max(0, total_conn - 8) * weights.get("high_fanout", 0.0)
        boundary_cost = crossing * weights.get("control_datapath_boundary", 0.0) if {"control", "datapath"}.issubset(groups) else 0.0
        arch_cost = crossing * scenario_arch_weight(units, connected, instances, multipliers) * weights.get("architecture_criticality", 1.0)
        uncertainty_cost = crossing * (1.0 - mean_confidence) * weights.get("semantic_uncertainty", 0.0)
        total_cost = base_cost + high_fanout_cost + boundary_cost + arch_cost + uncertainty_cost

        totals["crossing_nets"] += 1
        totals["crossing_connections_proxy"] += crossing
        totals["base_crossing_cost"] += base_cost
        totals["high_fanout_cost"] += high_fanout_cost
        totals["boundary_cost"] += boundary_cost
        totals["architecture_cost"] += arch_cost
        totals["semantic_uncertainty_cost"] += uncertainty_cost
        totals["scenario_proxy_cost"] += total_cost

        for unit in units:
            unit_cost[unit] += total_cost / max(1, len(units))

    instance_balance = balance_ratio(tier_counts["tier0"], tier_counts["tier1"])
    weight_balance = balance_ratio(tier_weights["tier0"], tier_weights["tier1"])
    balance_penalty = (1.0 - instance_balance) * weights.get("instance_balance", 0.0) * 1000.0
    weight_penalty = (1.0 - weight_balance) * weights.get("weight_balance", 0.0) * 1000.0
    objective = totals["scenario_proxy_cost"] + balance_penalty + weight_penalty

    summary = {
        "design": design,
        "scenario": scenario_name,
        "case": case,
        "assignment_file": str(assignment_path),
        "tier0_instances": tier_counts["tier0"],
        "tier1_instances": tier_counts["tier1"],
        "instance_balance_ratio": f"{instance_balance:.6f}",
        "tier0_weight": tier_weights["tier0"],
        "tier1_weight": tier_weights["tier1"],
        "weight_balance_ratio": f"{weight_balance:.6f}",
        "crossing_nets": totals["crossing_nets"],
        "crossing_connections_proxy": totals["crossing_connections_proxy"],
        "base_crossing_cost": f"{totals['base_crossing_cost']:.6f}",
        "high_fanout_cost": f"{totals['high_fanout_cost']:.6f}",
        "boundary_cost": f"{totals['boundary_cost']:.6f}",
        "architecture_cost": f"{totals['architecture_cost']:.6f}",
        "semantic_uncertainty_cost": f"{totals['semantic_uncertainty_cost']:.6f}",
        "scenario_proxy_cost": f"{totals['scenario_proxy_cost']:.6f}",
        "balance_penalty": f"{balance_penalty:.6f}",
        "weight_balance_penalty": f"{weight_penalty:.6f}",
        "scenario_objective": f"{objective:.6f}",
    }

    unit_rows = [
        {
            "design": design,
            "scenario": scenario_name,
            "case": case,
            "architecture_unit": unit,
            "scenario_proxy_cost": f"{cost:.6f}",
        }
        for unit, cost in unit_cost.most_common()
    ]
    return summary, unit_rows


def add_reductions(rows: list[dict[str, object]]) -> None:
    generic_by_key = {}
    for row in rows:
        if row["case"] == "generic":
            generic_by_key[(row["design"], row["scenario"])] = row
    for row in rows:
        generic = generic_by_key.get((row["design"], row["scenario"]))
        if not generic:
            row["reduction_vs_generic_scenario_objective"] = ""
            continue
        base = float(generic["scenario_objective"])
        cur = float(row["scenario_objective"])
        row["reduction_vs_generic_scenario_objective"] = f"{(base - cur) / base if base else 0.0:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--scenarios", type=Path, default=Path("configs/3d_integration_scenarios.yaml"))
    parser.add_argument("--assignment", action="append", required=True, help="CASE=assignment.csv")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    scenarios = parse_scenarios(args.scenarios)
    instances, net_to_instances = load_design(args.features_dir)

    summary_rows = []
    unit_rows = []
    for scenario_name, scenario in scenarios.items():
        for spec in args.assignment:
            case, assignment_path = parse_assignment_spec(spec)
            summary, units = evaluate(
                args.design,
                scenario_name,
                scenario,
                case,
                assignment_path,
                instances,
                net_to_instances,
            )
            summary_rows.append(summary)
            unit_rows.extend(units)

    add_reductions(summary_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.output_dir / f"{args.design}_scenario_cost_summary.csv"
    unit_path = args.output_dir / f"{args.design}_scenario_unit_costs.csv"
    manifest_path = args.output_dir / f"{args.design}_scenario_cost_manifest.json"

    summary_fields = [
        "design",
        "scenario",
        "case",
        "assignment_file",
        "tier0_instances",
        "tier1_instances",
        "instance_balance_ratio",
        "tier0_weight",
        "tier1_weight",
        "weight_balance_ratio",
        "crossing_nets",
        "crossing_connections_proxy",
        "base_crossing_cost",
        "high_fanout_cost",
        "boundary_cost",
        "architecture_cost",
        "semantic_uncertainty_cost",
        "scenario_proxy_cost",
        "balance_penalty",
        "weight_balance_penalty",
        "scenario_objective",
        "reduction_vs_generic_scenario_objective",
    ]
    unit_fields = ["design", "scenario", "case", "architecture_unit", "scenario_proxy_cost"]
    write_csv(summary_path, summary_rows, summary_fields)
    write_csv(unit_path, unit_rows, unit_fields)

    manifest = {
        "design": args.design,
        "features_dir": str(args.features_dir),
        "scenarios": str(args.scenarios),
        "assignments": args.assignment,
        "outputs": [str(summary_path), str(unit_path), str(manifest_path)],
        "note": "Scenario cost is an early-stage architecture-aware proxy, not physical signoff.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(summary_path)
    print(unit_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
