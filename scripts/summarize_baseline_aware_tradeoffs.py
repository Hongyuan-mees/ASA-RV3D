
#!/usr/bin/env python3
"""Summarize tradeoffs against native TritonPart timing-aware baseline.

This script is deliberately conservative. It does not rerun partitioning and it
does not claim that one method dominates all objectives. It consolidates the
current comparable evidence:

- TritonPart hypergraph baseline
- OpenROAD native `triton_part_design -timing_aware_flag` baseline, where it
  runs and can be imported into RV3D instance space
- ASA-RV3D timing-regret guarded repair

The output is meant to support paper/README calibration after the native
timing-aware baseline became available for several designs.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import mean


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def by_key(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in rows if row.get(key)}


def fnum(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def reduction(new_value: float | None, old_value: float | None) -> float | None:
    if new_value is None or old_value in (None, 0.0):
        return None
    return (old_value - new_value) / old_value


def fmt(value: float | None) -> str:
    return "" if value is None else f"{value:.6f}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline-summary",
        type=Path,
        default=Path(
            "results/benchmark_summary/tritonpart_design_timing_aware_baseline_summary.csv"
        ),
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=Path("results/benchmark_summary/baseline_aware_tradeoff_summary.csv"),
    )
    parser.add_argument(
        "--output-rollup",
        type=Path,
        default=Path("results/benchmark_summary/baseline_aware_tradeoff_rollup.csv"),
    )
    args = parser.parse_args()

    baseline_rows = by_key(read_rows(args.baseline_summary), "design")
    summary: list[dict[str, str]] = []

    for design in DESIGNS:
        baseline = baseline_rows.get(design, {})
        crossing_csv = baseline.get("crossing_csv") or (
            f"results/benchmark_summary/{design}_tritonpart_design_timing_aware_crossing.csv"
        )
        crossing_path = Path(crossing_csv)
        crossing_rows = by_key(read_rows(crossing_path), "case") if crossing_path.is_file() else {}

        hyper = crossing_rows.get("tritonpart_hypergraph", {})
        native = crossing_rows.get("tritonpart_design_timing_aware", {})
        asa = crossing_rows.get("asa_rv3d", {})

        hyper_tw = fnum(hyper.get("timing_weighted_crossing"))
        native_tw = fnum(native.get("timing_weighted_crossing"))
        asa_tw = fnum(asa.get("timing_weighted_crossing"))

        hyper_frac = fnum(hyper.get("timing_crossing_net_fraction"))
        native_frac = fnum(native.get("timing_crossing_net_fraction"))
        asa_frac = fnum(asa.get("timing_crossing_net_fraction"))

        fallback = fnum(baseline.get("import_fallback_rows"))
        reference_rows = fnum(baseline.get("import_reference_rows"))
        fallback_fraction = (
            fallback / reference_rows
            if fallback is not None and reference_rows not in (None, 0.0)
            else None
        )

        native_vs_hyper = reduction(native_tw, hyper_tw)
        asa_vs_hyper = reduction(asa_tw, hyper_tw)
        native_vs_asa = reduction(native_tw, asa_tw)
        asa_frac_vs_native = reduction(asa_frac, native_frac)

        if native_tw is None:
            interpretation = "native_timing_aware_not_comparable"
        elif asa_tw is None:
            interpretation = "asa_not_comparable"
        elif native_tw < asa_tw and asa_frac is not None and native_frac is not None and asa_frac < native_frac:
            interpretation = "native_better_timing_weighted_asa_better_crossing_fraction"
        elif native_tw < asa_tw:
            interpretation = "native_better_timing_weighted"
        elif asa_tw < native_tw:
            interpretation = "asa_better_timing_weighted"
        else:
            interpretation = "tie"

        summary.append(
            {
                "design": design,
                "native_timing_aware_status": baseline.get("native_timing_aware_status", ""),
                "native_return_code": baseline.get("return_code", ""),
                "import_fallback_rows": baseline.get("import_fallback_rows", ""),
                "import_fallback_fraction": fmt(fallback_fraction),
                "hypergraph_timing_weighted_crossing": fmt(hyper_tw),
                "native_timing_weighted_crossing": fmt(native_tw),
                "asa_timing_weighted_crossing": fmt(asa_tw),
                "native_reduction_vs_hypergraph": fmt(native_vs_hyper),
                "asa_reduction_vs_hypergraph": fmt(asa_vs_hyper),
                "native_reduction_vs_asa": fmt(native_vs_asa),
                "hypergraph_timing_crossing_net_fraction": fmt(hyper_frac),
                "native_timing_crossing_net_fraction": fmt(native_frac),
                "asa_timing_crossing_net_fraction": fmt(asa_frac),
                "asa_crossing_fraction_reduction_vs_native": fmt(asa_frac_vs_native),
                "native_crossing_nets": native.get("crossing_nets", ""),
                "asa_crossing_nets": asa.get("crossing_nets", ""),
                "interpretation": interpretation,
            }
        )

    comparable = [
        row
        for row in summary
        if row["native_timing_weighted_crossing"] and row["asa_timing_weighted_crossing"]
    ]
    native_better_tw = [
        row
        for row in comparable
        if float(row["native_timing_weighted_crossing"])
        < float(row["asa_timing_weighted_crossing"])
    ]
    asa_better_frac = [
        row
        for row in comparable
        if row["native_timing_crossing_net_fraction"]
        and row["asa_timing_crossing_net_fraction"]
        and float(row["asa_timing_crossing_net_fraction"])
        < float(row["native_timing_crossing_net_fraction"])
    ]

    native_vs_asa_values = [
        float(row["native_reduction_vs_asa"])
        for row in comparable
        if row["native_reduction_vs_asa"]
    ]
    asa_frac_vs_native_values = [
        float(row["asa_crossing_fraction_reduction_vs_native"])
        for row in comparable
        if row["asa_crossing_fraction_reduction_vs_native"]
    ]

    rollup = [
        {"metric": "designs", "value": ",".join(DESIGNS)},
        {"metric": "comparable_cases", "value": str(len(comparable))},
        {
            "metric": "native_better_timing_weighted_than_asa_cases",
            "value": str(len(native_better_tw)),
        },
        {
            "metric": "asa_better_timing_crossing_fraction_than_native_cases",
            "value": str(len(asa_better_frac)),
        },
        {
            "metric": "mean_native_reduction_vs_asa_timing_weighted",
            "value": fmt(mean(native_vs_asa_values) if native_vs_asa_values else None),
        },
        {
            "metric": "mean_asa_crossing_fraction_reduction_vs_native",
            "value": fmt(mean(asa_frac_vs_native_values) if asa_frac_vs_native_values else None),
        },
    ]

    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    with args.output_summary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary[0].keys()))
        writer.writeheader()
        writer.writerows(summary)

    with args.output_rollup.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(rollup)

    print(args.output_summary)
    print(args.output_rollup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
