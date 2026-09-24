#!/usr/bin/env python3
"""Summarize TritonPart-compatible ASA guarded Phase-2 results."""

from __future__ import annotations

import csv
from pathlib import Path


OUT_DIR = Path("results/benchmark_summary")
SCENARIO = "state_and_clock_protected"
PRIMARY_DESIGNS = ["picorv32", "riscv32i"]
BOUNDARY_DESIGNS = ["scr1_core_tuned"]


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


def by_case(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row["case"]: row for row in rows if row.get("case")}


def f(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def frac_delta(new: float | None, old: float | None) -> str:
    if new is None or old in (None, 0.0):
        return ""
    return f"{(new - old) / old:.6f}"


def make_primary_row(design: str) -> dict[str, object]:
    repair_path = Path(
        f"results/{design}_tritonpart_compatible_guarded_repair/{SCENARIO}/"
        "tritonpart_compatible_guarded_repair_summary.csv"
    )
    timing_path = OUT_DIR / f"{design}_{SCENARIO}_tritonpart_compatible_guarded_timing_crossing.csv"
    path_cut_path = OUT_DIR / f"{design}_{SCENARIO}_tritonpart_compatible_guarded_path_cuts.csv"

    repair_rows = read_csv(repair_path)
    if not repair_rows:
        return {
            "design": design,
            "scenario": SCENARIO,
            "status": "missing_phase2_result",
            "note": f"Missing {repair_path}",
        }
    repair = repair_rows[0]
    timing = by_case(read_csv(timing_path))
    paths = by_case(read_csv(path_cut_path))
    native_timing = timing.get("native_timing_aware", {})
    asa_timing = timing.get("tritonpart_compatible_asa", {})
    native_paths = paths.get("native_timing_aware", {})
    asa_paths = paths.get("tritonpart_compatible_asa", {})

    timing_regret = frac_delta(
        f(asa_timing.get("timing_weighted_crossing")),
        f(native_timing.get("timing_weighted_crossing")),
    )
    path_regret = frac_delta(f(asa_paths.get("P_avg_cut")), f(native_paths.get("P_avg_cut")))
    pwst_delta = ""
    if f(asa_paths.get("P_wst_cut")) is not None and f(native_paths.get("P_wst_cut")) is not None:
        pwst_delta = fmt(f(asa_paths.get("P_wst_cut")) - f(native_paths.get("P_wst_cut")))  # type: ignore[arg-type]

    admissible = (
        repair.get("initial_area_balance_pass") == "true"
        and repair.get("final_area_balance_pass") == "true"
        and (f(repair.get("cut_regret")) or 0.0) <= 0.05
        and (f(timing_regret) or 0.0) <= 0.01
        and (f(path_regret) or 0.0) <= 0.0
        and (f(pwst_delta) or 0.0) <= 0.0
    )

    return {
        "design": design,
        "scenario": SCENARIO,
        "status": "admissible_phase2" if admissible else "phase2_guard_violation",
        "initial_area_balance_pass": repair.get("initial_area_balance_pass", ""),
        "final_area_balance_pass": repair.get("final_area_balance_pass", ""),
        "final_area_weight_balance": repair.get("final_area_weight_balance", ""),
        "final_tier0_area_fraction": repair.get("final_tier0_area_fraction", ""),
        "cut_regret": repair.get("cut_regret", ""),
        "crossing_connection_regret": repair.get("crossing_connection_regret", ""),
        "timing_weighted_regret_vs_native": timing_regret,
        "P_avg_cut_regret_vs_native": path_regret,
        "P_wst_cut_delta_vs_native": pwst_delta,
        "accepted_moves": repair.get("accepted_moves", ""),
        "rejected_area_moves": repair.get("rejected_area_moves", ""),
        "rejected_cut_moves": repair.get("rejected_cut_moves", ""),
        "rejected_path_moves": repair.get("rejected_path_moves", ""),
        "scenario_gain": repair.get("cumulative_scenario_gain", ""),
        "native_timing_weighted_crossing": native_timing.get("timing_weighted_crossing", ""),
        "asa_timing_weighted_crossing": asa_timing.get("timing_weighted_crossing", ""),
        "native_P_avg_cut": native_paths.get("P_avg_cut", ""),
        "asa_P_avg_cut": asa_paths.get("P_avg_cut", ""),
        "native_P_wst_cut": native_paths.get("P_wst_cut", ""),
        "asa_P_wst_cut": asa_paths.get("P_wst_cut", ""),
        "assignment_file": repair.get("assignment_file", ""),
        "note": "Online guarded repair result.",
    }


def make_boundary_row(design: str) -> dict[str, object]:
    phase1 = read_csv(OUT_DIR / "asa_on_native_phase1_rollup.csv")
    row = next((r for r in phase1 if r.get("design") == design), {})
    return {
        "design": design,
        "scenario": SCENARIO,
        "status": row.get("evidence_status", "boundary_not_rerun_phase2"),
        "initial_area_balance_pass": "",
        "final_area_balance_pass": row.get("area_balance_pass", ""),
        "final_area_weight_balance": row.get("area_weight_balance", ""),
        "final_tier0_area_fraction": row.get("tier0_area_fraction", ""),
        "cut_regret": row.get("crossing_regret_vs_native", ""),
        "crossing_connection_regret": "",
        "timing_weighted_regret_vs_native": row.get("timing_weighted_regret_vs_native", ""),
        "P_avg_cut_regret_vs_native": row.get("P_avg_cut_regret_vs_native", ""),
        "P_wst_cut_delta_vs_native": row.get("P_wst_cut_delta_vs_native", ""),
        "accepted_moves": "",
        "rejected_area_moves": "",
        "rejected_cut_moves": "",
        "rejected_path_moves": "",
        "scenario_gain": row.get("scenario_gain", ""),
        "native_timing_weighted_crossing": "",
        "asa_timing_weighted_crossing": row.get("timing_weighted_crossing", ""),
        "native_P_avg_cut": "",
        "asa_P_avg_cut": "",
        "native_P_wst_cut": "",
        "asa_P_wst_cut": "",
        "assignment_file": row.get("assignment_file", ""),
        "note": row.get("note", "Boundary case retained from Phase 1."),
    }


def main() -> int:
    rows = [make_primary_row(design) for design in PRIMARY_DESIGNS]
    rows.extend(make_boundary_row(design) for design in BOUNDARY_DESIGNS)
    write_csv(OUT_DIR / "tritonpart_compatible_guarded_phase2_summary.csv", rows)

    admissible = [row for row in rows if row.get("status") == "admissible_phase2"]
    timing_gains = [
        -(f(str(row.get("timing_weighted_regret_vs_native"))) or 0.0)
        for row in admissible
        if row.get("timing_weighted_regret_vs_native") != ""
    ]
    rollup = [
        {"metric": "cases", "value": str(len(rows))},
        {"metric": "admissible_phase2_cases", "value": str(len(admissible))},
        {"metric": "admissible_phase2_designs", "value": ",".join(str(row["design"]) for row in admissible)},
        {
            "metric": "mean_admissible_timing_weighted_improvement",
            "value": fmt(sum(timing_gains) / len(timing_gains) if timing_gains else None),
        },
    ]
    write_csv(OUT_DIR / "tritonpart_compatible_guarded_phase2_rollup.csv", rollup)

    lines = [
        "# TritonPart-Compatible ASA Guarded Phase 2",
        "",
        "This summary reports the online guarded-repair prototype, where each accepted move must preserve OpenROAD-compatible area balance, bounded cut regret, and path-cut guards.",
        "",
        "## Result",
        "",
        f"- Admissible Phase-2 cases: {len(admissible)} / {len(rows)}",
        f"- Admissible designs: {', '.join(str(row['design']) for row in admissible) or 'none'}",
        "",
        "## Case Summary",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['design']}",
                "",
                f"- Status: {row['status']}",
                f"- Final area pass: {row['final_area_balance_pass']}",
                f"- Cut regret: {row['cut_regret']}",
                f"- Timing-weighted regret vs native: {row['timing_weighted_regret_vs_native']}",
                f"- P_avg_cut regret vs native: {row['P_avg_cut_regret_vs_native']}",
                f"- P_wst_cut delta vs native: {row['P_wst_cut_delta_vs_native']}",
                f"- Scenario gain: {row['scenario_gain']}",
                f"- Note: {row['note']}",
                "",
            ]
        )
    analysis = OUT_DIR / "tritonpart_compatible_guarded_phase2_summary.md"
    analysis.write_text("\n".join(lines), encoding="utf-8")
    print(analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

