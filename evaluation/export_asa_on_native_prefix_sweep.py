#!/usr/bin/env python3
"""Export ASA-on-native replay assignments at selected trace prefixes."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def normalize_name(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        name = name[1:]
    return name


def as_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def assignment_rows_at_prefix(
    initial_rows: list[dict[str, str]],
    trace_rows: list[dict[str, str]],
    prefix: int,
) -> tuple[list[dict[str, str]], dict[str, float]]:
    tier = {normalize_name(row["instance"]): row["tier"] for row in initial_rows}
    cumulative = {
        "gain": 0.0,
        "scenario_gain": 0.0,
        "physical_gain": 0.0,
        "timing_gain": 0.0,
    }
    applied = 0
    for row in trace_rows:
        move_index = int(row.get("move_index", "0") or "0")
        if move_index > prefix:
            break
        inst = normalize_name(row["instance"])
        if inst not in tier:
            continue
        to_tier = row.get("to_tier", "")
        if to_tier not in {"tier0", "tier1"}:
            raise RuntimeError(f"Unexpected to_tier for {inst}: {to_tier}")
        tier[inst] = to_tier
        applied = max(applied, move_index)
        for key in cumulative:
            cumulative[key] += as_float(row.get(key))

    out_rows: list[dict[str, str]] = []
    for row in initial_rows:
        out = dict(row)
        out["tier"] = tier[normalize_name(row["instance"])]
        out_rows.append(out)
    cumulative["applied_prefix"] = float(applied)
    return out_rows, cumulative


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", default="picorv32")
    parser.add_argument("--scenario", default="state_and_clock_protected")
    parser.add_argument(
        "--initial-assignment",
        type=Path,
        default=Path("results/picorv32_tritonpart_design_timing_aware/tritonpart_design_timing_aware_assignment.csv"),
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("results/picorv32_timing_aware_start_asa/state_and_clock_protected/local_refinement_trace.csv"),
    )
    parser.add_argument("--prefix", type=int, action="append", default=[5, 10, 15, 20, 23, 25, 26, 27])
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/picorv32_asa_on_native_prefix_sweep/state_and_clock_protected"),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/asa_on_native_picorv32_state_and_clock_protected_prefix_sweep.csv"),
    )
    args = parser.parse_args()

    initial_rows = read_csv(args.initial_assignment)
    trace_rows = read_csv(args.trace)
    fieldnames = list(initial_rows[0].keys())

    summary: list[dict[str, object]] = []
    for prefix in args.prefix:
        rows, cumulative = assignment_rows_at_prefix(initial_rows, trace_rows, prefix)
        assignment = args.output_dir / f"prefix_{prefix:03d}_assignment.csv"
        write_csv(assignment, rows, fieldnames)
        summary.append(
            {
                "design": args.design,
                "scenario": args.scenario,
                "prefix": prefix,
                "applied_prefix": int(cumulative["applied_prefix"]),
                "cumulative_gain": f"{cumulative['gain']:.6f}",
                "cumulative_scenario_gain": f"{cumulative['scenario_gain']:.6f}",
                "cumulative_physical_gain": f"{cumulative['physical_gain']:.6f}",
                "cumulative_timing_gain": f"{cumulative['timing_gain']:.6f}",
                "assignment_file": str(assignment),
            }
        )

    write_csv(args.output_summary, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

