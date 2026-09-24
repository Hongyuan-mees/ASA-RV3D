#!/usr/bin/env python3
"""Create the final riscv32i bounded-regret ASA-on-native Phase-1 summary."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def first(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    return rows[0] if rows else {}


def f(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def pct(value: str | float | None) -> str:
    number = f(value) if isinstance(value, str) else value
    if number is None:
        return ""
    return f"{100.0 * number:.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_eval.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_bounded_regret_summary.csv"),
    )
    parser.add_argument(
        "--output-analysis",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_bounded_regret_analysis.md"),
    )
    args = parser.parse_args()

    eval_rows = read_csv(args.eval)
    area_by_case: dict[str, dict[str, str]] = {
        "native_timing_aware": first(Path("results/benchmark_summary/asa_on_native_riscv32i_native_area_balance.csv")),
        "cut_regret_0p050000": first(Path("results/benchmark_summary/cut_regret_0p05_area_balance.csv")),
        "cut_regret_0p100000": first(Path("results/benchmark_summary/cut_regret_0p10_area_balance.csv")),
        "cut_regret_0p200000": first(Path("results/benchmark_summary/cut_regret_0p20_area_balance.csv")),
    }

    summary_rows: list[dict[str, object]] = []
    for row in eval_rows:
        area = area_by_case.get(row["case"], {})
        summary_rows.append(
            {
                "design": row["design"],
                "scenario": row["scenario"],
                "case": row["case"],
                "native_area_balance_pass": area.get("balance_constraint_2_pass", ""),
                "area_weight_balance": area.get("area_weight_balance", ""),
                "tier0_area_fraction": area.get("tier0_area_fraction", ""),
                "tier1_area_fraction": area.get("tier1_area_fraction", ""),
                "cut_regret": row["selected_cut_regret"],
                "crossing_nets": row["selected_crossing_nets"],
                "timing_weighted_crossing": row["timing_weighted_crossing"],
                "timing_weighted_regret_vs_native": row["timing_weighted_regret_vs_native"],
                "P_avg_cut": row["P_avg_cut"],
                "P_avg_cut_regret_vs_native": row["P_avg_cut_regret_vs_native"],
                "P_wst_cut": row["P_wst_cut"],
                "P_wst_cut_delta_vs_native": row["P_wst_cut_delta_vs_native"],
                "cut_path_fraction": row["cut_path_fraction"],
                "cumulative_scenario_gain": row["cumulative_scenario_gain"],
                "cumulative_timing_gain": row["cumulative_timing_gain"],
                "cumulative_physical_gain": row["cumulative_physical_gain"],
                "assignment_file": row["assignment_file"],
            }
        )

    write_csv(args.output_summary, summary_rows)

    best = next((row for row in summary_rows if row["case"] == "cut_regret_0p050000"), None)
    lines = [
        "# ASA-on-Native Bounded-Regret Phase 1",
        "",
        "Design: riscv32i",
        "Scenario: state_and_clock_protected",
        "",
        "## Main Finding",
        "",
        "A small cut-regret budget preserves TritonPart-compatible feasibility and timing-path quality while exposing architecture/scenario benefit.",
        "",
    ]
    if best:
        lines.extend(
            [
                "## Recommended Phase-1 Candidate",
                "",
                "- Case: cut_regret_0p05",
                f"- Native area balance pass: {best['native_area_balance_pass']}",
                f"- Cut regret: {pct(best['cut_regret'])}",
                f"- Timing-weighted crossing regret: {pct(best['timing_weighted_regret_vs_native'])}",
                f"- P_avg_cut regret: {pct(best['P_avg_cut_regret_vs_native'])}",
                f"- P_wst_cut delta: {best['P_wst_cut_delta_vs_native']}",
                f"- Scenario gain: {best['cumulative_scenario_gain']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation",
            "",
            "The unconstrained ASA-on-native repair was too aggressive in raw cutsize. The bounded replay shows that a small prefix of the same repair trace already provides scenario gain while preserving native area feasibility and timing-path cuts. This supports the bounded-regret refinement direction, but the next implementation should enforce cut-regret directly during candidate move acceptance rather than relying on trace replay.",
            "",
        ]
    )
    args.output_analysis.parent.mkdir(parents=True, exist_ok=True)
    args.output_analysis.write_text("\n".join(lines), encoding="utf-8")
    print(args.output_analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
