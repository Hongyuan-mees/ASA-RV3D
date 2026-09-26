#!/usr/bin/env python3
"""Summarize normalized dynamic convergence Phase-3 ON/OFF runs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_DESIGNS = ["picorv32", "riscv32i"]
DEFAULT_SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = []
        for row in rows:
            for key in row:
                if key not in fieldnames:
                    fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def f(row: dict[str, object], key: str, default: float = 0.0) -> float:
    value = row.get(key, "")
    if value == "":
        return default
    return float(value)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summary_path(root: Path, design: str, scenario: str, mode: str) -> Path:
    if mode == "architecture_on":
        stem = f"{design}_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair"
    else:
        stem = f"{design}_tritonpart_compatible_normalized_dynamic_convergence_architecture_off_guarded_repair"
    return root / "results" / stem / scenario / "tritonpart_compatible_dynamic_guarded_repair_summary.csv"


def load_summary(root: Path, design: str, scenario: str, mode: str) -> dict[str, str]:
    path = summary_path(root, design, scenario, mode)
    rows = read_rows(path)
    if not rows:
        return {"status": "missing", "summary_file": str(path)}
    row = dict(rows[0])
    row["status"] = "present"
    row["summary_file"] = str(path)
    return row


def summarize_mode(row: dict[str, str], prefix: str) -> dict[str, object]:
    return {
        f"{prefix}_status": row.get("status", ""),
        f"{prefix}_accepted_moves": row.get("accepted_moves", ""),
        f"{prefix}_stopped_no_legal_move": row.get("stopped_no_legal_move", ""),
        f"{prefix}_stopped_converged": row.get("stopped_converged", ""),
        f"{prefix}_final_recent_gain_fraction": row.get("final_recent_gain_fraction", ""),
        f"{prefix}_objective_reduction": row.get("objective_reduction", ""),
        f"{prefix}_final_crossing_nets": row.get("final_crossing_nets", ""),
        f"{prefix}_cut_regret": row.get("cut_regret", ""),
        f"{prefix}_crossing_connection_regret": row.get("crossing_connection_regret", ""),
        f"{prefix}_final_area_balance_pass": row.get("final_area_balance_pass", ""),
        f"{prefix}_final_tier0_area_fraction": row.get("final_tier0_area_fraction", ""),
        f"{prefix}_final_P_avg_cut": row.get("final_P_avg_cut", ""),
        f"{prefix}_P_avg_cut_regret": row.get("P_avg_cut_regret", ""),
        f"{prefix}_final_P_wst_cut": row.get("final_P_wst_cut", ""),
        f"{prefix}_P_wst_cut_delta": row.get("P_wst_cut_delta", ""),
        f"{prefix}_assignment_file": row.get("assignment_file", ""),
        f"{prefix}_summary_file": row.get("summary_file", ""),
    }


def summarize_case(root: Path, design: str, scenario: str) -> dict[str, object]:
    on = load_summary(root, design, scenario, "architecture_on")
    off = load_summary(root, design, scenario, "architecture_off")
    status = "compared" if on.get("status") == "present" and off.get("status") == "present" else "missing_input"
    row: dict[str, object] = {
        "design": design,
        "scenario": scenario,
        "status": status,
    }
    row.update(summarize_mode(on, "on"))
    row.update(summarize_mode(off, "off"))

    if status == "compared":
        row.update(
            {
                "objective_note": "objective_reductions_not_directly_comparable_across_on_off",
                "on_minus_off_crossing_nets": f"{f(on, 'final_crossing_nets') - f(off, 'final_crossing_nets'):.0f}",
                "on_minus_off_cut_regret": f"{f(on, 'cut_regret') - f(off, 'cut_regret'):.6f}",
                "on_minus_off_P_avg_cut": f"{f(on, 'final_P_avg_cut') - f(off, 'final_P_avg_cut'):.6f}",
                "on_minus_off_P_wst_cut": f"{f(on, 'final_P_wst_cut') - f(off, 'final_P_wst_cut'):.6f}",
            }
        )
    return row


def count(rows: list[dict[str, object]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_convergence_phase3_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_convergence_phase3_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    rows = [summarize_case(args.root, design, scenario) for design in designs for scenario in scenarios]
    write_csv(args.root / args.summary, rows)

    compared = [row for row in rows if row.get("status") == "compared"]
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "compared_cases", "value": len(compared)},
        {"metric": "designs", "value": ",".join(designs)},
        {"metric": "scenarios", "value": ",".join(scenarios)},
        {"metric": "on_converged_cases", "value": count(compared, "on_stopped_converged", "true")},
        {"metric": "off_converged_cases", "value": count(compared, "off_stopped_converged", "true")},
        {
            "metric": "mean_on_objective_reduction",
            "value": f"{mean([f(row, 'on_objective_reduction') for row in compared]):.6f}",
        },
        {
            "metric": "mean_off_objective_reduction",
            "value": f"{mean([f(row, 'off_objective_reduction') for row in compared]):.6f}",
        },
        {
            "metric": "mean_on_cut_regret",
            "value": f"{mean([f(row, 'on_cut_regret') for row in compared]):.6f}",
        },
        {
            "metric": "mean_off_cut_regret",
            "value": f"{mean([f(row, 'off_cut_regret') for row in compared]):.6f}",
        },
        {
            "metric": "mean_on_minus_off_crossing_nets",
            "value": f"{mean([f(row, 'on_minus_off_crossing_nets') for row in compared]):.6f}",
        },
        {
            "metric": "max_on_P_avg_cut_regret",
            "value": f"{max([f(row, 'on_P_avg_cut_regret') for row in compared], default=0.0):.6f}",
        },
        {
            "metric": "max_off_P_avg_cut_regret",
            "value": f"{max([f(row, 'off_P_avg_cut_regret') for row in compared], default=0.0):.6f}",
        },
        {
            "metric": "max_on_P_wst_cut_delta",
            "value": f"{max([f(row, 'on_P_wst_cut_delta') for row in compared], default=0.0):.6f}",
        },
        {
            "metric": "max_off_P_wst_cut_delta",
            "value": f"{max([f(row, 'off_P_wst_cut_delta') for row in compared], default=0.0):.6f}",
        },
    ]
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
