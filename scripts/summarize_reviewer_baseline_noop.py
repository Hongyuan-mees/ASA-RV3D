#!/usr/bin/env python3
"""Summarize no-op checks for feasible native baselines."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

DESIGNS = ("picorv32", "riscv32i")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def load_tiers(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    return {row.get("instance", ""): row.get("tier", "") for row in rows if row.get("instance")}


def first_row(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    return rows[0] if rows else {}


def summarize_design(root: Path, design: str) -> dict[str, object]:
    summary_path = root / "results" / "benchmark_summary" / f"{design}_baseline_restoration_noop_summary.csv"
    moves_path = root / "results" / "benchmark_summary" / f"{design}_baseline_restoration_noop_moves.csv"
    summary = first_row(summary_path)
    if not summary:
        return {
            "design": design,
            "status": "missing_summary",
            "summary_file": str(summary_path),
        }

    initial = root / summary.get("initial_assignment_file", "")
    restored = root / summary.get("restored_assignment_file", "")
    initial_tiers = load_tiers(initial) if initial.exists() else {}
    restored_tiers = load_tiers(restored) if restored.exists() else {}
    tier_maps_identical = bool(initial_tiers) and initial_tiers == restored_tiers
    moves = read_rows(moves_path)
    noop_pass = (
        summary.get("status") == "already_feasible"
        and summary.get("reconstructed_area_pass") == "true"
        and summary.get("moved_instances") in {"0", "0.000000"}
        and not moves
        and tier_maps_identical
    )
    return {
        "design": design,
        "status": summary.get("status", ""),
        "noop_pass": str(noop_pass).lower(),
        "tier_maps_identical": str(tier_maps_identical).lower(),
        "move_rows": len(moves),
        "moved_instances": summary.get("moved_instances", ""),
        "baseline_tier0_area_fraction": summary.get("baseline_tier0_area_fraction", ""),
        "final_tier0_area_fraction": summary.get("final_tier0_area_fraction", ""),
        "baseline_crossing_nets": summary.get("baseline_crossing_nets", ""),
        "final_crossing_nets": summary.get("final_crossing_nets", ""),
        "cut_regret": summary.get("cut_regret", ""),
        "baseline_P_avg_cut": summary.get("baseline_P_avg_cut", ""),
        "final_P_avg_cut": summary.get("final_P_avg_cut", ""),
        "P_avg_cut_regret": summary.get("P_avg_cut_regret", ""),
        "baseline_P_wst_cut": summary.get("baseline_P_wst_cut", ""),
        "final_P_wst_cut": summary.get("final_P_wst_cut", ""),
        "P_wst_cut_delta": summary.get("P_wst_cut_delta", ""),
        "initial_assignment_file": summary.get("initial_assignment_file", ""),
        "restored_assignment_file": summary.get("restored_assignment_file", ""),
        "summary_file": str(summary_path),
        "moves_file": str(moves_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/benchmark_summary/baseline_restoration_noop_check.csv"),
    )
    args = parser.parse_args()
    rows = [summarize_design(args.root, design) for design in DESIGNS]
    write_csv(args.root / args.output, rows)
    for row in rows:
        print(f"{row['design']}: noop_pass={row.get('noop_pass')} status={row.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
