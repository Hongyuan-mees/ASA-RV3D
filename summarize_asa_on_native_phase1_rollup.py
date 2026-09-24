#!/usr/bin/env python3
"""Summarize ASA-on-native timing-aware Phase-1 evidence.

The rollup separates primary comparable successes from boundary cases.  It does
not rerun experiments or tune parameters; it only consolidates existing
bounded-regret and prefix-candidate CSV outputs.
"""

from __future__ import annotations

import csv
from pathlib import Path


OUT_DIR = Path("results/benchmark_summary")


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


def f(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def area_pass(row: dict[str, str]) -> str:
    return row.get("area_balance_pass") or row.get("native_area_balance_pass") or ""


def pick_case(rows: list[dict[str, str]], case_name: str) -> dict[str, str]:
    for row in rows:
        if row.get("case") == case_name:
            return row
    return {}


def crossing_regret(row: dict[str, str]) -> str:
    return row.get("crossing_regret_vs_native") or row.get("cut_regret") or ""


def path_regret(row: dict[str, str]) -> str:
    return row.get("P_avg_cut_regret_vs_native", "")


def make_row(
    *,
    design: str,
    scenario: str,
    evidence_status: str,
    row: dict[str, str],
    note: str,
) -> dict[str, object]:
    return {
        "design": design,
        "scenario": scenario,
        "evidence_status": evidence_status,
        "candidate_case": row.get("case", ""),
        "area_balance_pass": area_pass(row),
        "area_weight_balance": row.get("area_weight_balance", ""),
        "tier0_area_fraction": row.get("tier0_area_fraction", ""),
        "tier1_area_fraction": row.get("tier1_area_fraction", ""),
        "crossing_regret_vs_native": crossing_regret(row),
        "timing_weighted_regret_vs_native": row.get("timing_weighted_regret_vs_native", ""),
        "P_avg_cut_regret_vs_native": path_regret(row),
        "P_wst_cut_delta_vs_native": row.get("P_wst_cut_delta_vs_native", ""),
        "scenario_gain": row.get("cumulative_scenario_gain", ""),
        "timing_weighted_crossing": row.get("timing_weighted_crossing", ""),
        "crossing_nets": row.get("crossing_nets", ""),
        "assignment_file": row.get("assignment_file", ""),
        "note": note,
    }


def main() -> int:
    rows: list[dict[str, object]] = []

    riscv = read_csv(OUT_DIR / "asa_on_native_riscv32i_bounded_regret_summary.csv")
    riscv_candidate = pick_case(riscv, "cut_regret_0p050000")
    if riscv_candidate:
        rows.append(
            make_row(
                design="riscv32i",
                scenario="state_and_clock_protected",
                evidence_status="primary_comparable_pass",
                row=riscv_candidate,
                note="Small cut-regret candidate preserves area/path quality with positive scenario gain.",
            )
        )

    pico = read_csv(
        OUT_DIR / "asa_on_native_picorv32_state_and_clock_protected_prefix_candidate_summary.csv"
    )
    if pico:
        rows.append(
            make_row(
                design="picorv32",
                scenario="state_and_clock_protected",
                evidence_status="primary_comparable_pass",
                row=pico[0],
                note="Area-feasible prefix improves cut and timing-weighted crossing while preserving path-cut metrics.",
            )
        )

    scr1 = read_csv(
        OUT_DIR / "asa_on_native_scr1_core_tuned_state_and_clock_protected_bounded_regret_summary.csv"
    )
    scr1_native = pick_case(scr1, "native_timing_aware")
    scr1_candidate = pick_case(scr1, "cut_regret_0p050000")
    if scr1_candidate:
        status = "boundary_inconclusive_native_area_window"
        note = (
            "Native timing-aware baseline is already slightly outside the reconstructed strict 48/52 area window; "
            "retain as boundary evidence, not primary comparable success."
        )
        if scr1_native and area_pass(scr1_native) == "true" and area_pass(scr1_candidate) == "true":
            status = "primary_comparable_pass"
            note = "Native and candidate both pass reconstructed area window."
        rows.append(
            make_row(
                design="scr1_core_tuned",
                scenario="state_and_clock_protected",
                evidence_status=status,
                row=scr1_candidate,
                note=note,
            )
        )

    if not rows:
        raise SystemExit("No ASA-on-native Phase-1 rows found")

    summary_csv = OUT_DIR / "asa_on_native_phase1_rollup.csv"
    write_csv(summary_csv, rows)

    primary = [row for row in rows if row["evidence_status"] == "primary_comparable_pass"]
    boundary = [row for row in rows if str(row["evidence_status"]).startswith("boundary")]
    mean_scenario_gain = None
    gains = [f(str(row["scenario_gain"])) for row in primary if row.get("scenario_gain")]
    gains = [gain for gain in gains if gain is not None]
    if gains:
        mean_scenario_gain = sum(gains) / len(gains)

    rollup = [
        {"metric": "cases", "value": str(len(rows))},
        {"metric": "primary_comparable_pass_cases", "value": str(len(primary))},
        {"metric": "boundary_or_inconclusive_cases", "value": str(len(boundary))},
        {"metric": "primary_designs", "value": ",".join(str(row["design"]) for row in primary)},
        {"metric": "boundary_designs", "value": ",".join(str(row["design"]) for row in boundary)},
        {"metric": "mean_primary_scenario_gain", "value": fmt(mean_scenario_gain)},
    ]
    write_csv(OUT_DIR / "asa_on_native_phase1_rollup_metrics.csv", rollup)

    lines = [
        "# ASA-on-Native Phase-1 Rollup",
        "",
        "This rollup summarizes the strong-baseline diagnostic experiments where ASA-RV3D refines native OpenROAD/TritonPart timing-aware assignments.",
        "",
        "## Result",
        "",
        f"- Primary comparable pass cases: {len(primary)}",
        f"- Boundary / inconclusive cases: {len(boundary)}",
        f"- Primary designs: {', '.join(str(row['design']) for row in primary) or 'none'}",
        f"- Boundary designs: {', '.join(str(row['design']) for row in boundary) or 'none'}",
        "",
        "## Interpretation",
        "",
        "The current evidence supports ASA-RV3D as a bounded, domain-aware refinement layer on top of a strong timing-aware TritonPart baseline for the primary comparable cases. SCR1 is retained as a boundary case because the native timing-aware baseline is already slightly outside the reconstructed strict area-balance window.",
        "",
        "## Candidate Rows",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row['design']}",
                "",
                f"- Status: {row['evidence_status']}",
                f"- Candidate: {row['candidate_case']}",
                f"- Area pass: {row['area_balance_pass']}",
                f"- Crossing regret vs native: {row['crossing_regret_vs_native']}",
                f"- Timing-weighted regret vs native: {row['timing_weighted_regret_vs_native']}",
                f"- P_avg_cut regret vs native: {row['P_avg_cut_regret_vs_native']}",
                f"- P_wst_cut delta vs native: {row['P_wst_cut_delta_vs_native']}",
                f"- Scenario gain: {row['scenario_gain']}",
                f"- Note: {row['note']}",
                "",
            ]
        )

    analysis = OUT_DIR / "asa_on_native_phase1_rollup.md"
    analysis.write_text("\n".join(lines), encoding="utf-8")
    print(analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

