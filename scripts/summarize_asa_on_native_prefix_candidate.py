#!/usr/bin/env python3
"""Pick the best area-feasible ASA-on-native prefix candidate."""

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


def f(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def pct(value: str | float | None) -> str:
    number = f(value) if isinstance(value, str) else (value or 0.0)
    return f"{100.0 * number:.2f}%"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", default="picorv32")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_eval.csv"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_candidate_summary.csv"),
    )
    parser.add_argument(
        "--output-analysis",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_candidate_analysis.md"),
    )
    args = parser.parse_args()

    rows = read_csv(args.input)
    candidates = [
        row
        for row in rows
        if row["case"] != "native_timing_aware"
        and row.get("area_balance_pass") == "true"
        and f(row.get("P_avg_cut_regret_vs_native")) <= 0.0
        and f(row.get("P_wst_cut_delta_vs_native")) <= 0.0
    ]
    if not candidates:
        candidates = [
            row
            for row in rows
            if row["case"] != "native_timing_aware" and row.get("area_balance_pass") == "true"
        ]
    if not candidates:
        raise SystemExit("No area-feasible prefix candidates found")

    best = max(
        candidates,
        key=lambda row: (
            f(row.get("cumulative_scenario_gain")),
            -f(row.get("timing_weighted_regret_vs_native")),
            -f(row.get("crossing_regret_vs_native")),
        ),
    )
    write_csv(args.output_summary, [best])

    lines = [
        f"# ASA-on-Native Prefix Candidate: {args.design} / {args.scenario}",
        "",
        "## Selected Candidate",
        "",
        f"- Case: {best['case']}",
        f"- Area balance pass: {best['area_balance_pass']}",
        f"- Area weight balance: {best['area_weight_balance']}",
        f"- Tier0 area fraction: {best['tier0_area_fraction']}",
        f"- Crossing regret vs native: {pct(best['crossing_regret_vs_native'])}",
        f"- Timing-weighted crossing regret vs native: {pct(best['timing_weighted_regret_vs_native'])}",
        f"- P_avg_cut regret vs native: {pct(best['P_avg_cut_regret_vs_native'])}",
        f"- P_wst_cut delta vs native: {best['P_wst_cut_delta_vs_native']}",
        f"- Scenario gain: {best['cumulative_scenario_gain']}",
        "",
        "## Interpretation",
        "",
        "This prefix is an area-feasible ASA-on-native refinement point. It should be treated as a bounded diagnostic candidate until the same area/cut/path guards are enforced directly during move acceptance.",
        "",
    ]
    args.output_analysis.parent.mkdir(parents=True, exist_ok=True)
    args.output_analysis.write_text("\n".join(lines), encoding="utf-8")
    print(args.output_analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

