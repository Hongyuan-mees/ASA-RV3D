#!/usr/bin/env python3
"""Summarize SCR1 reviewer-response restored-baseline Phase-3 results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

DESIGN = "scr1_core_tuned"
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
NATIVE = "native_timing_aware"
ON = "reviewer_restored_architecture_on"
OFF = "reviewer_restored_architecture_off"


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def by_case(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("case", ""): row for row in rows if row.get("case")}


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def f(row: dict[str, object] | dict[str, str], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value in ("", None):
        return default
    return float(value)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct_reduction(before: float, after: float) -> float:
    return (before - after) / before if before else 0.0


def summary_path(root: Path, scenario: str, mode: str) -> Path:
    if mode == "on":
        stem = f"{DESIGN}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_guarded_repair"
    else:
        stem = f"{DESIGN}_tritonpart_compatible_normalized_dynamic_reviewer_restored_baseline_architecture_off_guarded_repair"
    return root / "results" / stem / scenario / "tritonpart_compatible_dynamic_guarded_repair_summary.csv"


def load_phase3(root: Path, scenario: str, mode: str) -> dict[str, str]:
    path = summary_path(root, scenario, mode)
    rows = read_rows(path)
    if not rows:
        return {"status": "missing", "summary_file": str(path)}
    row = dict(rows[0])
    row["status"] = "present"
    row["summary_file"] = str(path)
    return row


def restoration_row(root: Path) -> dict[str, str]:
    rows = read_rows(root / "results" / "benchmark_summary" / "scr1_core_tuned_feasibility_restoration_summary.csv")
    for row in rows:
        if row.get("policy") == "guarded":
            return row
    return {}


def audit_row(root: Path) -> dict[str, str]:
    rows = read_rows(root / "results" / "benchmark_summary" / "native_baseline_feasibility_audit.csv")
    for row in rows:
        if row.get("design") == DESIGN:
            return row
    return {}


def load_case(root: Path, scenario: str) -> dict[str, object]:
    phase_on = load_phase3(root, scenario, "on")
    phase_off = load_phase3(root, scenario, "off")
    prefix = f"{DESIGN}_{scenario}_reviewer_restored_baseline"
    timing = by_case(read_rows(root / "results" / "benchmark_summary" / f"{prefix}_timing_crossing.csv"))
    path = by_case(read_rows(root / "results" / "benchmark_summary" / f"{prefix}_path_cuts.csv"))
    structural_rows = read_rows(root / "results" / "benchmark_summary" / f"{prefix}_structural_rollup.csv")
    structural = structural_rows[0] if structural_rows else {}

    missing: list[str] = []
    if phase_on.get("status") != "present":
        missing.append("phase3:on")
    if phase_off.get("status") != "present":
        missing.append("phase3:off")
    for case in (NATIVE, ON, OFF):
        if case not in timing:
            missing.append(f"timing:{case}")
        if case not in path:
            missing.append(f"path:{case}")
    if not structural:
        missing.append("structural_rollup")

    row: dict[str, object] = {
        "design": DESIGN,
        "scenario": scenario,
        "status": "missing_input" if missing else "reviewer_compared",
        "missing": ";".join(missing),
    }
    if missing:
        return row

    native_timing = timing[NATIVE]
    on_timing = timing[ON]
    off_timing = timing[OFF]
    native_path = path[NATIVE]
    on_path = path[ON]
    off_path = path[OFF]

    row.update(
        {
            "on_accepted_moves": phase_on.get("accepted_moves", ""),
            "off_accepted_moves": phase_off.get("accepted_moves", ""),
            "on_stopped_converged": phase_on.get("stopped_converged", ""),
            "off_stopped_converged": phase_off.get("stopped_converged", ""),
            "on_objective_reduction": phase_on.get("objective_reduction", ""),
            "off_objective_reduction": phase_off.get("objective_reduction", ""),
            "on_final_area_balance_pass": phase_on.get("final_area_balance_pass", ""),
            "off_final_area_balance_pass": phase_off.get("final_area_balance_pass", ""),
            "on_final_tier0_area_fraction": phase_on.get("final_tier0_area_fraction", ""),
            "off_final_tier0_area_fraction": phase_off.get("final_tier0_area_fraction", ""),
            "native_crossing_nets": native_timing["crossing_nets"],
            "on_crossing_nets": on_timing["crossing_nets"],
            "off_crossing_nets": off_timing["crossing_nets"],
            "on_crossing_reduction_vs_native": f"{pct_reduction(f(native_timing, 'crossing_nets'), f(on_timing, 'crossing_nets')):.6f}",
            "off_crossing_reduction_vs_native": f"{pct_reduction(f(native_timing, 'crossing_nets'), f(off_timing, 'crossing_nets')):.6f}",
            "on_minus_off_crossing_nets": f"{f(on_timing, 'crossing_nets') - f(off_timing, 'crossing_nets'):.0f}",
            "native_timing_weighted_crossing": native_timing["timing_weighted_crossing"],
            "on_timing_weighted_crossing": on_timing["timing_weighted_crossing"],
            "off_timing_weighted_crossing": off_timing["timing_weighted_crossing"],
            "on_timing_weighted_reduction_vs_native": f"{pct_reduction(f(native_timing, 'timing_weighted_crossing'), f(on_timing, 'timing_weighted_crossing')):.6f}",
            "off_timing_weighted_reduction_vs_native": f"{pct_reduction(f(native_timing, 'timing_weighted_crossing'), f(off_timing, 'timing_weighted_crossing')):.6f}",
            "on_minus_off_timing_weighted_crossing": f"{f(on_timing, 'timing_weighted_crossing') - f(off_timing, 'timing_weighted_crossing'):.6f}",
            "native_timing_crossing_nets": native_timing["timing_crossing_nets"],
            "on_timing_crossing_nets": on_timing["timing_crossing_nets"],
            "off_timing_crossing_nets": off_timing["timing_crossing_nets"],
            "on_minus_off_timing_crossing_nets": f"{f(on_timing, 'timing_crossing_nets') - f(off_timing, 'timing_crossing_nets'):.0f}",
            "native_P_avg_cut": native_path["P_avg_cut"],
            "on_P_avg_cut": on_path["P_avg_cut"],
            "off_P_avg_cut": off_path["P_avg_cut"],
            "on_P_avg_cut_regret": f"{(f(on_path, 'P_avg_cut') - f(native_path, 'P_avg_cut')) / f(native_path, 'P_avg_cut') if f(native_path, 'P_avg_cut') else 0.0:.6f}",
            "off_P_avg_cut_regret": f"{(f(off_path, 'P_avg_cut') - f(native_path, 'P_avg_cut')) / f(native_path, 'P_avg_cut') if f(native_path, 'P_avg_cut') else 0.0:.6f}",
            "native_P_wst_cut": native_path["P_wst_cut"],
            "on_P_wst_cut": on_path["P_wst_cut"],
            "off_P_wst_cut": off_path["P_wst_cut"],
            "on_P_wst_cut_delta": f"{f(on_path, 'P_wst_cut') - f(native_path, 'P_wst_cut'):.6f}",
            "off_P_wst_cut_delta": f"{f(off_path, 'P_wst_cut') - f(native_path, 'P_wst_cut'):.6f}",
            "max_on_P_avg_cut_regret": f"{(f(on_path, 'P_avg_cut') - f(native_path, 'P_avg_cut')) / f(native_path, 'P_avg_cut') if f(native_path, 'P_avg_cut') else 0.0:.6f}",
            "max_on_P_wst_cut_delta": f"{f(on_path, 'P_wst_cut') - f(native_path, 'P_wst_cut'):.6f}",
            "native_structural_sensitive_crossing_nets": structural["native_scenario_sensitive_crossing_nets"],
            "on_structural_sensitive_crossing_nets": structural["architecture_on_scenario_sensitive_crossing_nets"],
            "off_structural_sensitive_crossing_nets": structural["architecture_off_scenario_sensitive_crossing_nets"],
            "on_structural_reduction_vs_native": structural["architecture_on_reduction_vs_native"],
            "on_structural_reduction_vs_off": structural["architecture_on_reduction_vs_off"],
            "architecture_on_better_structural_than_off": structural["architecture_on_better_than_off"],
            "on_assignment_file": phase_on.get("assignment_file", ""),
            "off_assignment_file": phase_off.get("assignment_file", ""),
        }
    )
    return row


def count(rows: list[dict[str, object]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--summary", type=Path, default=Path("results/benchmark_summary/reviewer_scr1_restored_phase3_summary.csv"))
    parser.add_argument("--rollup", type=Path, default=Path("results/benchmark_summary/reviewer_scr1_restored_phase3_rollup.csv"))
    args = parser.parse_args()

    scenarios = args.scenarios or SCENARIOS
    rows = [load_case(args.root, scenario) for scenario in scenarios]
    write_csv(args.root / args.summary, rows)

    compared = [row for row in rows if row.get("status") == "reviewer_compared"]
    restore = restoration_row(args.root)
    audit = audit_row(args.root)
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "reviewer_compared_cases", "value": len(compared)},
        {"metric": "design", "value": DESIGN},
        {"metric": "scenarios", "value": ",".join(scenarios)},
        {"metric": "native_baseline_area_status", "value": audit.get("root_cause_status", "")},
        {"metric": "native_tier0_area_fraction", "value": audit.get("tier0_area_fraction", "")},
        {"metric": "restoration_status", "value": restore.get("status", "")},
        {"metric": "restored_tier0_area_fraction", "value": restore.get("final_tier0_area_fraction", "")},
        {"metric": "restoration_moves", "value": restore.get("moved_instances", "")},
        {"metric": "restoration_cut_regret", "value": restore.get("cut_regret", "")},
        {"metric": "restoration_guard_status", "value": restore.get("guard_status", "")},
        {"metric": "architecture_on_better_structural_than_off_cases", "value": count(compared, "architecture_on_better_structural_than_off", "true")},
        {"metric": "architecture_off_better_or_equal_structural_cases", "value": len(compared) - count(compared, "architecture_on_better_structural_than_off", "true")},
        {"metric": "mean_on_crossing_reduction_vs_native", "value": f"{mean([f(row, 'on_crossing_reduction_vs_native') for row in compared]):.6f}"},
        {"metric": "mean_off_crossing_reduction_vs_native", "value": f"{mean([f(row, 'off_crossing_reduction_vs_native') for row in compared]):.6f}"},
        {"metric": "mean_on_timing_weighted_reduction_vs_native", "value": f"{mean([f(row, 'on_timing_weighted_reduction_vs_native') for row in compared]):.6f}"},
        {"metric": "mean_off_timing_weighted_reduction_vs_native", "value": f"{mean([f(row, 'off_timing_weighted_reduction_vs_native') for row in compared]):.6f}"},
        {"metric": "mean_on_structural_reduction_vs_native", "value": f"{mean([f(row, 'on_structural_reduction_vs_native') for row in compared]):.6f}"},
        {"metric": "mean_on_structural_reduction_vs_off", "value": f"{mean([f(row, 'on_structural_reduction_vs_off') for row in compared]):.6f}"},
        {"metric": "max_on_P_avg_cut_regret", "value": f"{max([f(row, 'on_P_avg_cut_regret') for row in compared], default=0.0):.6f}"},
        {"metric": "max_on_P_wst_cut_delta", "value": f"{max([f(row, 'on_P_wst_cut_delta') for row in compared], default=0.0):.6f}"},
    ]
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
