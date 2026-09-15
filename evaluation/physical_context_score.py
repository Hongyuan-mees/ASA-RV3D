#!/usr/bin/env python3
"""Compute coverage-aware physical context scores.

This is the next physical-aware ASA-RV3D layer after DEF matching diagnosis and
physical coverage summarization.  It does not change tier assignments.  It
creates per-instance physical scores that can later be used by a partitioner.

Core idea:

  physical_context_score =
      physical_confidence_weight
      * (locality/spread + long-net exposure + fanout exposure)

Units with poor DEF observability are gated by a low confidence weight, so their
missing coordinates do not create false physical evidence.

Outputs:
  results/<design>_features/physical_context_scores.csv
  results/<design>_features/physical_context_summary.csv
  results/<design>_features/physical_context_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


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


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def f(row: dict[str, str], key: str, default: float = 0.0) -> float:
    try:
        raw = row.get(key, "")
        if raw == "":
            return default
        return float(raw)
    except ValueError:
        return default


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--coverage-summary", type=Path, default=Path("results/benchmark_summary/physical_coverage_summary.csv"))
    args = parser.parse_args()

    features_dir = (args.features_dir or Path("results") / f"{args.design}_features").resolve()
    physical_rows = read_csv(features_dir / "physical_instance_features.csv")
    coverage_rows = read_csv(args.coverage_summary)
    coverage = {
        row["architecture_unit"]: row
        for row in coverage_rows
        if row["design"] == args.design
    }
    if not coverage:
        raise RuntimeError(f"No coverage rows found for design {args.design}")

    max_hpwl = max((f(row, "max_net_hpwl_um") for row in physical_rows), default=0.0)
    max_total_hpwl = max((f(row, "total_net_hpwl_um") for row in physical_rows), default=0.0)
    max_fanout = max((f(row, "max_net_fanout") for row in physical_rows), default=0.0)
    max_long_count = max((f(row, "long_net_count_p75") for row in physical_rows), default=0.0)
    max_very_long_count = max((f(row, "very_long_net_count_p90") for row in physical_rows), default=0.0)

    scored_rows: list[dict[str, object]] = []
    by_unit: dict[str, list[dict[str, object]]] = defaultdict(list)

    for row in physical_rows:
        unit = row["architecture_unit"]
        cov = coverage.get(unit, {})
        confidence = float(cov.get("physical_confidence_weight", "0.1") or 0.1)
        bucket = cov.get("physical_observability_bucket", "unknown")
        recommendation = cov.get("physical_scoring_recommendation", "unknown")

        placed = int(float(row.get("placed", "0") or 0))
        mean_hpwl = f(row, "mean_net_hpwl_um")
        max_row_hpwl = f(row, "max_net_hpwl_um")
        total_hpwl = f(row, "total_net_hpwl_um")
        max_row_fanout = f(row, "max_net_fanout")
        high_fanout_count = f(row, "high_fanout_net_count")
        long_count = f(row, "long_net_count_p75")
        very_long_count = f(row, "very_long_net_count_p90")
        clock_reset_count = f(row, "clock_reset_net_count")

        long_net_exposure = 0.50 * clamp01(max_row_hpwl / max_hpwl if max_hpwl else 0.0)
        long_net_exposure += 0.30 * clamp01(total_hpwl / max_total_hpwl if max_total_hpwl else 0.0)
        long_net_exposure += 0.20 * clamp01(very_long_count / max_very_long_count if max_very_long_count else 0.0)
        long_net_exposure = clamp01(long_net_exposure)

        fanout_exposure = 0.65 * clamp01(max_row_fanout / max_fanout if max_fanout else 0.0)
        fanout_exposure += 0.35 * clamp01(high_fanout_count / max_long_count if max_long_count else 0.0)
        fanout_exposure = clamp01(fanout_exposure)

        locality_risk = 0.60 * long_net_exposure + 0.40 * fanout_exposure
        clock_reset_exposure = clamp01(clock_reset_count / max(1.0, f(row, "net_count", 1.0)))

        raw_physical_score = 0.70 * locality_risk + 0.20 * clock_reset_exposure + 0.10 * (1.0 if placed else 0.0)
        physical_context_score = confidence * raw_physical_score

        out = {
            "instance": row["instance"],
            "architecture_unit": unit,
            "physical_observability_bucket": bucket,
            "physical_confidence_weight": f"{confidence:.3f}",
            "physical_scoring_recommendation": recommendation,
            "placed": placed,
            "placement_region": row["placement_region"],
            "mean_net_hpwl_um": f"{mean_hpwl:.3f}",
            "max_net_hpwl_um": f"{max_row_hpwl:.3f}",
            "total_net_hpwl_um": f"{total_hpwl:.3f}",
            "max_net_fanout": f"{max_row_fanout:.0f}",
            "clock_reset_net_count": f"{clock_reset_count:.0f}",
            "long_net_exposure_score": f"{long_net_exposure:.6f}",
            "fanout_exposure_score": f"{fanout_exposure:.6f}",
            "clock_reset_exposure_score": f"{clock_reset_exposure:.6f}",
            "raw_physical_score": f"{raw_physical_score:.6f}",
            "physical_context_score": f"{physical_context_score:.6f}",
        }
        scored_rows.append(out)
        by_unit[unit].append(out)

    summary_rows: list[dict[str, object]] = []
    for unit, rows in sorted(by_unit.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        scores = [float(r["physical_context_score"]) for r in rows]
        raw_scores = [float(r["raw_physical_score"]) for r in rows]
        long_scores = [float(r["long_net_exposure_score"]) for r in rows]
        fanout_scores = [float(r["fanout_exposure_score"]) for r in rows]
        placed_count = sum(int(r["placed"]) for r in rows)
        high_score_count = sum(1 for s in scores if s >= 0.5)
        summary_rows.append(
            {
                "design": args.design,
                "architecture_unit": unit,
                "instance_count": len(rows),
                "placed_fraction": f"{placed_count / len(rows) if rows else 0.0:.6f}",
                "physical_observability_bucket": rows[0]["physical_observability_bucket"],
                "physical_confidence_weight": rows[0]["physical_confidence_weight"],
                "mean_raw_physical_score": f"{sum(raw_scores) / len(raw_scores) if raw_scores else 0.0:.6f}",
                "mean_physical_context_score": f"{sum(scores) / len(scores) if scores else 0.0:.6f}",
                "max_physical_context_score": f"{max(scores) if scores else 0.0:.6f}",
                "mean_long_net_exposure_score": f"{sum(long_scores) / len(long_scores) if long_scores else 0.0:.6f}",
                "mean_fanout_exposure_score": f"{sum(fanout_scores) / len(fanout_scores) if fanout_scores else 0.0:.6f}",
                "high_physical_score_instances": high_score_count,
            }
        )

    score_fields = [
        "instance",
        "architecture_unit",
        "physical_observability_bucket",
        "physical_confidence_weight",
        "physical_scoring_recommendation",
        "placed",
        "placement_region",
        "mean_net_hpwl_um",
        "max_net_hpwl_um",
        "total_net_hpwl_um",
        "max_net_fanout",
        "clock_reset_net_count",
        "long_net_exposure_score",
        "fanout_exposure_score",
        "clock_reset_exposure_score",
        "raw_physical_score",
        "physical_context_score",
    ]
    summary_fields = [
        "design",
        "architecture_unit",
        "instance_count",
        "placed_fraction",
        "physical_observability_bucket",
        "physical_confidence_weight",
        "mean_raw_physical_score",
        "mean_physical_context_score",
        "max_physical_context_score",
        "mean_long_net_exposure_score",
        "mean_fanout_exposure_score",
        "high_physical_score_instances",
    ]

    score_path = features_dir / "physical_context_scores.csv"
    summary_path = features_dir / "physical_context_summary.csv"
    manifest_path = features_dir / "physical_context_manifest.json"

    write_csv(score_path, scored_rows, score_fields)
    write_csv(summary_path, summary_rows, summary_fields)
    manifest = {
        "design": args.design,
        "features_dir": str(features_dir),
        "coverage_summary": str(args.coverage_summary),
        "instance_count": len(scored_rows),
        "unit_count": len(summary_rows),
        "max_hpwl_um": round(max_hpwl, 3),
        "max_total_hpwl_um": round(max_total_hpwl, 3),
        "max_fanout": round(max_fanout, 3),
        "outputs": [str(score_path), str(summary_path), str(manifest_path)],
        "note": "Scores are coverage-gated physical proxies and are not yet used for partitioning.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(score_path)
    print(summary_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
