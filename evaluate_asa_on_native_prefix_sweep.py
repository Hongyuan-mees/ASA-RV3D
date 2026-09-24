#!/usr/bin/env python3
"""Evaluate ASA-on-native prefix-sweep assignments.

This keeps the prefix sweep separate from the cut-regret replay.  Prefix labels
are useful for finding the last area-feasible point in a repair trace, then
checking whether that point also preserves timing/cut/path quality.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
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


def by_key(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows if row.get(key)}


def f(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def frac_delta(new: float | None, old: float | None) -> str:
    if new is None or old in (None, 0.0):
        return ""
    return f"{(new - old) / old:.6f}"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", default="picorv32")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument(
        "--prefix-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_area_sweep.csv"),
    )
    parser.add_argument(
        "--native-assignment",
        type=Path,
        default=Path("results/picorv32_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"),
    )
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=Path("results/picorv32_features"),
    )
    parser.add_argument(
        "--timing-report",
        type=Path,
        default=Path("results/timing_reports/picorv32_report_checks_max.rpt"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_eval.csv"),
    )
    parser.add_argument("--max-paths", type=int, default=100)
    args = parser.parse_args()

    prefix_rows = read_csv(args.prefix_summary)
    assignments: list[tuple[str, Path]] = [("native_timing_aware", args.native_assignment)]
    for row in prefix_rows:
        label = f"prefix_{int(row['prefix']):03d}"
        assignments.append((label, Path(row["assignment_file"])))

    out_prefix = f"asa_on_native_{args.design}_{args.scenario}_prefix"
    timing_out = Path("results/benchmark_summary") / f"{out_prefix}_timing_crossing.csv"
    timing_cmd = [
        sys.executable,
        "evaluation/evaluate_timing_crossing.py",
        "--design",
        args.design,
        "--features-dir",
        str(args.features_dir),
        "--timing",
        str(args.features_dir / "timing_context_scores.csv"),
    ]
    for label, path in assignments:
        timing_cmd.extend(["--assignment", f"{label}={path}"])
    timing_cmd.extend(["--output", str(timing_out)])
    run(timing_cmd)

    path_out = Path("results/benchmark_summary") / f"{out_prefix}_path_cuts.csv"
    path_cmd = [
        sys.executable,
        "evaluate_timing_path_cuts.py",
        "--design",
        args.design,
        "--timing-report",
        str(args.timing_report),
        "--max-paths",
        str(args.max_paths),
    ]
    for label, path in assignments:
        path_cmd.extend(["--assignment", f"{label}={path}"])
    path_cmd.extend(["--output", str(path_out)])
    run(path_cmd)

    timing = by_key(read_csv(timing_out), "case")
    paths = by_key(read_csv(path_out), "case")
    prefix_by_label = {f"prefix_{int(row['prefix']):03d}": row for row in prefix_rows}

    native_timing = timing["native_timing_aware"]
    native_paths = paths["native_timing_aware"]
    native_tw = f(native_timing.get("timing_weighted_crossing"))
    native_cross = f(native_timing.get("crossing_nets"))
    native_pavg = f(native_paths.get("P_avg_cut"))
    native_pwst = f(native_paths.get("P_wst_cut"))

    out_rows: list[dict[str, object]] = []
    for label, assignment in assignments:
        trow = timing[label]
        prow = paths[label]
        prefix = prefix_by_label.get(label, {})
        tw = f(trow.get("timing_weighted_crossing"))
        crossing = f(trow.get("crossing_nets"))
        pavg = f(prow.get("P_avg_cut"))
        pwst = f(prow.get("P_wst_cut"))
        out_rows.append(
            {
                "design": args.design,
                "scenario": args.scenario,
                "case": label,
                "assignment_file": str(assignment),
                "area_balance_pass": prefix.get("area_balance_pass", "true" if label == "native_timing_aware" else ""),
                "area_weight_balance": prefix.get("area_weight_balance", ""),
                "tier0_area_fraction": prefix.get("tier0_area_fraction", ""),
                "tier1_area_fraction": prefix.get("tier1_area_fraction", ""),
                "cumulative_scenario_gain": prefix.get("cumulative_scenario_gain", "0.000000"),
                "cumulative_physical_gain": prefix.get("cumulative_physical_gain", "0.000000"),
                "cumulative_timing_gain": prefix.get("cumulative_timing_gain", "0.000000"),
                "crossing_nets": trow.get("crossing_nets", ""),
                "crossing_regret_vs_native": frac_delta(crossing, native_cross),
                "timing_weighted_crossing": trow.get("timing_weighted_crossing", ""),
                "timing_weighted_regret_vs_native": frac_delta(tw, native_tw),
                "timing_crossing_net_fraction": trow.get("timing_crossing_net_fraction", ""),
                "high_timing_crossing_nets": trow.get("high_timing_crossing_nets", ""),
                "P_avg_cut": prow.get("P_avg_cut", ""),
                "P_avg_cut_regret_vs_native": frac_delta(pavg, native_pavg),
                "P_wst_cut": prow.get("P_wst_cut", ""),
                "P_wst_cut_delta_vs_native": "" if pwst is None or native_pwst is None else f"{pwst - native_pwst:.6f}",
                "cut_path_fraction": prow.get("cut_path_fraction", ""),
            }
        )

    write_csv(args.output, out_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

