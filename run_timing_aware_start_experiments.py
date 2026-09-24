#!/usr/bin/env python3
"""Run Phase-1 ASA-on-native-timing-aware TritonPart experiments.

This is the zero-tuning strong-baseline experiment:

    native OpenROAD triton_part_design timing-aware assignment
        -> existing ASA-RV3D timing-regret guarded repair

The script intentionally does not tune ASA weights or per-design parameters. It
only changes the starting assignment passed to the existing repair script.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


DESIGNS = ["riscv32i", "picorv32", "scr1_core_tuned"]
SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]
REPAIR_SCRIPT = Path("partition/partition_tritonpart_timing_regret_guarded_repair.py")
TIMING_CROSSING_SCRIPT = Path("evaluation/evaluate_timing_crossing.py")


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def metric_rows(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for row in read_rows(path):
        key = row.get("metric")
        if key:
            data[key] = row.get("value", "")
    return data


def by_key(path: Path, key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in read_rows(path) if row.get(key)}


def as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def frac_delta(new_value: float | None, old_value: float | None) -> float | None:
    if new_value is None or old_value in (None, 0.0):
        return None
    return (new_value - old_value) / old_value


def improvement(new_value: float | None, old_value: float | None) -> float | None:
    if new_value is None or old_value in (None, 0.0):
        return None
    return (old_value - new_value) / old_value


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def run(cmd: list[str], dry_run: bool = False) -> None:
    print("+", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def repair_supports_frozen_instances() -> bool:
    if not REPAIR_SCRIPT.exists():
        return False
    result = subprocess.run(
        [sys.executable, str(REPAIR_SCRIPT), "--help"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return "--frozen-instances" in result.stdout


def write_frozen_instances(mapping_report: Path, output_path: Path) -> int:
    rows = read_rows(mapping_report)
    frozen = [
        row["instance"]
        for row in rows
        if row.get("status", "").startswith("fallback") and row.get("instance")
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(frozen) + ("\n" if frozen else ""), encoding="utf-8")
    return len(frozen)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", choices=DESIGNS)
    parser.add_argument("--scenario", action="append", choices=SCENARIOS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--stop-after-run",
        action="store_true",
        help="Run repair/evaluation commands but do not aggregate summaries.",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/timing_aware_start_asa_summary.csv"),
    )
    parser.add_argument(
        "--output-rollup",
        type=Path,
        default=Path("results/benchmark_summary/timing_aware_start_asa_rollup.csv"),
    )
    args = parser.parse_args()

    designs = args.design or DESIGNS
    scenarios = args.scenario or SCENARIOS
    supports_freeze = repair_supports_frozen_instances()

    for design in designs:
        initial = Path(
            f"results/{design}_tritonpart_design_timing_aware/"
            "tritonpart_design_timing_aware_assignment.csv"
        )
        if not initial.exists():
            raise RuntimeError(f"Missing native timing-aware assignment: {initial}")
        for scenario in scenarios:
            out_dir = Path(f"results/{design}_timing_aware_start_asa/{scenario}")
            mapping_report = Path(f"results/{design}_tritonpart_design_timing_aware/name_mapping_report.csv")
            frozen_path = out_dir / "frozen_fallback_instances.txt"
            fallback_rows = write_frozen_instances(mapping_report, frozen_path)

            cmd = [
                sys.executable,
                str(REPAIR_SCRIPT),
                "--design",
                design,
                "--scenario",
                scenario,
                "--features-dir",
                f"results/{design}_features",
                "--tritonpart-assignment",
                str(initial),
                "--output-dir",
                str(out_dir),
            ]
            freeze_enforced = False
            if supports_freeze and fallback_rows:
                cmd.extend(["--frozen-instances", str(frozen_path)])
                freeze_enforced = True

            run(cmd, dry_run=args.dry_run)

            repaired = out_dir / "tritonpart_timing_regret_guarded_repair_assignment.csv"
            timing_out = Path(
                f"results/benchmark_summary/timing_aware_start_{design}_{scenario}_timing_crossing.csv"
            )
            timing_cmd = [
                sys.executable,
                str(TIMING_CROSSING_SCRIPT),
                "--design",
                design,
                "--features-dir",
                f"results/{design}_features",
                "--timing",
                f"results/{design}_features/timing_context_scores.csv",
                "--assignment",
                f"native_timing_aware={initial}",
                "--assignment",
                f"asa_on_native={repaired}",
                "--output",
                str(timing_out),
            ]
            run(timing_cmd, dry_run=args.dry_run)

            meta_path = out_dir / "timing_aware_start_meta.csv"
            write_rows(
                meta_path,
                [
                    {
                        "design": design,
                        "scenario": scenario,
                        "native_assignment": str(initial),
                        "fallback_rows": str(fallback_rows),
                        "freeze_fallback_supported": str(supports_freeze).lower(),
                        "freeze_fallback_enforced": str(freeze_enforced).lower(),
                    }
                ],
            )

    if args.dry_run or args.stop_after_run:
        return 0

    summary: list[dict[str, str]] = []
    for design in designs:
        for scenario in scenarios:
            out_dir = Path(f"results/{design}_timing_aware_start_asa/{scenario}")
            comparison = by_key(out_dir / "partition_comparison.csv", "strategy")
            timing = by_key(
                Path(f"results/benchmark_summary/timing_aware_start_{design}_{scenario}_timing_crossing.csv"),
                "case",
            )
            meta = read_rows(out_dir / "timing_aware_start_meta.csv")
            meta_row = meta[0] if meta else {}

            ta = comparison.get("tritonpart_initial", {})
            asa = comparison.get("tritonpart_timing_regret_guarded_repair", {})
            ta_timing = timing.get("native_timing_aware", {})
            asa_timing = timing.get("asa_on_native", {})

            ta_scenario = as_float(ta.get("scenario_objective"))
            asa_scenario = as_float(asa.get("scenario_objective"))
            ta_arch = as_float(ta.get("architecture_preference_penalty"))
            asa_arch = as_float(asa.get("architecture_preference_penalty"))
            ta_phys = as_float(ta.get("physical_context_crossing_penalty"))
            asa_phys = as_float(asa.get("physical_context_crossing_penalty"))
            ta_combined = as_float(ta.get("timing_augmented_objective"))
            asa_combined = as_float(asa.get("timing_augmented_objective"))

            ta_tw = as_float(ta_timing.get("timing_weighted_crossing"))
            asa_tw = as_float(asa_timing.get("timing_weighted_crossing"))
            ta_cross = as_float(ta.get("crossing_nets"))
            asa_cross = as_float(asa.get("crossing_nets"))
            ta_conn = as_float(ta.get("crossing_connections_proxy"))
            asa_conn = as_float(asa.get("crossing_connections_proxy"))

            summary.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "fallback_rows": meta_row.get("fallback_rows", ""),
                    "freeze_fallback_supported": meta_row.get("freeze_fallback_supported", ""),
                    "freeze_fallback_enforced": meta_row.get("freeze_fallback_enforced", ""),
                    "ta_scenario_objective": fmt(ta_scenario),
                    "asa_scenario_objective": fmt(asa_scenario),
                    "scenario_improvement_fraction": fmt(improvement(asa_scenario, ta_scenario)),
                    "ta_architecture_preference_penalty": fmt(ta_arch),
                    "asa_architecture_preference_penalty": fmt(asa_arch),
                    "architecture_penalty_improvement_fraction": fmt(improvement(asa_arch, ta_arch)),
                    "ta_physical_context_penalty": fmt(ta_phys),
                    "asa_physical_context_penalty": fmt(asa_phys),
                    "physical_penalty_improvement_fraction": fmt(improvement(asa_phys, ta_phys)),
                    "ta_timing_augmented_objective": fmt(ta_combined),
                    "asa_timing_augmented_objective": fmt(asa_combined),
                    "combined_objective_improvement_fraction": fmt(improvement(asa_combined, ta_combined)),
                    "ta_timing_weighted_crossing": fmt(ta_tw),
                    "asa_timing_weighted_crossing": fmt(asa_tw),
                    "timing_regret_fraction": fmt(frac_delta(asa_tw, ta_tw)),
                    "ta_timing_crossing_nets": ta_timing.get("timing_crossing_nets", ""),
                    "asa_timing_crossing_nets": asa_timing.get("timing_crossing_nets", ""),
                    "ta_high_timing_crossing_nets": ta_timing.get("high_timing_crossing_nets", ""),
                    "asa_high_timing_crossing_nets": asa_timing.get("high_timing_crossing_nets", ""),
                    "ta_crossing_nets": fmt(ta_cross),
                    "asa_crossing_nets": fmt(asa_cross),
                    "crossing_delta_fraction": fmt(frac_delta(asa_cross, ta_cross)),
                    "ta_crossing_connections_proxy": fmt(ta_conn),
                    "asa_crossing_connections_proxy": fmt(asa_conn),
                    "crossing_connection_delta_fraction": fmt(frac_delta(asa_conn, ta_conn)),
                    "ta_instance_balance": ta.get("instance_balance_ratio", ""),
                    "asa_instance_balance": asa.get("instance_balance_ratio", ""),
                    "ta_weight_balance": ta.get("weight_balance_ratio", ""),
                    "asa_weight_balance": asa.get("weight_balance_ratio", ""),
                }
            )

    write_rows(args.output_summary, summary)

    def vals(column: str) -> list[float]:
        return [float(row[column]) for row in summary if row.get(column)]

    scenario_improvements = [v for v in vals("scenario_improvement_fraction")]
    timing_regrets = [v for v in vals("timing_regret_fraction")]
    crossing_deltas = [v for v in vals("crossing_delta_fraction")]
    rollup = [
        {"metric": "cases", "value": str(len(summary))},
        {"metric": "designs", "value": ",".join(designs)},
        {"metric": "scenarios", "value": ",".join(scenarios)},
        {
            "metric": "scenario_improved_cases",
            "value": str(sum(1 for v in scenario_improvements if v > 0.0)),
        },
        {
            "metric": "timing_improved_or_equal_cases",
            "value": str(sum(1 for v in timing_regrets if v <= 0.0)),
        },
        {
            "metric": "timing_regret_le_1pct_cases",
            "value": str(sum(1 for v in timing_regrets if v <= 0.01)),
        },
        {
            "metric": "mean_scenario_improvement",
            "value": fmt(sum(scenario_improvements) / len(scenario_improvements) if scenario_improvements else None),
        },
        {
            "metric": "mean_timing_regret",
            "value": fmt(sum(timing_regrets) / len(timing_regrets) if timing_regrets else None),
        },
        {
            "metric": "max_timing_regret",
            "value": fmt(max(timing_regrets) if timing_regrets else None),
        },
        {
            "metric": "mean_crossing_delta",
            "value": fmt(sum(crossing_deltas) / len(crossing_deltas) if crossing_deltas else None),
        },
        {
            "metric": "min_instance_balance",
            "value": fmt(min(as_float(row.get("asa_instance_balance")) or 1.0 for row in summary)),
        },
        {
            "metric": "min_weight_balance",
            "value": fmt(min(as_float(row.get("asa_weight_balance")) or 1.0 for row in summary)),
        },
        {
            "metric": "freeze_fallback_enforced_cases",
            "value": str(sum(1 for row in summary if row.get("freeze_fallback_enforced") == "true")),
        },
    ]
    write_rows(args.output_rollup, rollup)

    print(args.output_summary)
    print(args.output_rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
