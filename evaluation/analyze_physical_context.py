#!/usr/bin/env python3
"""Analyze whether physical context scores are meaningful.

This sanity analysis checks whether high-scoring instances are associated with
long nets, high fanout, or clock/reset exposure.  It does not alter partitioning.

Outputs:
  results/benchmark_summary/physical_context_top_instances.csv
  results/benchmark_summary/physical_context_unit_ranking.csv
  results/benchmark_summary/physical_context_score_buckets.csv
"""

from __future__ import annotations

import csv
from pathlib import Path


DESIGNS = ["ibex", "riscv32i"]
FEATURE_DIR = {
    "ibex": Path("results/ibex_features"),
    "riscv32i": Path("results/riscv32i_features"),
}
OUT_DIR = Path("results/benchmark_summary")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def f(row: dict[str, str], key: str) -> float:
    try:
        return float(row.get(key, "0") or 0)
    except ValueError:
        return 0.0


def bucket(score: float) -> str:
    if score >= 0.5:
        return "very_high"
    if score >= 0.35:
        return "high"
    if score >= 0.2:
        return "medium"
    if score >= 0.1:
        return "low"
    return "very_low"


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> int:
    top_rows: list[dict[str, object]] = []
    unit_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []

    for design in DESIGNS:
        rows = read_csv(FEATURE_DIR[design] / "physical_context_scores.csv")
        rows_sorted = sorted(rows, key=lambda r: f(r, "physical_context_score"), reverse=True)

        for rank, row in enumerate(rows_sorted[:30], start=1):
            top_rows.append(
                {
                    "design": design,
                    "rank": rank,
                    "instance": row["instance"],
                    "architecture_unit": row["architecture_unit"],
                    "physical_context_score": row["physical_context_score"],
                    "raw_physical_score": row["raw_physical_score"],
                    "physical_confidence_weight": row["physical_confidence_weight"],
                    "physical_observability_bucket": row["physical_observability_bucket"],
                    "placement_region": row["placement_region"],
                    "max_net_hpwl_um": row["max_net_hpwl_um"],
                    "total_net_hpwl_um": row["total_net_hpwl_um"],
                    "max_net_fanout": row["max_net_fanout"],
                    "clock_reset_net_count": row["clock_reset_net_count"],
                    "long_net_exposure_score": row["long_net_exposure_score"],
                    "fanout_exposure_score": row["fanout_exposure_score"],
                    "clock_reset_exposure_score": row["clock_reset_exposure_score"],
                }
            )

        by_unit: dict[str, list[dict[str, str]]] = {}
        by_bucket: dict[str, list[dict[str, str]]] = {}
        for row in rows:
            by_unit.setdefault(row["architecture_unit"], []).append(row)
            by_bucket.setdefault(bucket(f(row, "physical_context_score")), []).append(row)

        for unit, unit_rows_src in sorted(
            by_unit.items(),
            key=lambda kv: mean([f(r, "physical_context_score") for r in kv[1]]),
            reverse=True,
        ):
            scores = [f(r, "physical_context_score") for r in unit_rows_src]
            raw_scores = [f(r, "raw_physical_score") for r in unit_rows_src]
            long_scores = [f(r, "long_net_exposure_score") for r in unit_rows_src]
            fanout_scores = [f(r, "fanout_exposure_score") for r in unit_rows_src]
            clock_scores = [f(r, "clock_reset_exposure_score") for r in unit_rows_src]
            unit_rows.append(
                {
                    "design": design,
                    "architecture_unit": unit,
                    "instance_count": len(unit_rows_src),
                    "mean_physical_context_score": f"{mean(scores):.6f}",
                    "max_physical_context_score": f"{max(scores) if scores else 0.0:.6f}",
                    "mean_raw_physical_score": f"{mean(raw_scores):.6f}",
                    "mean_long_net_exposure_score": f"{mean(long_scores):.6f}",
                    "mean_fanout_exposure_score": f"{mean(fanout_scores):.6f}",
                    "mean_clock_reset_exposure_score": f"{mean(clock_scores):.6f}",
                    "very_high_score_instances": sum(1 for s in scores if s >= 0.5),
                    "high_or_above_score_instances": sum(1 for s in scores if s >= 0.35),
                }
            )

        for bkt, bkt_rows in sorted(by_bucket.items()):
            bucket_rows.append(
                {
                    "design": design,
                    "score_bucket": bkt,
                    "instance_count": len(bkt_rows),
                    "mean_max_net_hpwl_um": f"{mean([f(r, 'max_net_hpwl_um') for r in bkt_rows]):.3f}",
                    "mean_total_net_hpwl_um": f"{mean([f(r, 'total_net_hpwl_um') for r in bkt_rows]):.3f}",
                    "mean_max_net_fanout": f"{mean([f(r, 'max_net_fanout') for r in bkt_rows]):.3f}",
                    "mean_clock_reset_net_count": f"{mean([f(r, 'clock_reset_net_count') for r in bkt_rows]):.3f}",
                    "mean_long_net_exposure_score": f"{mean([f(r, 'long_net_exposure_score') for r in bkt_rows]):.6f}",
                    "mean_fanout_exposure_score": f"{mean([f(r, 'fanout_exposure_score') for r in bkt_rows]):.6f}",
                }
            )

    write_csv(
        OUT_DIR / "physical_context_top_instances.csv",
        top_rows,
        [
            "design",
            "rank",
            "instance",
            "architecture_unit",
            "physical_context_score",
            "raw_physical_score",
            "physical_confidence_weight",
            "physical_observability_bucket",
            "placement_region",
            "max_net_hpwl_um",
            "total_net_hpwl_um",
            "max_net_fanout",
            "clock_reset_net_count",
            "long_net_exposure_score",
            "fanout_exposure_score",
            "clock_reset_exposure_score",
        ],
    )
    write_csv(
        OUT_DIR / "physical_context_unit_ranking.csv",
        unit_rows,
        [
            "design",
            "architecture_unit",
            "instance_count",
            "mean_physical_context_score",
            "max_physical_context_score",
            "mean_raw_physical_score",
            "mean_long_net_exposure_score",
            "mean_fanout_exposure_score",
            "mean_clock_reset_exposure_score",
            "very_high_score_instances",
            "high_or_above_score_instances",
        ],
    )
    write_csv(
        OUT_DIR / "physical_context_score_buckets.csv",
        bucket_rows,
        [
            "design",
            "score_bucket",
            "instance_count",
            "mean_max_net_hpwl_um",
            "mean_total_net_hpwl_um",
            "mean_max_net_fanout",
            "mean_clock_reset_net_count",
            "mean_long_net_exposure_score",
            "mean_fanout_exposure_score",
        ],
    )

    print(OUT_DIR / "physical_context_top_instances.csv")
    print(OUT_DIR / "physical_context_unit_ranking.csv")
    print(OUT_DIR / "physical_context_score_buckets.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
