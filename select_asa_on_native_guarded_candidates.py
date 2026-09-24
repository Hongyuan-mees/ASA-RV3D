#!/usr/bin/env python3
"""Select ASA-on-native candidates using explicit guard rules.

This is a Phase-1 diagnostic selector.  It does not rerun optimization and does
not tune parameters.  It reads the existing ASA-on-native bounded/prefix
candidate summaries, applies one fixed set of guard thresholds, and reports
which candidates are admissible.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


OUT_DIR = Path("results/benchmark_summary")


DEFAULT_INPUTS = [
    (
        "riscv32i",
        "state_and_clock_protected",
        OUT_DIR / "asa_on_native_riscv32i_bounded_regret_summary.csv",
        "bounded_cut_regret",
    ),
    (
        "picorv32",
        "state_and_clock_protected",
        OUT_DIR / "asa_on_native_picorv32_state_and_clock_protected_prefix_candidate_summary.csv",
        "area_feasible_prefix",
    ),
    (
        "scr1_core_tuned",
        "state_and_clock_protected",
        OUT_DIR / "asa_on_native_scr1_core_tuned_state_and_clock_protected_bounded_regret_summary.csv",
        "bounded_cut_regret",
    ),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def area_pass(row: dict[str, str]) -> bool:
    return (row.get("area_balance_pass") or row.get("native_area_balance_pass")) == "true"


def candidate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("case") != "native_timing_aware"]


def metric(row: dict[str, str], *names: str) -> float | None:
    for name in names:
        value = as_float(row.get(name))
        if value is not None:
            return value
    return None


def select_best(
    rows: list[dict[str, str]],
    *,
    max_cut_regret: float,
    max_timing_weighted_regret: float,
    max_pavg_regret: float,
    max_pwst_delta: float,
) -> tuple[dict[str, str] | None, list[dict[str, object]]]:
    evaluated: list[dict[str, object]] = []
    admissible: list[dict[str, str]] = []
    for row in candidate_rows(rows):
        cut_regret = metric(row, "crossing_regret_vs_native", "cut_regret")
        timing_regret = metric(row, "timing_weighted_regret_vs_native")
        pavg_regret = metric(row, "P_avg_cut_regret_vs_native")
        pwst_delta = metric(row, "P_wst_cut_delta_vs_native")

        reasons: list[str] = []
        if not area_pass(row):
            reasons.append("area_balance")
        if cut_regret is None or cut_regret > max_cut_regret:
            reasons.append("cut_regret")
        if timing_regret is None or timing_regret > max_timing_weighted_regret:
            reasons.append("timing_weighted_regret")
        if pavg_regret is not None and pavg_regret > max_pavg_regret:
            reasons.append("P_avg_cut_regret")
        if pwst_delta is not None and pwst_delta > max_pwst_delta:
            reasons.append("P_wst_cut_delta")

        accepted = not reasons
        if accepted:
            admissible.append(row)
        evaluated.append(
            {
                "case": row.get("case", ""),
                "accepted": str(accepted).lower(),
                "reject_reasons": ";".join(reasons),
                "area_balance_pass": str(area_pass(row)).lower(),
                "cut_regret": fmt(cut_regret),
                "timing_weighted_regret": fmt(timing_regret),
                "P_avg_cut_regret": fmt(pavg_regret),
                "P_wst_cut_delta": fmt(pwst_delta),
                "scenario_gain": row.get("cumulative_scenario_gain", ""),
            }
        )

    if not admissible:
        return None, evaluated
    best = max(
        admissible,
        key=lambda row: (
            metric(row, "cumulative_scenario_gain") or 0.0,
            -(metric(row, "timing_weighted_regret_vs_native") or 0.0),
            -(metric(row, "crossing_regret_vs_native", "cut_regret") or 0.0),
        ),
    )
    return best, evaluated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-cut-regret", type=float, default=0.05)
    parser.add_argument("--max-timing-weighted-regret", type=float, default=0.01)
    parser.add_argument("--max-pavg-regret", type=float, default=0.0)
    parser.add_argument("--max-pwst-delta", type=float, default=0.0)
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=OUT_DIR / "asa_on_native_guarded_candidate_summary.csv",
    )
    parser.add_argument(
        "--output-details",
        type=Path,
        default=OUT_DIR / "asa_on_native_guarded_candidate_details.csv",
    )
    parser.add_argument(
        "--output-rollup",
        type=Path,
        default=OUT_DIR / "asa_on_native_guarded_candidate_rollup.csv",
    )
    parser.add_argument(
        "--output-analysis",
        type=Path,
        default=OUT_DIR / "asa_on_native_guarded_candidate_analysis.md",
    )
    args = parser.parse_args()

    summary_rows: list[dict[str, object]] = []
    detail_rows: list[dict[str, object]] = []
    for design, scenario, path, source_type in DEFAULT_INPUTS:
        rows = read_csv(path)
        if not rows:
            summary_rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "source_type": source_type,
                    "status": "missing_input",
                    "selected_case": "",
                    "area_balance_pass": "",
                    "cut_regret": "",
                    "timing_weighted_regret": "",
                    "P_avg_cut_regret": "",
                    "P_wst_cut_delta": "",
                    "scenario_gain": "",
                    "assignment_file": "",
                    "input": str(path),
                }
            )
            continue

        selected, evaluated = select_best(
            rows,
            max_cut_regret=args.max_cut_regret,
            max_timing_weighted_regret=args.max_timing_weighted_regret,
            max_pavg_regret=args.max_pavg_regret,
            max_pwst_delta=args.max_pwst_delta,
        )
        for row in evaluated:
            out = {
                "design": design,
                "scenario": scenario,
                "source_type": source_type,
                "input": str(path),
            }
            out.update(row)
            detail_rows.append(out)

        if selected is None:
            rejected = [row for row in evaluated if row.get("accepted") == "false"]
            reasons = sorted({reason for row in rejected for reason in str(row.get("reject_reasons", "")).split(";") if reason})
            summary_rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "source_type": source_type,
                    "status": "no_admissible_candidate",
                    "selected_case": "",
                    "area_balance_pass": "",
                    "cut_regret": "",
                    "timing_weighted_regret": "",
                    "P_avg_cut_regret": "",
                    "P_wst_cut_delta": "",
                    "scenario_gain": "",
                    "assignment_file": "",
                    "input": str(path),
                    "reject_reasons": ";".join(reasons),
                }
            )
            continue

        summary_rows.append(
            {
                "design": design,
                "scenario": scenario,
                "source_type": source_type,
                "status": "admissible",
                "selected_case": selected.get("case", ""),
                "area_balance_pass": str(area_pass(selected)).lower(),
                "cut_regret": fmt(metric(selected, "crossing_regret_vs_native", "cut_regret")),
                "timing_weighted_regret": fmt(metric(selected, "timing_weighted_regret_vs_native")),
                "P_avg_cut_regret": fmt(metric(selected, "P_avg_cut_regret_vs_native")),
                "P_wst_cut_delta": fmt(metric(selected, "P_wst_cut_delta_vs_native")),
                "scenario_gain": selected.get("cumulative_scenario_gain", ""),
                "assignment_file": selected.get("assignment_file", ""),
                "input": str(path),
                "reject_reasons": "",
            }
        )

    write_csv(args.output_summary, summary_rows)
    write_csv(args.output_details, detail_rows)

    admissible = [row for row in summary_rows if row["status"] == "admissible"]
    rollup = [
        {"metric": "cases", "value": str(len(summary_rows))},
        {"metric": "admissible_cases", "value": str(len(admissible))},
        {"metric": "admissible_designs", "value": ",".join(str(row["design"]) for row in admissible)},
        {"metric": "max_cut_regret", "value": f"{args.max_cut_regret:.6f}"},
        {"metric": "max_timing_weighted_regret", "value": f"{args.max_timing_weighted_regret:.6f}"},
        {"metric": "max_pavg_regret", "value": f"{args.max_pavg_regret:.6f}"},
        {"metric": "max_pwst_delta", "value": f"{args.max_pwst_delta:.6f}"},
    ]
    write_csv(args.output_rollup, rollup)

    lines = [
        "# ASA-on-Native Guarded Candidate Selection",
        "",
        "This diagnostic applies one fixed guard rule to existing ASA-on-native candidates.",
        "",
        "## Guard Rule",
        "",
        f"- area_balance_pass must be true",
        f"- crossing regret <= {args.max_cut_regret:.2%}",
        f"- timing-weighted regret <= {args.max_timing_weighted_regret:.2%}",
        f"- P_avg_cut regret <= {args.max_pavg_regret:.2%}",
        f"- P_wst_cut delta <= {args.max_pwst_delta:.6f}",
        "",
        "## Result",
        "",
        f"- Admissible cases: {len(admissible)} / {len(summary_rows)}",
        f"- Admissible designs: {', '.join(str(row['design']) for row in admissible) or 'none'}",
        "",
    ]
    for row in summary_rows:
        lines.extend(
            [
                f"### {row['design']}",
                "",
                f"- Status: {row['status']}",
                f"- Selected case: {row['selected_case']}",
                f"- Cut regret: {row['cut_regret']}",
                f"- Timing-weighted regret: {row['timing_weighted_regret']}",
                f"- P_avg_cut regret: {row['P_avg_cut_regret']}",
                f"- P_wst_cut delta: {row['P_wst_cut_delta']}",
                f"- Scenario gain: {row['scenario_gain']}",
                f"- Reject reasons: {row.get('reject_reasons', '')}",
                "",
            ]
        )
    args.output_analysis.write_text("\n".join(lines), encoding="utf-8")
    print(args.output_analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

