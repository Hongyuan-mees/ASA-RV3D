#!/usr/bin/env python3
"""Evaluate cut-regret replay assignments for ASA-on-native Phase 1."""

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
    parser.add_argument("--design", default="riscv32i")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument(
        "--replay-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_summary.csv"),
    )
    parser.add_argument(
        "--native-assignment",
        type=Path,
        default=Path("results/riscv32i_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"),
    )
    parser.add_argument(
        "--timing-report",
        type=Path,
        default=Path("results/timing_reports/riscv32i_report_checks_max.rpt"),
    )
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=Path("results/riscv32i_features"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_eval.csv"),
    )
    parser.add_argument("--max-paths", type=int, default=100)
    args = parser.parse_args()

    replay_rows = read_csv(args.replay_summary)
    assignments: list[tuple[str, Path]] = [("native_timing_aware", args.native_assignment)]
    for row in replay_rows:
        label = f"cut_regret_{row['cut_regret_budget'].replace('.', 'p')}"
        assignments.append((label, Path(row["assignment_file"])))

    timing_out = Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_timing_crossing.csv")
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

    path_out = Path("results/benchmark_summary/asa_on_native_riscv32i_cut_regret_replay_path_cuts.csv")
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
    path_cuts = by_key(read_csv(path_out), "case")
    replay_by_label = {
        f"cut_regret_{row['cut_regret_budget'].replace('.', 'p')}": row
        for row in replay_rows
    }
    native_timing = timing["native_timing_aware"]
    native_paths = path_cuts["native_timing_aware"]
    native_tw = f(native_timing.get("timing_weighted_crossing"))
    native_pavg = f(native_paths.get("P_avg_cut"))
    native_pwst = f(native_paths.get("P_wst_cut"))

    out_rows: list[dict[str, object]] = []
    for label, assignment in assignments:
        trow = timing[label]
        prow = path_cuts[label]
        replay = replay_by_label.get(label, {})
        tw = f(trow.get("timing_weighted_crossing"))
        pavg = f(prow.get("P_avg_cut"))
        pwst = f(prow.get("P_wst_cut"))
        out_rows.append(
            {
                "design": args.design,
                "scenario": args.scenario,
                "case": label,
                "assignment_file": str(assignment),
                "selected_move_index": replay.get("selected_move_index", "0"),
                "selected_cut_regret": replay.get("selected_cut_regret", "0.000000"),
                "selected_crossing_nets": replay.get("selected_crossing_nets", trow.get("crossing_nets", "")),
                "timing_weighted_crossing": trow.get("timing_weighted_crossing", ""),
                "timing_weighted_regret_vs_native": frac_delta(tw, native_tw),
                "timing_crossing_net_fraction": trow.get("timing_crossing_net_fraction", ""),
                "high_timing_crossing_nets": trow.get("high_timing_crossing_nets", ""),
                "P_avg_cut": prow.get("P_avg_cut", ""),
                "P_avg_cut_regret_vs_native": frac_delta(pavg, native_pavg),
                "P_wst_cut": prow.get("P_wst_cut", ""),
                "P_wst_cut_delta_vs_native": "" if pwst is None or native_pwst is None else f"{pwst - native_pwst:.6f}",
                "cut_path_fraction": prow.get("cut_path_fraction", ""),
                "cumulative_gain": replay.get("cumulative_gain", "0.000000"),
                "cumulative_scenario_gain": replay.get("cumulative_scenario_gain", "0.000000"),
                "cumulative_physical_gain": replay.get("cumulative_physical_gain", "0.000000"),
                "cumulative_timing_gain": replay.get("cumulative_timing_gain", "0.000000"),
            }
        )

    write_csv(args.output, out_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
