#!/usr/bin/env python3
"""Summarize physical observability for architecture units.

This script turns DEF matching / physical feature extraction into a confidence
layer for future physical-aware scoring.

It answers:

  Which architecture units have reliable physical observations?
  Which units should be gated or down-weighted in physical-aware scoring?

Outputs:
  results/benchmark_summary/physical_coverage_summary.csv
  results/benchmark_summary/physical_coverage_recommendations.csv
"""

from __future__ import annotations

import csv
from pathlib import Path


OUT_DIR = Path("results/benchmark_summary")


def discover_feature_dirs() -> dict[str, Path]:
    feature_dirs: dict[str, Path] = {}
    for path in sorted(Path("results").glob("*_features/physical_unit_summary.csv")):
        feature_dir = path.parent
        design = feature_dir.name.removesuffix("_features")
        matching = feature_dir / "def_matching_unmatched_by_unit.csv"
        if matching.exists():
            feature_dirs[design] = feature_dir
    return feature_dirs


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


def confidence_bucket(placed_fraction: float, instance_count: int) -> tuple[str, float, str]:
    """Return bucket, numeric weight, and recommendation."""

    if instance_count < 10:
        return "small_sample", 0.25, "diagnostic_only"
    if placed_fraction >= 0.90:
        return "high", 1.00, "use_physical_features"
    if placed_fraction >= 0.70:
        return "medium", 0.70, "use_with_confidence_weight"
    if placed_fraction >= 0.40:
        return "low", 0.35, "use_only_for_diagnostics"
    return "very_low", 0.10, "do_not_use_for_physical_scoring"


def main() -> int:
    coverage_rows: list[dict[str, object]] = []
    recommendation_rows: list[dict[str, object]] = []

    feature_dirs = discover_feature_dirs()
    if not feature_dirs:
        raise RuntimeError("No feature directories with physical_unit_summary.csv were found.")

    for design, feature_dir in feature_dirs.items():
        unit_rows = read_csv(feature_dir / "physical_unit_summary.csv")
        matching_rows = read_csv(feature_dir / "def_matching_unmatched_by_unit.csv")
        matching_by_unit = {row["architecture_unit"]: row for row in matching_rows}

        for row in unit_rows:
            unit = row["architecture_unit"]
            instance_count = int(row["instance_count"])
            placed_fraction = float(row["placed_fraction"])
            unmatched_fraction = float(matching_by_unit.get(unit, {}).get("unmatched_fraction", 1.0))
            bucket, weight, recommendation = confidence_bucket(placed_fraction, instance_count)

            coverage_rows.append(
                {
                    "design": design,
                    "architecture_unit": unit,
                    "instance_count": instance_count,
                    "placed_fraction": f"{placed_fraction:.6f}",
                    "unmatched_fraction": f"{unmatched_fraction:.6f}",
                    "physical_observability_bucket": bucket,
                    "physical_confidence_weight": f"{weight:.3f}",
                    "physical_scoring_recommendation": recommendation,
                    "mean_norm_x": row["mean_norm_x"],
                    "mean_norm_y": row["mean_norm_y"],
                    "top_region": row["top_region"],
                    "top_region_fraction": row["top_region_fraction"],
                    "mean_net_hpwl_um": row["mean_net_hpwl_um"],
                    "mean_max_net_hpwl_um": row["mean_max_net_hpwl_um"],
                    "clock_reset_net_count": row["clock_reset_net_count"],
                    "long_net_count_p75": row["long_net_count_p75"],
                    "very_long_net_count_p90": row["very_long_net_count_p90"],
                }
            )

        total_units = len(unit_rows)
        high = sum(1 for r in coverage_rows if r["design"] == design and r["physical_observability_bucket"] == "high")
        medium = sum(1 for r in coverage_rows if r["design"] == design and r["physical_observability_bucket"] == "medium")
        low_or_worse = sum(
            1
            for r in coverage_rows
            if r["design"] == design and r["physical_observability_bucket"] in {"low", "very_low", "small_sample"}
        )
        weighted_instances = sum(
            int(r["instance_count"]) * float(r["physical_confidence_weight"])
            for r in coverage_rows
            if r["design"] == design
        )
        total_instances = sum(int(r["instance_count"]) for r in coverage_rows if r["design"] == design)

        recommendation_rows.append(
            {
                "design": design,
                "architecture_unit_count": total_units,
                "high_confidence_units": high,
                "medium_confidence_units": medium,
                "low_or_gated_units": low_or_worse,
                "total_instances": total_instances,
                "confidence_weighted_instance_coverage": f"{weighted_instances / total_instances if total_instances else 0.0:.6f}",
                "recommendation": "use_coverage_gated_physical_scoring",
            }
        )

    write_csv(
        OUT_DIR / "physical_coverage_summary.csv",
        coverage_rows,
        [
            "design",
            "architecture_unit",
            "instance_count",
            "placed_fraction",
            "unmatched_fraction",
            "physical_observability_bucket",
            "physical_confidence_weight",
            "physical_scoring_recommendation",
            "mean_norm_x",
            "mean_norm_y",
            "top_region",
            "top_region_fraction",
            "mean_net_hpwl_um",
            "mean_max_net_hpwl_um",
            "clock_reset_net_count",
            "long_net_count_p75",
            "very_long_net_count_p90",
        ],
    )
    write_csv(
        OUT_DIR / "physical_coverage_recommendations.csv",
        recommendation_rows,
        [
            "design",
            "architecture_unit_count",
            "high_confidence_units",
            "medium_confidence_units",
            "low_or_gated_units",
            "total_instances",
            "confidence_weighted_instance_coverage",
            "recommendation",
        ],
    )
    print(OUT_DIR / "physical_coverage_summary.csv")
    print(OUT_DIR / "physical_coverage_recommendations.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
