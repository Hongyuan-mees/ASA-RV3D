#!/usr/bin/env python3
"""Summarize one ASA-on-native Phase-1 experiment.

The summary keeps three layers separate:

* native OpenROAD area balance feasibility
* TritonPart-style connectivity/timing-path QoR
* ASA-RV3D architecture/scenario/physical benefit
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def first(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    return rows[0] if rows else {}


def by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in read_rows(path) if row.get(key)}


def f(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def pct(value: float | None) -> str:
    if value is None:
        return ""
    return f"{100.0 * value:.2f}%"


def delta_frac(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0.0):
        return None
    return (new - old) / old


def improvement(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0.0):
        return None
    return (old - new) / old


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", default="riscv32i")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument("--output-summary", type=Path, default=Path("results/benchmark_summary/asa_on_native_riscv32i_summary.csv"))
    parser.add_argument("--output-analysis", type=Path, default=Path("results/benchmark_summary/asa_on_native_riscv32i_analysis.md"))
    args = parser.parse_args()

    phase = by_key(Path("results/benchmark_summary/timing_aware_start_asa_summary.csv"), "design")
    phase_row = next(
        (
            row
            for row in phase.values()
            if row.get("design") == args.design and row.get("scenario") == args.scenario
        ),
        {},
    )
    path_cuts = by_key(Path(f"results/benchmark_summary/asa_on_native_{args.design}_path_cuts.csv"), "case")
    native_area = first(Path(f"results/benchmark_summary/asa_on_native_{args.design}_native_area_balance.csv"))
    asa_area = first(Path(f"results/benchmark_summary/asa_on_native_{args.design}_asa_area_balance.csv"))

    native_path = path_cuts.get("native_timing_aware", {})
    asa_path = path_cuts.get("asa_on_native", {})

    native_cut = f(phase_row.get("ta_crossing_nets"))
    asa_cut = f(phase_row.get("asa_crossing_nets"))
    native_tw = f(phase_row.get("ta_timing_weighted_crossing"))
    asa_tw = f(phase_row.get("asa_timing_weighted_crossing"))
    native_scenario = f(phase_row.get("ta_scenario_objective"))
    asa_scenario = f(phase_row.get("asa_scenario_objective"))
    native_arch = f(phase_row.get("ta_architecture_preference_penalty"))
    asa_arch = f(phase_row.get("asa_architecture_preference_penalty"))
    native_phys = f(phase_row.get("ta_physical_context_penalty"))
    asa_phys = f(phase_row.get("asa_physical_context_penalty"))

    native_pavg = f(native_path.get("P_avg_cut"))
    asa_pavg = f(asa_path.get("P_avg_cut"))
    native_pwst = f(native_path.get("P_wst_cut"))
    asa_pwst = f(asa_path.get("P_wst_cut"))

    rows = [
        {
            "metric": "native_area_balance_pass",
            "native_timing_aware_tp": native_area.get("balance_constraint_2_pass", ""),
            "asa_on_native": asa_area.get("balance_constraint_2_pass", ""),
            "change": "pass/fail",
            "layer": "A_hard_feasibility",
        },
        {
            "metric": "native_area_weight_balance",
            "native_timing_aware_tp": native_area.get("area_weight_balance", ""),
            "asa_on_native": asa_area.get("area_weight_balance", ""),
            "change": fmt(delta_frac(f(asa_area.get("area_weight_balance")), f(native_area.get("area_weight_balance")))),
            "layer": "A_hard_feasibility",
        },
        {
            "metric": "cutsize_crossing_nets",
            "native_timing_aware_tp": fmt(native_cut),
            "asa_on_native": fmt(asa_cut),
            "change": fmt(delta_frac(asa_cut, native_cut)),
            "layer": "B_connectivity_qor",
        },
        {
            "metric": "P_avg_cut",
            "native_timing_aware_tp": fmt(native_pavg),
            "asa_on_native": fmt(asa_pavg),
            "change": fmt(delta_frac(asa_pavg, native_pavg)),
            "layer": "B_timing_path_qor",
        },
        {
            "metric": "P_wst_cut",
            "native_timing_aware_tp": fmt(native_pwst),
            "asa_on_native": fmt(asa_pwst),
            "change": fmt((asa_pwst - native_pwst) if asa_pwst is not None and native_pwst is not None else None),
            "layer": "B_timing_path_qor",
        },
        {
            "metric": "timing_weighted_crossing",
            "native_timing_aware_tp": fmt(native_tw),
            "asa_on_native": fmt(asa_tw),
            "change": fmt(delta_frac(asa_tw, native_tw)),
            "layer": "B_supplementary_timing",
        },
        {
            "metric": "scenario_objective",
            "native_timing_aware_tp": fmt(native_scenario),
            "asa_on_native": fmt(asa_scenario),
            "change": fmt(improvement(asa_scenario, native_scenario)),
            "layer": "C_asa_domain_qor",
        },
        {
            "metric": "architecture_preference_penalty",
            "native_timing_aware_tp": fmt(native_arch),
            "asa_on_native": fmt(asa_arch),
            "change": fmt(improvement(asa_arch, native_arch)),
            "layer": "C_asa_domain_qor",
        },
        {
            "metric": "physical_context_penalty",
            "native_timing_aware_tp": fmt(native_phys),
            "asa_on_native": fmt(asa_phys),
            "change": fmt(improvement(asa_phys, native_phys)),
            "layer": "C_asa_domain_qor",
        },
        {
            "metric": "instance_balance_diagnostic",
            "native_timing_aware_tp": phase_row.get("ta_instance_balance", ""),
            "asa_on_native": phase_row.get("asa_instance_balance", ""),
            "change": "diagnostic_only",
            "layer": "diagnostic",
        },
        {
            "metric": "architecture_weight_balance_diagnostic",
            "native_timing_aware_tp": phase_row.get("ta_weight_balance", ""),
            "asa_on_native": phase_row.get("asa_weight_balance", ""),
            "change": "diagnostic_only",
            "layer": "diagnostic",
        },
    ]
    write_rows(args.output_summary, rows)

    area_pass = asa_area.get("balance_constraint_2_pass", "")
    cut_regret = delta_frac(asa_cut, native_cut)
    pavg_regret = delta_frac(asa_pavg, native_pavg)
    tw_regret = delta_frac(asa_tw, native_tw)
    scenario_gain = improvement(asa_scenario, native_scenario)
    arch_gain = improvement(asa_arch, native_arch)

    analysis = [
        f"# ASA-on-Native Phase 1: {args.design} / {args.scenario}",
        "",
        "This is a one-design, one-scenario strong-baseline check.",
        "",
        "## Key Questions",
        "",
        f"1. Native area balance remains legal: {area_pass}",
        f"2. Cutsize regret: {pct(cut_regret)}",
        f"3. P_avg_cut regret: {pct(pavg_regret)}",
        f"4. Timing-weighted crossing regret: {pct(tw_regret)}",
        f"5. Scenario objective improvement: {pct(scenario_gain)}",
        f"6. Architecture penalty improvement: {pct(arch_gain)}",
        "",
        "## Interpretation Rule",
        "",
        "Continue only if native area balance remains legal and the architecture/scenario benefit is not dominated by connectivity or timing-path regret.",
        "",
    ]
    args.output_analysis.parent.mkdir(parents=True, exist_ok=True)
    args.output_analysis.write_text("\n".join(analysis), encoding="utf-8")
    print(args.output_analysis)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
