#!/usr/bin/env python3
"""Summarize Phase-3 architecture ON/OFF ablation under identical guards.

This compares dynamic constrained ASA checkpoints selected with the same
area/cut/path/timing-weighted guards, once with recovered architecture semantics
enabled and once with architecture semantics disabled.

Objective reductions are reported for completeness but are not directly
comparable across ON/OFF because the objective definition changes when
architecture semantics are disabled.  The comparable columns are cut,
timing-weighted crossing, timing-crossing net counts, high-timing crossing
counts, and path-cut metrics.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_DESIGNS = ["picorv32", "riscv32i"]
DEFAULT_SCENARIO = "state_and_clock_protected"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def selected_row(root: Path, design: str, scenario: str, mode: str) -> dict[str, str]:
    if mode == "on":
        path = (
            root
            / "results"
            / f"{design}_tritonpart_compatible_dynamic_canonical_checkpoint"
            / scenario
            / "dynamic_canonical_selected_checkpoint.csv"
        )
    else:
        path = (
            root
            / "results"
            / f"{design}_tritonpart_compatible_dynamic_architecture_off_canonical_checkpoint"
            / scenario
            / "dynamic_canonical_selected_checkpoint.csv"
        )
    rows = read_rows(path)
    return rows[0] if rows else {"status": "missing", "missing": str(path)}


def summarize_case(root: Path, design: str, scenario: str) -> dict[str, object]:
    on = selected_row(root, design, scenario, "on")
    off = selected_row(root, design, scenario, "off")
    if on.get("status") != "selected" or off.get("status") != "selected":
        return {
            "design": design,
            "scenario": scenario,
            "status": "missing_input",
            "on_status": on.get("status", ""),
            "off_status": off.get("status", ""),
            "missing": ";".join(x for x in [on.get("missing", ""), off.get("missing", "")] if x),
        }

    on_tw = f(on, "candidate_timing_weighted_crossing")
    off_tw = f(off, "candidate_timing_weighted_crossing")
    on_cross = f(on, "crossing_nets")
    off_cross = f(off, "crossing_nets")
    on_timing_nets = f(on, "candidate_timing_crossing_nets")
    off_timing_nets = f(off, "candidate_timing_crossing_nets")
    on_high = f(on, "candidate_high_timing_crossing_nets")
    off_high = f(off, "candidate_high_timing_crossing_nets")
    on_pavg = f(on, "P_avg_cut")
    off_pavg = f(off, "P_avg_cut")
    on_pwst = f(on, "P_wst_cut")
    off_pwst = f(off, "P_wst_cut")

    return {
        "design": design,
        "scenario": scenario,
        "status": "compared",
        "on_prefix": on.get("prefix", ""),
        "off_prefix": off.get("prefix", ""),
        "on_objective_reduction": on.get("objective_reduction", ""),
        "off_objective_reduction": off.get("objective_reduction", ""),
        "objective_note": "not_directly_comparable",
        "on_crossing_nets": f"{on_cross:.0f}",
        "off_crossing_nets": f"{off_cross:.0f}",
        "crossing_delta_off_minus_on": f"{off_cross - on_cross:.0f}",
        "on_timing_weighted_crossing": f"{on_tw:.6f}",
        "off_timing_weighted_crossing": f"{off_tw:.6f}",
        "timing_weighted_delta_off_minus_on": f"{off_tw - on_tw:.6f}",
        "on_timing_weighted_regret": on.get("timing_weighted_regret", ""),
        "off_timing_weighted_regret": off.get("timing_weighted_regret", ""),
        "on_timing_crossing_nets": f"{on_timing_nets:.0f}",
        "off_timing_crossing_nets": f"{off_timing_nets:.0f}",
        "timing_crossing_net_delta_off_minus_on": f"{off_timing_nets - on_timing_nets:.0f}",
        "on_high_timing_crossing_nets": f"{on_high:.0f}",
        "off_high_timing_crossing_nets": f"{off_high:.0f}",
        "high_timing_crossing_delta_off_minus_on": f"{off_high - on_high:.0f}",
        "on_P_avg_cut": f"{on_pavg:.6f}",
        "off_P_avg_cut": f"{off_pavg:.6f}",
        "P_avg_cut_delta_off_minus_on": f"{off_pavg - on_pavg:.6f}",
        "on_P_wst_cut": f"{on_pwst:.6f}",
        "off_P_wst_cut": f"{off_pwst:.6f}",
        "P_wst_cut_delta_off_minus_on": f"{off_pwst - on_pwst:.6f}",
        "on_area_balance_pass": on.get("area_balance_pass", ""),
        "off_area_balance_pass": off.get("area_balance_pass", ""),
        "on_assignment_file": on.get("assignment_file", ""),
        "off_assignment_file": off.get("assignment_file", ""),
        "interpretation": interpret(on_tw, off_tw, on_cross, off_cross, on_timing_nets, off_timing_nets),
    }


def interpret(
    on_tw: float,
    off_tw: float,
    on_cross: float,
    off_cross: float,
    on_timing_nets: float,
    off_timing_nets: float,
) -> str:
    tw_eps = 1e-9
    if on_tw + tw_eps < off_tw and on_timing_nets <= off_timing_nets:
        return "architecture_on_better_timing_sensitive"
    if off_tw + tw_eps < on_tw and off_timing_nets <= on_timing_nets:
        return "architecture_off_better_timing_sensitive"
    if on_cross < off_cross and off_tw <= on_tw:
        return "mixed_on_better_cut_off_better_timing"
    if off_cross < on_cross and on_tw <= off_tw:
        return "mixed_off_better_cut_on_better_timing"
    return "mixed_tradeoff"


def count(rows: list[dict[str, object]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", default=DEFAULT_SCENARIO)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_architecture_ablation_phase3_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_architecture_ablation_phase3_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    rows = [summarize_case(args.root, design, args.scenario) for design in designs]
    write_csv(args.root / args.summary, rows)

    compared = [row for row in rows if row.get("status") == "compared"]
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "compared_cases", "value": len(compared)},
        {"metric": "designs", "value": ",".join(designs)},
        {
            "metric": "architecture_on_better_timing_sensitive_cases",
            "value": count(compared, "interpretation", "architecture_on_better_timing_sensitive"),
        },
        {
            "metric": "architecture_off_better_timing_sensitive_cases",
            "value": count(compared, "interpretation", "architecture_off_better_timing_sensitive"),
        },
        {
            "metric": "mixed_tradeoff_cases",
            "value": len(compared)
            - count(compared, "interpretation", "architecture_on_better_timing_sensitive")
            - count(compared, "interpretation", "architecture_off_better_timing_sensitive"),
        },
        {
            "metric": "mean_timing_weighted_delta_off_minus_on",
            "value": f"{mean([f(row, 'timing_weighted_delta_off_minus_on') for row in compared]):.6f}",
        },
        {
            "metric": "mean_crossing_delta_off_minus_on",
            "value": f"{mean([f(row, 'crossing_delta_off_minus_on') for row in compared]):.6f}",
        },
        {
            "metric": "mean_timing_crossing_net_delta_off_minus_on",
            "value": f"{mean([f(row, 'timing_crossing_net_delta_off_minus_on') for row in compared]):.6f}",
        },
        {
            "metric": "objective_note",
            "value": "objective_reductions_not_directly_comparable_across_on_off",
        },
    ]
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
