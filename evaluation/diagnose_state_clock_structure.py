#!/usr/bin/env python3
"""Diagnose whether state/clock units are structurally strong enough.

This is a diagnostic experiment, not a tuning step.  It does not change scenario
weights or partition assignments.  It asks:

  Are clock/reset and state-related units large and connected enough to dominate
  a state/clock-protected objective?

Outputs:

  results/benchmark_summary/state_clock_diagnosis_summary.csv
  results/benchmark_summary/state_clock_diagnosis_units.csv
  results/benchmark_summary/state_clock_diagnosis_crossing.csv
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


DESIGNS = ["ibex", "riscv32i"]
STATE_CLOCK_UNITS = {"clock_reset", "pipeline_state", "register_file", "csr", "trap_debug"}
FEATURE_DIR = {
    "ibex": Path("results/ibex_features"),
    "riscv32i": Path("results/riscv32i_features"),
}
OUT_DIR = Path("results/benchmark_summary")


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


def load_features(design: str) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    features_dir = FEATURE_DIR[design]
    feature_rows = read_csv(features_dir / "instance_features.csv")
    mapping_rows = read_csv(features_dir / "architecture_mapping_instances.csv")
    mapping = {row["instance"]: row for row in mapping_rows}

    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in feature_rows:
        inst = row["instance"]
        mapped = mapping.get(inst, {})
        enriched = dict(row)
        enriched["architecture_unit"] = mapped.get("architecture_unit", "unclassified")
        enriched["semantic_group"] = mapped.get("semantic_group", "infrastructure")
        enriched["mapping_confidence"] = mapped.get("mapping_confidence", "0.5")
        instances[inst] = enriched
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return instances, net_to_instances


def load_assignment(design: str) -> dict[str, str]:
    path = (
        Path("results")
        / f"{design}_scenario_partition"
        / "state_and_clock_protected"
        / "scenario_aware_assignment.csv"
    )
    return {row["instance"]: row["tier"] for row in read_csv(path)}


def safe_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def summarize_design(design: str) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    instances, net_to_instances = load_features(design)
    assignment = load_assignment(design)
    total_instances = len(instances)
    total_net_pins = sum(len(v) for v in net_to_instances.values())

    unit_instances: Counter[str] = Counter()
    unit_net_incidence: Counter[str] = Counter()
    unit_neighbor_sum: Counter[str] = Counter()
    unit_confidence_sum: defaultdict[str, float] = defaultdict(float)
    unit_tier0: Counter[str] = Counter()
    unit_tier1: Counter[str] = Counter()

    for inst, row in instances.items():
        unit = row["architecture_unit"]
        unit_instances[unit] += 1
        unit_net_incidence[unit] += max(0, int(row.get("net_count", "0") or 0))
        unit_neighbor_sum[unit] += max(0, int(row.get("unique_neighbor_count", "0") or 0))
        unit_confidence_sum[unit] += safe_float(row.get("mapping_confidence", "0.5"), 0.5)
        tier = assignment.get(inst)
        if tier == "tier0":
            unit_tier0[unit] += 1
        elif tier == "tier1":
            unit_tier1[unit] += 1

    crossing_by_unit: Counter[str] = Counter()
    crossing_pins_by_unit: Counter[str] = Counter()
    crossing_state_clock_nets = 0
    total_crossing_nets = 0
    state_clock_crossing_connections = 0
    total_crossing_connections = 0

    for net, connected_all in net_to_instances.items():
        connected = [inst for inst in connected_all if inst in instances and inst in assignment]
        if not connected:
            continue
        tiers = Counter(assignment[inst] for inst in connected)
        if len(tiers) <= 1:
            continue
        total_crossing_nets += 1
        crossing = min(tiers.values())
        total_crossing_connections += crossing
        units = {instances[inst]["architecture_unit"] for inst in connected}
        if units & STATE_CLOCK_UNITS:
            crossing_state_clock_nets += 1
            state_clock_crossing_connections += crossing
        for unit in units:
            crossing_by_unit[unit] += 1
        for inst in connected:
            crossing_pins_by_unit[instances[inst]["architecture_unit"]] += 1

    unit_rows: list[dict[str, object]] = []
    for unit, count in unit_instances.most_common():
        is_state_clock = unit in STATE_CLOCK_UNITS
        tier0 = unit_tier0[unit]
        tier1 = unit_tier1[unit]
        high = max(tier0, tier1)
        low = min(tier0, tier1)
        unit_rows.append(
            {
                "design": design,
                "architecture_unit": unit,
                "is_state_clock_unit": int(is_state_clock),
                "instance_count": count,
                "instance_fraction": f"{count / total_instances:.6f}",
                "net_incidence": unit_net_incidence[unit],
                "net_incidence_fraction": f"{unit_net_incidence[unit] / total_net_pins if total_net_pins else 0.0:.6f}",
                "mean_unique_neighbor_count": f"{unit_neighbor_sum[unit] / count if count else 0.0:.3f}",
                "mean_mapping_confidence": f"{unit_confidence_sum[unit] / count if count else 0.0:.6f}",
                "tier0_instances": tier0,
                "tier1_instances": tier1,
                "tier_balance_ratio": f"{low / high if high else 1.0:.6f}",
                "crossing_nets_touching_unit": crossing_by_unit[unit],
                "crossing_pins_for_unit": crossing_pins_by_unit[unit],
            }
        )

    state_clock_instance_count = sum(unit_instances[u] for u in STATE_CLOCK_UNITS)
    state_clock_net_incidence = sum(unit_net_incidence[u] for u in STATE_CLOCK_UNITS)
    summary_rows = [
        {
            "design": design,
            "total_instances": total_instances,
            "state_clock_instance_count": state_clock_instance_count,
            "state_clock_instance_fraction": f"{state_clock_instance_count / total_instances:.6f}",
            "total_net_pin_incidence": total_net_pins,
            "state_clock_net_pin_incidence": state_clock_net_incidence,
            "state_clock_net_pin_fraction": f"{state_clock_net_incidence / total_net_pins if total_net_pins else 0.0:.6f}",
            "total_crossing_nets": total_crossing_nets,
            "state_clock_crossing_nets": crossing_state_clock_nets,
            "state_clock_crossing_net_fraction": f"{crossing_state_clock_nets / total_crossing_nets if total_crossing_nets else 0.0:.6f}",
            "total_crossing_connections_proxy": total_crossing_connections,
            "state_clock_crossing_connections_proxy": state_clock_crossing_connections,
            "state_clock_crossing_connection_fraction": f"{state_clock_crossing_connections / total_crossing_connections if total_crossing_connections else 0.0:.6f}",
        }
    ]

    crossing_rows = [
        {
            "design": design,
            "architecture_unit": row["architecture_unit"],
            "is_state_clock_unit": row["is_state_clock_unit"],
            "crossing_nets_touching_unit": row["crossing_nets_touching_unit"],
            "crossing_pins_for_unit": row["crossing_pins_for_unit"],
            "instance_fraction": row["instance_fraction"],
            "net_incidence_fraction": row["net_incidence_fraction"],
        }
        for row in sorted(
            unit_rows,
            key=lambda r: (-int(r["crossing_nets_touching_unit"]), -int(r["crossing_pins_for_unit"]), str(r["architecture_unit"])),
        )
    ]
    return summary_rows, unit_rows, crossing_rows


def main() -> int:
    summary_rows: list[dict[str, object]] = []
    unit_rows: list[dict[str, object]] = []
    crossing_rows: list[dict[str, object]] = []
    for design in DESIGNS:
        s, u, c = summarize_design(design)
        summary_rows.extend(s)
        unit_rows.extend(u)
        crossing_rows.extend(c)

    write_csv(
        OUT_DIR / "state_clock_diagnosis_summary.csv",
        summary_rows,
        [
            "design",
            "total_instances",
            "state_clock_instance_count",
            "state_clock_instance_fraction",
            "total_net_pin_incidence",
            "state_clock_net_pin_incidence",
            "state_clock_net_pin_fraction",
            "total_crossing_nets",
            "state_clock_crossing_nets",
            "state_clock_crossing_net_fraction",
            "total_crossing_connections_proxy",
            "state_clock_crossing_connections_proxy",
            "state_clock_crossing_connection_fraction",
        ],
    )
    write_csv(
        OUT_DIR / "state_clock_diagnosis_units.csv",
        unit_rows,
        [
            "design",
            "architecture_unit",
            "is_state_clock_unit",
            "instance_count",
            "instance_fraction",
            "net_incidence",
            "net_incidence_fraction",
            "mean_unique_neighbor_count",
            "mean_mapping_confidence",
            "tier0_instances",
            "tier1_instances",
            "tier_balance_ratio",
            "crossing_nets_touching_unit",
            "crossing_pins_for_unit",
        ],
    )
    write_csv(
        OUT_DIR / "state_clock_diagnosis_crossing.csv",
        crossing_rows,
        [
            "design",
            "architecture_unit",
            "is_state_clock_unit",
            "crossing_nets_touching_unit",
            "crossing_pins_for_unit",
            "instance_fraction",
            "net_incidence_fraction",
        ],
    )
    print(OUT_DIR / "state_clock_diagnosis_summary.csv")
    print(OUT_DIR / "state_clock_diagnosis_units.csv")
    print(OUT_DIR / "state_clock_diagnosis_crossing.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
