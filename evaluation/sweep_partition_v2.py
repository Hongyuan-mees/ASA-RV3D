#!/usr/bin/env python3
"""Run a small parameter sweep for the score-based partition v2 heuristic."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from types import SimpleNamespace


def add_repo_root_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))


add_repo_root_to_path()

from partition.partition_v2 import run  # noqa: E402


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_comparison(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["strategy"]: row for row in csv.DictReader(handle)}


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, default=Path("results") / "ibex_features")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "partition_v2_sweep")
    parser.add_argument("--architecture-weights", default="0.1,0.2,0.4,0.8")
    parser.add_argument("--min-weight-balances", default="0.90,0.95,0.98")
    parser.add_argument("--crossing-weight", type=float, default=1.0)
    parser.add_argument("--instance-balance-weight", type=float, default=0.4)
    parser.add_argument("--weight-balance-weight", type=float, default=0.02)
    parser.add_argument("--max-passes", type=int, default=4)
    parser.add_argument("--max-moves-per-pass", type=int, default=4000)
    parser.add_argument("--min-gain", type=float, default=0.001)
    parser.add_argument("--min-instance-balance", type=float, default=0.80)
    args = parser.parse_args()

    features_dir = args.features_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    architecture_weights = parse_float_list(args.architecture_weights)
    min_weight_balances = parse_float_list(args.min_weight_balances)

    for arch_weight in architecture_weights:
        for min_weight_balance in min_weight_balances:
            run_name = f"arch{arch_weight:g}_wb{min_weight_balance:g}".replace(".", "p")
            run_dir = output_dir / run_name
            run_args = SimpleNamespace(
                features_dir=features_dir,
                output_dir=run_dir,
                crossing_weight=args.crossing_weight,
                instance_balance_weight=args.instance_balance_weight,
                weight_balance_weight=args.weight_balance_weight,
                architecture_weight=arch_weight,
                max_passes=args.max_passes,
                max_moves_per_pass=args.max_moves_per_pass,
                min_gain=args.min_gain,
                min_instance_balance=args.min_instance_balance,
                min_weight_balance=min_weight_balance,
            )
            run(run_args)
            comparison = read_comparison(run_dir / "partition_comparison.csv")
            generic = comparison["generic_balance"]
            v1 = comparison["architecture_aware_v1"]
            v2 = comparison["architecture_score_v2"]

            generic_cross = float(generic["crossing_connections_proxy"])
            v1_cross = float(v1["crossing_connections_proxy"])
            v2_cross = float(v2["crossing_connections_proxy"])
            rows.append(
                {
                    "run_name": run_name,
                    "architecture_weight": arch_weight,
                    "min_weight_balance": min_weight_balance,
                    "v2_crossing_nets": v2["crossing_nets"],
                    "v2_crossing_connections_proxy": v2["crossing_connections_proxy"],
                    "v2_crossing_connection_fraction": v2["crossing_connection_fraction"],
                    "v2_instance_balance_ratio": v2["instance_balance_ratio"],
                    "v2_weight_balance_ratio": v2["weight_balance_ratio"],
                    "v2_reduction_vs_generic": f"{((generic_cross - v2_cross) / generic_cross):.6f}",
                    "v2_reduction_vs_v1": f"{((v1_cross - v2_cross) / v1_cross):.6f}",
                    "generic_crossing_connections_proxy": generic["crossing_connections_proxy"],
                    "v1_crossing_connections_proxy": v1["crossing_connections_proxy"],
                }
            )

    write_csv(
        output_dir / "sweep_summary.csv",
        rows,
        [
            "run_name",
            "architecture_weight",
            "min_weight_balance",
            "v2_crossing_nets",
            "v2_crossing_connections_proxy",
            "v2_crossing_connection_fraction",
            "v2_instance_balance_ratio",
            "v2_weight_balance_ratio",
            "v2_reduction_vs_generic",
            "v2_reduction_vs_v1",
            "generic_crossing_connections_proxy",
            "v1_crossing_connections_proxy",
        ],
    )

    print(output_dir / "sweep_summary.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
