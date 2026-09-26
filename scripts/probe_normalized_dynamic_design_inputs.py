#!/usr/bin/env python3
"""Check required inputs for normalized dynamic convergence Phase-3 runs."""

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


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def present_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def present_dir(path: Path) -> bool:
    return path.is_dir()


def probe_design(root: Path, design: str, scenario: str) -> dict[str, object]:
    native = root / "results" / f"{design}_tritonpart_design_timing_aware" / "tritonpart_design_timing_aware_assignment.csv"
    features = root / "results" / f"{design}_features"
    feature_table = features / "instance_features.csv"
    timing_context = features / "timing_context_scores.csv"
    timing_report = root / "results" / "timing_reports" / f"{design}_report_checks_max.rpt"
    area = root / "results" / "benchmark_summary" / f"{design}_openroad_instance_area.csv"
    missing = []
    checks = {
        "native_assignment": present_file(native),
        "features_dir": present_dir(features),
        "instance_features": present_file(feature_table),
        "timing_context": present_file(timing_context),
        "timing_report": present_file(timing_report),
        "openroad_area": present_file(area),
    }
    for name, ok in checks.items():
        if not ok:
            missing.append(name)
    return {
        "design": design,
        "scenario": scenario,
        "ready": str(not missing).lower(),
        **{name: str(ok).lower() for name, ok in checks.items()},
        "missing": ";".join(missing),
        "native_assignment_path": str(native),
        "features_dir_path": str(features),
        "timing_report_path": str(timing_report),
        "openroad_area_path": str(area),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/benchmark_summary/normalized_dynamic_phase3_input_probe.csv"),
    )
    args = parser.parse_args()

    designs = args.designs or DEFAULT_DESIGNS
    scenarios = args.scenarios or DEFAULT_SCENARIOS
    rows = [probe_design(args.root, design, scenario) for design in designs for scenario in scenarios]
    write_csv(args.root / args.output, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
