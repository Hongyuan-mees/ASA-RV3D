#!/usr/bin/env python3
"""Run downstream vertical-delay validation for normalized dynamic Phase-3.

This wrapper evaluates final normalized dynamic assignments with the shared
path-level downstream proxy.  It intentionally does not reuse the older
path-aware ASA sweep labels because Phase-3 compares:

* native_timing_aware
* normalized_architecture_on
* normalized_architecture_off

The downstream proxy is independent of the Phase-3 checkpoint selection.  It
reports vertical-link path transition metrics and WNS/TNS degradation estimates
for a fixed vertical delay.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path


DESIGNS = ["picorv32", "riscv32i"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
DEFAULT_DELAYS = [0.02, 0.05, 0.10]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def as_float(value: str) -> float:
    return float(value) if value not in ("", None) else 0.0


def delta(new: str, base: str) -> str:
    return f"{as_float(new) - as_float(base):.6f}"


def reduction(base: str, new: str) -> str:
    return f"{as_float(base) - as_float(new):.6f}"


def delay_tag(delay: float) -> str:
    return f"{delay:.6f}".rstrip("0").rstrip(".").replace(".", "p")


def assignment_paths(design: str, scenario: str) -> dict[str, Path]:
    return {
        "native_timing_aware": (
            Path("results")
            / f"{design}_tritonpart_design_timing_aware"
            / "tritonpart_design_timing_aware_assignment.csv"
        ),
        "normalized_architecture_on": (
            Path("results")
            / f"{design}_tritonpart_compatible_normalized_dynamic_convergence_guarded_repair"
            / scenario
            / "tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
        ),
        "normalized_architecture_off": (
            Path("results")
            / f"{design}_tritonpart_compatible_normalized_dynamic_convergence_architecture_off_guarded_repair"
            / scenario
            / "tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
        ),
    }


def case_output(design: str, scenario: str, delay: float) -> Path:
    return (
        Path("results")
        / "benchmark_summary"
        / f"{design}_{scenario}_normalized_dynamic_downstream_delay_{delay_tag(delay)}.csv"
    )


def run_case(design: str, scenario: str, delay: float, max_paths: int, force: bool) -> Path:
    output = case_output(design, scenario, delay)
    if output.exists() and not force:
        return output

    assignments = assignment_paths(design, scenario)
    cmd = [
        sys.executable,
        "evaluation/evaluate_path_aware_downstream_vertical_delay.py",
        "--design",
        design,
        "--scenario",
        scenario,
        "--timing-report",
        str(Path("results") / "timing_reports" / f"{design}_report_checks_max.rpt"),
        "--max-paths",
        str(max_paths),
        "--vertical-delay-ns",
        str(delay),
        "--output",
        str(output),
    ]
    for label, path in assignments.items():
        cmd.extend(["--assignment", f"{label}={path}"])

    print(" ".join(cmd))
    subprocess.run(cmd, check=True)
    return output


def summarize_output(path: Path) -> dict[str, dict[str, str]]:
    rows = read_csv(path)
    by_case = {row["case"]: row for row in rows}
    required = {"native_timing_aware", "normalized_architecture_on", "normalized_architecture_off"}
    missing = sorted(required - set(by_case))
    if missing:
        raise RuntimeError(f"{path} missing cases: {', '.join(missing)}")
    return by_case


def summary_row(design: str, scenario: str, delay: float, path: Path) -> dict[str, object]:
    by_case = summarize_output(path)
    native = by_case["native_timing_aware"]
    on = by_case["normalized_architecture_on"]
    off = by_case["normalized_architecture_off"]
    return {
        "vertical_delay_ns": f"{delay:.6f}",
        "design": design,
        "scenario": scenario,
        "native_crossing_path_fraction": native["crossing_path_fraction"],
        "on_crossing_path_fraction": on["crossing_path_fraction"],
        "off_crossing_path_fraction": off["crossing_path_fraction"],
        "on_crossing_path_fraction_delta_vs_native": delta(on["crossing_path_fraction"], native["crossing_path_fraction"]),
        "off_crossing_path_fraction_delta_vs_native": delta(off["crossing_path_fraction"], native["crossing_path_fraction"]),
        "native_mean_tier_transitions": native["mean_tier_transitions_per_path"],
        "on_mean_tier_transitions": on["mean_tier_transitions_per_path"],
        "off_mean_tier_transitions": off["mean_tier_transitions_per_path"],
        "on_mean_transition_reduction_vs_native": reduction(native["mean_tier_transitions_per_path"], on["mean_tier_transitions_per_path"]),
        "off_mean_transition_reduction_vs_native": reduction(native["mean_tier_transitions_per_path"], off["mean_tier_transitions_per_path"]),
        "native_max_tier_transitions": native["max_tier_transitions_on_path"],
        "on_max_tier_transitions": on["max_tier_transitions_on_path"],
        "off_max_tier_transitions": off["max_tier_transitions_on_path"],
        "native_wns_degradation": native["estimated_wns_degradation_ns"],
        "on_wns_degradation": on["estimated_wns_degradation_ns"],
        "off_wns_degradation": off["estimated_wns_degradation_ns"],
        "on_wns_degradation_reduction_vs_native": reduction(native["estimated_wns_degradation_ns"], on["estimated_wns_degradation_ns"]),
        "off_wns_degradation_reduction_vs_native": reduction(native["estimated_wns_degradation_ns"], off["estimated_wns_degradation_ns"]),
        "native_tns_degradation": native["estimated_tns_degradation_ns"],
        "on_tns_degradation": on["estimated_tns_degradation_ns"],
        "off_tns_degradation": off["estimated_tns_degradation_ns"],
        "on_tns_degradation_reduction_vs_native": reduction(native["estimated_tns_degradation_ns"], on["estimated_tns_degradation_ns"]),
        "off_tns_degradation_reduction_vs_native": reduction(native["estimated_tns_degradation_ns"], off["estimated_tns_degradation_ns"]),
        "case_csv": str(path),
    }


def mean(rows: list[dict[str, object]], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows) if rows else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", choices=DESIGNS, help="Design to include; repeatable.")
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, help="Scenario to include; repeatable.")
    parser.add_argument("--delay", type=float, action="append", help="Vertical delay value in ns; repeatable.")
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    designs = args.design or DESIGNS
    scenarios = args.scenario or SCENARIOS
    delays = args.delay or DEFAULT_DELAYS

    summary_rows: list[dict[str, object]] = []
    rollup_rows: list[dict[str, object]] = []

    for delay in delays:
        delay_rows: list[dict[str, object]] = []
        for design in designs:
            for scenario in scenarios:
                output = run_case(design, scenario, delay, args.max_paths, args.force)
                row = summary_row(design, scenario, delay, output)
                summary_rows.append(row)
                delay_rows.append(row)

        rollup_rows.append(
            {
                "vertical_delay_ns": f"{delay:.6f}",
                "cases": len(delay_rows),
                "mean_on_crossing_path_fraction_delta_vs_native": f"{mean(delay_rows, 'on_crossing_path_fraction_delta_vs_native'):.6f}",
                "mean_off_crossing_path_fraction_delta_vs_native": f"{mean(delay_rows, 'off_crossing_path_fraction_delta_vs_native'):.6f}",
                "mean_on_mean_transition_reduction_vs_native": f"{mean(delay_rows, 'on_mean_transition_reduction_vs_native'):.6f}",
                "mean_off_mean_transition_reduction_vs_native": f"{mean(delay_rows, 'off_mean_transition_reduction_vs_native'):.6f}",
                "mean_on_wns_degradation_reduction_vs_native": f"{mean(delay_rows, 'on_wns_degradation_reduction_vs_native'):.6f}",
                "mean_off_wns_degradation_reduction_vs_native": f"{mean(delay_rows, 'off_wns_degradation_reduction_vs_native'):.6f}",
                "mean_on_tns_degradation_reduction_vs_native": f"{mean(delay_rows, 'on_tns_degradation_reduction_vs_native'):.6f}",
                "mean_off_tns_degradation_reduction_vs_native": f"{mean(delay_rows, 'off_tns_degradation_reduction_vs_native'):.6f}",
            }
        )

    summary_fields = [
        "vertical_delay_ns",
        "design",
        "scenario",
        "native_crossing_path_fraction",
        "on_crossing_path_fraction",
        "off_crossing_path_fraction",
        "on_crossing_path_fraction_delta_vs_native",
        "off_crossing_path_fraction_delta_vs_native",
        "native_mean_tier_transitions",
        "on_mean_tier_transitions",
        "off_mean_tier_transitions",
        "on_mean_transition_reduction_vs_native",
        "off_mean_transition_reduction_vs_native",
        "native_max_tier_transitions",
        "on_max_tier_transitions",
        "off_max_tier_transitions",
        "native_wns_degradation",
        "on_wns_degradation",
        "off_wns_degradation",
        "on_wns_degradation_reduction_vs_native",
        "off_wns_degradation_reduction_vs_native",
        "native_tns_degradation",
        "on_tns_degradation",
        "off_tns_degradation",
        "on_tns_degradation_reduction_vs_native",
        "off_tns_degradation_reduction_vs_native",
        "case_csv",
    ]
    rollup_fields = [
        "vertical_delay_ns",
        "cases",
        "mean_on_crossing_path_fraction_delta_vs_native",
        "mean_off_crossing_path_fraction_delta_vs_native",
        "mean_on_mean_transition_reduction_vs_native",
        "mean_off_mean_transition_reduction_vs_native",
        "mean_on_wns_degradation_reduction_vs_native",
        "mean_off_wns_degradation_reduction_vs_native",
        "mean_on_tns_degradation_reduction_vs_native",
        "mean_off_tns_degradation_reduction_vs_native",
    ]

    write_csv(
        Path("results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_summary.csv"),
        summary_rows,
        summary_fields,
    )
    write_csv(
        Path("results/benchmark_summary/normalized_dynamic_downstream_delay_sweep_rollup.csv"),
        rollup_rows,
        rollup_fields,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
