#!/usr/bin/env python3
"""Summarize Phase-3 method-freeze eligibility and anomaly decisions."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_DESIGNS = ["picorv32", "riscv32i", "scr1_core_tuned"]
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


def key(row: dict[str, str]) -> tuple[str, str]:
    return row.get("design", ""), row.get("scenario", "")


def f(row: dict[str, str], name: str, default: float = 0.0) -> float:
    value = row.get(name, "")
    if value == "":
        return default
    return float(value)


def decision_for(
    *,
    design: str,
    scenario: str,
    eligibility: dict[str, str],
    canonical: dict[str, str],
    optimizer: dict[str, str],
) -> tuple[str, str]:
    if eligibility.get("eligible_for_main_result") == "false":
        return "N/A_weak_semantic_coverage", "Scenario target structures are not observable enough for architecture-semantics claims."
    if not canonical:
        return "missing_canonical_metrics", "Canonical convergence metrics are missing."

    if optimizer.get("initial_area_balance_pass") == "false":
        return (
            "boundary_native_area_window",
            "Native timing-aware baseline is already outside the strict reconstructed area-balance window; retain as boundary evidence, not a primary comparable success.",
        )

    if design == "picorv32" and scenario == "control_datapath_split":
        return (
            "diagnostic_anomaly",
            "Architecture-ON improves over native but architecture-OFF is stronger in raw/timing and structural metrics; diagnose before final claims.",
        )

    on_struct_better = canonical.get("architecture_on_better_structural_than_off") == "true"
    on_timing_delta = f(canonical, "on_minus_off_timing_weighted_crossing")
    if on_struct_better and on_timing_delta <= 0:
        return "primary_architecture_evidence", "Architecture-ON improves structural metrics versus OFF without worse timing-weighted crossing."
    if on_struct_better:
        return "secondary_architecture_evidence", "Architecture-ON improves structural metrics versus OFF with a generic timing/cut trade-off."
    return "eligible_tradeoff_case", "Eligible scenario, but architecture-OFF is equal or better on the structural metric."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument(
        "--eligibility",
        type=Path,
        default=Path("results/benchmark_summary/phase3_scenario_eligibility_diagnostic.csv"),
    )
    parser.add_argument(
        "--canonical",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_convergence_canonical_summary.csv"),
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/phase3_method_freeze_summary.csv"),
    )
    parser.add_argument(
        "--rollup",
        type=Path,
        default=Path("results/benchmark_summary/phase3_method_freeze_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    eligibility_rows = {key(row): row for row in read_rows(args.root / args.eligibility)}
    canonical_rows = {key(row): row for row in read_rows(args.root / args.canonical)}
    optimizer_rows = {}
    for design in designs:
        for scenario in scenarios:
            optimizer_path = (
                args.root
                / f"results/{design}_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair"
                / scenario
                / "tritonpart_compatible_dynamic_guarded_repair_summary.csv"
            )
            optimizer_case_rows = read_rows(optimizer_path)
            if optimizer_case_rows:
                optimizer_rows[(design, scenario)] = optimizer_case_rows[0]

    rows: list[dict[str, object]] = []
    for design in designs:
        for scenario in scenarios:
            eligibility = eligibility_rows.get((design, scenario), {})
            canonical = canonical_rows.get((design, scenario), {})
            optimizer = optimizer_rows.get((design, scenario), {})
            decision, rationale = decision_for(
                design=design,
                scenario=scenario,
                eligibility=eligibility,
                canonical=canonical,
                optimizer=optimizer,
            )
            rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "decision": decision,
                    "rationale": rationale,
                    "eligible_for_main_result": eligibility.get("eligible_for_main_result", ""),
                    "initial_area_balance_pass": optimizer.get("initial_area_balance_pass", ""),
                    "final_area_balance_pass": optimizer.get("final_area_balance_pass", ""),
                    "final_area_weight_balance": optimizer.get("final_area_weight_balance", ""),
                    "final_tier0_area_fraction": optimizer.get("final_tier0_area_fraction", ""),
                    "accepted_moves": optimizer.get("accepted_moves", ""),
                    "target_instance_count": eligibility.get("target_instance_count", ""),
                    "target_instance_fraction": eligibility.get("target_instance_fraction", ""),
                    "target_net_count": eligibility.get("target_net_count", ""),
                    "on_crossing_reduction_vs_native": canonical.get("on_crossing_reduction_vs_native", ""),
                    "on_timing_weighted_reduction_vs_native": canonical.get("on_timing_weighted_reduction_vs_native", ""),
                    "on_structural_reduction_vs_native": canonical.get("on_structural_reduction_vs_native", ""),
                    "on_structural_reduction_vs_off": canonical.get("on_structural_reduction_vs_off", ""),
                    "architecture_on_better_structural_than_off": canonical.get("architecture_on_better_structural_than_off", ""),
                }
            )

    write_csv(args.root / args.summary, rows)
    decisions = sorted({str(row["decision"]) for row in rows})
    rollup = [
        {"metric": "cases", "value": len(rows)},
        {"metric": "designs", "value": ",".join(designs)},
        {"metric": "scenarios", "value": ",".join(scenarios)},
    ]
    for decision in decisions:
        rollup.append(
            {
                "metric": f"{decision}_cases",
                "value": sum(1 for row in rows if row["decision"] == decision),
            }
        )
    write_csv(args.root / args.rollup, rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
