#!/usr/bin/env python3
"""Summarize Phase-3 dynamic constrained ASA checkpoint results.

This rollup is intentionally narrow: it summarizes paper-safe canonical
checkpoints selected from dynamic TritonPart-compatible ASA refinement.  A row
is counted as admissible only when it preserves area/cut/path guards and does
not increase canonical timing-weighted crossing relative to native timing-aware
TritonPart.
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


def by_case(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["case"]: row for row in rows if row.get("case")}


def summarize_case(root: Path, design: str, scenario: str) -> dict[str, object]:
    selected_path = (
        root
        / "results"
        / f"{design}_tritonpart_compatible_dynamic_canonical_checkpoint"
        / scenario
        / "dynamic_canonical_selected_checkpoint.csv"
    )
    timing_path = (
        root
        / "results"
        / "benchmark_summary"
        / f"{design}_{scenario}_dynamic_canonical_checkpoint_timing_crossing.csv"
    )
    path_cuts_path = (
        root
        / "results"
        / "benchmark_summary"
        / f"{design}_{scenario}_dynamic_canonical_checkpoint_path_cuts.csv"
    )
    selected_rows = read_rows(selected_path)
    timing_rows = read_rows(timing_path)
    path_rows = read_rows(path_cuts_path)
    if not selected_rows:
        return {
            "design": design,
            "scenario": scenario,
            "status": "missing_selected_checkpoint",
            "missing": str(selected_path),
        }
    selected = selected_rows[0]
    timing = by_case(timing_rows)
    paths = by_case(path_rows)
    native_timing = timing.get("native_timing_aware", {})
    cand_timing = (
        timing.get("dynamic_canonical_checkpoint")
        or timing.get("dynamic_checkpoint")
        or {}
    )
    native_path = paths.get("native_timing_aware", {})
    cand_path = (
        paths.get("dynamic_canonical_checkpoint")
        or paths.get("dynamic_checkpoint")
        or {}
    )

    native_crossing = f(native_timing, "crossing_nets")
    cand_crossing = f(cand_timing, "crossing_nets")
    crossing_reduction = (
        (native_crossing - cand_crossing) / native_crossing
        if native_crossing
        else 0.0
    )
    native_tw = f(native_timing, "timing_weighted_crossing")
    cand_tw = f(cand_timing, "timing_weighted_crossing")
    tw_reduction = (native_tw - cand_tw) / native_tw if native_tw else 0.0
    native_timing_nets = f(native_timing, "timing_crossing_nets")
    cand_timing_nets = f(cand_timing, "timing_crossing_nets")
    native_high = f(native_timing, "high_timing_crossing_nets")
    cand_high = f(cand_timing, "high_timing_crossing_nets")
    native_pavg = f(native_path, "P_avg_cut")
    cand_pavg = f(cand_path, "P_avg_cut")
    pavg_reduction = (native_pavg - cand_pavg) / native_pavg if native_pavg else 0.0
    native_pwst = f(native_path, "P_wst_cut")
    cand_pwst = f(cand_path, "P_wst_cut")

    admissible = (
        selected.get("status") == "selected"
        and selected.get("area_balance_pass") == "true"
        and f(selected, "cut_regret") <= 0.05
        and f(selected, "P_avg_cut_regret") <= 0.0
        and f(selected, "P_wst_cut_delta") <= 0.0
        and f(selected, "timing_weighted_regret") <= 0.0
    )

    return {
        "design": design,
        "scenario": scenario,
        "status": "admissible_phase3" if admissible else "not_admissible_phase3",
        "selected_prefix": selected.get("prefix", ""),
        "objective_reduction": selected.get("objective_reduction", ""),
        "area_balance_pass": selected.get("area_balance_pass", ""),
        "area_weight_balance": selected.get("area_weight_balance", ""),
        "tier0_area_fraction": selected.get("tier0_area_fraction", ""),
        "cut_regret": selected.get("cut_regret", ""),
        "native_crossing_nets": f"{native_crossing:.0f}",
        "dynamic_crossing_nets": f"{cand_crossing:.0f}",
        "crossing_reduction": f"{crossing_reduction:.6f}",
        "native_timing_weighted_crossing": f"{native_tw:.6f}",
        "dynamic_timing_weighted_crossing": f"{cand_tw:.6f}",
        "timing_weighted_reduction": f"{tw_reduction:.6f}",
        "timing_weighted_regret": selected.get("timing_weighted_regret", ""),
        "native_timing_crossing_nets": f"{native_timing_nets:.0f}",
        "dynamic_timing_crossing_nets": f"{cand_timing_nets:.0f}",
        "timing_crossing_net_delta": f"{cand_timing_nets - native_timing_nets:.0f}",
        "native_high_timing_crossing_nets": f"{native_high:.0f}",
        "dynamic_high_timing_crossing_nets": f"{cand_high:.0f}",
        "high_timing_crossing_net_delta": f"{cand_high - native_high:.0f}",
        "native_P_avg_cut": f"{native_pavg:.6f}",
        "dynamic_P_avg_cut": f"{cand_pavg:.6f}",
        "P_avg_cut_reduction": f"{pavg_reduction:.6f}",
        "native_P_wst_cut": f"{native_pwst:.6f}",
        "dynamic_P_wst_cut": f"{cand_pwst:.6f}",
        "P_wst_cut_delta": f"{cand_pwst - native_pwst:.6f}",
        "assignment_file": selected.get("assignment_file", ""),
    }


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
        default=Path("results/benchmark_summary/dynamic_constrained_asa_phase3_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/dynamic_constrained_asa_phase3_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    rows = [summarize_case(args.root, design, args.scenario) for design in designs]
    write_csv(args.root / args.summary, rows)

    admissible_rows = [row for row in rows if row.get("status") == "admissible_phase3"]
    rollup_rows = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "admissible_phase3_cases", "value": len(admissible_rows)},
        {"metric": "designs", "value": ",".join(designs)},
        {
            "metric": "mean_objective_reduction",
            "value": f"{mean([f(row, 'objective_reduction') for row in admissible_rows]):.6f}",
        },
        {
            "metric": "mean_crossing_reduction",
            "value": f"{mean([f(row, 'crossing_reduction') for row in admissible_rows]):.6f}",
        },
        {
            "metric": "mean_timing_weighted_reduction",
            "value": f"{mean([f(row, 'timing_weighted_reduction') for row in admissible_rows]):.6f}",
        },
        {
            "metric": "mean_P_avg_cut_reduction",
            "value": f"{mean([f(row, 'P_avg_cut_reduction') for row in admissible_rows]):.6f}",
        },
        {
            "metric": "max_P_wst_cut_delta",
            "value": f"{max([f(row, 'P_wst_cut_delta') for row in admissible_rows], default=0.0):.6f}",
        },
        {
            "metric": "max_timing_weighted_regret",
            "value": f"{max([f(row, 'timing_weighted_regret') for row in admissible_rows], default=0.0):.6f}",
        },
    ]
    write_csv(args.root / args.rollup, rollup_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
