#!/usr/bin/env python3
"""Replay ASA-on-native moves under explicit cut-regret budgets.

This script does not rerun partitioning and does not tune ASA.  It replays the
existing local-refinement trace from a native timing-aware TritonPart starting
assignment, stops at the largest prefix that satisfies each cutsize budget, and
writes budgeted assignments for follow-up evaluation.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fieldnames:
        fieldnames = list(rows[0].keys()) if rows else []
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


def parse_nets_field(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    value = value.strip("[]")
    for sep in [";", "|"]:
        if sep in value:
            return [x.strip().strip("'\"") for x in value.split(sep) if x.strip().strip("'\"")]
    if "," in value:
        return [x.strip().strip("'\"") for x in value.split(",") if x.strip().strip("'\"")]
    return [value.strip("'\"")]


def load_assignment(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = read_csv(path)
    tier = {normalize_name(row["instance"]): row["tier"] for row in rows}
    return rows, tier


def load_net_to_instances(features_dir: Path, assignment_instances: set[str]) -> dict[str, list[str]]:
    rows = read_csv(features_dir / "instance_features.csv")
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = normalize_name(row["instance"])
        if inst not in assignment_instances:
            continue
        for net in parse_nets_field(row.get("nets", "")):
            net_to_instances[net].append(inst)
    return {net: insts for net, insts in net_to_instances.items() if len(insts) > 1}


def crossing_stats(tier: dict[str, str], net_to_instances: dict[str, list[str]]) -> tuple[int, int]:
    crossing_nets = 0
    crossing_connections = 0
    for insts in net_to_instances.values():
        c0 = sum(1 for inst in insts if tier.get(inst) == "tier0")
        c1 = sum(1 for inst in insts if tier.get(inst) == "tier1")
        if c0 and c1:
            crossing_nets += 1
            crossing_connections += min(c0, c1)
    return crossing_nets, crossing_connections


def format_assignment_rows(rows: list[dict[str, str]], tier: dict[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        new_row = dict(row)
        new_row["tier"] = tier[normalize_name(row["instance"])]
        out.append(new_row)
    return out


def budget_label(budget: float) -> str:
    return f"{budget:.2f}".replace(".", "p")


def as_float(value: str) -> float:
    return float(value) if value not in ("", None) else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", default="riscv32i")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument(
        "--initial-assignment",
        type=Path,
        default=Path("results/riscv32i_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"),
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("results/riscv32i_timing_aware_start_asa/state_and_clock_protected/local_refinement_trace.csv"),
    )
    parser.add_argument("--features-dir", type=Path, default=Path("results/riscv32i_features"))
    parser.add_argument("--budget", type=float, action="append", default=[0.05, 0.10, 0.20])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/riscv32i_asa_on_native_cut_regret_replay/state_and_clock_protected"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_summary.csv"),
    )
    args = parser.parse_args()

    assignment_rows, tier0 = load_assignment(args.initial_assignment)
    trace = read_csv(args.trace)
    net_to_instances = load_net_to_instances(args.features_dir, set(tier0))

    baseline_crossing, baseline_conn = crossing_stats(tier0, net_to_instances)
    snapshots: list[dict[str, object]] = []
    tier = dict(tier0)
    cumulative_gain = 0.0
    cumulative_scenario_gain = 0.0
    cumulative_physical_gain = 0.0
    cumulative_timing_gain = 0.0

    def add_snapshot(move_index: int) -> None:
        crossing, conn = crossing_stats(tier, net_to_instances)
        snapshots.append(
            {
                "move_index": move_index,
                "tier": dict(tier),
                "crossing_nets": crossing,
                "crossing_connections_proxy": conn,
                "cut_regret": (crossing - baseline_crossing) / baseline_crossing if baseline_crossing else 0.0,
                "crossing_connection_regret": (conn - baseline_conn) / baseline_conn if baseline_conn else 0.0,
                "cumulative_gain": cumulative_gain,
                "cumulative_scenario_gain": cumulative_scenario_gain,
                "cumulative_physical_gain": cumulative_physical_gain,
                "cumulative_timing_gain": cumulative_timing_gain,
            }
        )

    add_snapshot(0)
    for row in trace:
        inst = normalize_name(row["instance"])
        if inst not in tier:
            continue
        expected_from = row.get("from_tier", "")
        to_tier = row.get("to_tier", "")
        if expected_from and tier[inst] != expected_from:
            raise RuntimeError(f"Trace mismatch at {inst}: expected {expected_from}, saw {tier[inst]}")
        if to_tier not in {"tier0", "tier1"}:
            raise RuntimeError(f"Unexpected to_tier for {inst}: {to_tier}")
        tier[inst] = to_tier
        cumulative_gain += as_float(row.get("gain", "0"))
        cumulative_scenario_gain += as_float(row.get("scenario_gain", "0"))
        cumulative_physical_gain += as_float(row.get("physical_gain", "0"))
        cumulative_timing_gain += as_float(row.get("timing_gain", "0"))
        add_snapshot(int(row.get("move_index", len(snapshots))))

    summary_rows: list[dict[str, object]] = []
    assignment_fieldnames = list(assignment_rows[0].keys())
    for budget in args.budget:
        allowed = [snap for snap in snapshots if float(snap["cut_regret"]) <= budget + 1e-12]
        if not allowed:
            selected = snapshots[0]
        else:
            selected = allowed[-1]
        label = budget_label(budget)
        assignment_out = args.output_dir / f"cut_regret_{label}_assignment.csv"
        write_csv(
            assignment_out,
            format_assignment_rows(assignment_rows, selected["tier"]),  # type: ignore[arg-type]
            assignment_fieldnames,
        )
        summary_rows.append(
            {
                "design": args.design,
                "scenario": args.scenario,
                "cut_regret_budget": f"{budget:.6f}",
                "selected_move_index": selected["move_index"],
                "baseline_crossing_nets": baseline_crossing,
                "selected_crossing_nets": selected["crossing_nets"],
                "selected_cut_regret": f"{float(selected['cut_regret']):.6f}",
                "baseline_crossing_connections_proxy": baseline_conn,
                "selected_crossing_connections_proxy": selected["crossing_connections_proxy"],
                "selected_crossing_connection_regret": f"{float(selected['crossing_connection_regret']):.6f}",
                "cumulative_gain": f"{float(selected['cumulative_gain']):.6f}",
                "cumulative_scenario_gain": f"{float(selected['cumulative_scenario_gain']):.6f}",
                "cumulative_physical_gain": f"{float(selected['cumulative_physical_gain']):.6f}",
                "cumulative_timing_gain": f"{float(selected['cumulative_timing_gain']):.6f}",
                "assignment_file": str(assignment_out),
            }
        )

    write_csv(args.output_summary, summary_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
