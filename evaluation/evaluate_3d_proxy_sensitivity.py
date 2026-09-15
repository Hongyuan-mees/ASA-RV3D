#!/usr/bin/env python3
"""Run sensitivity analysis for the RISC-V-aware 3D proxy cost model.

The script repeatedly invokes the same transparent proxy-cost evaluator with
different cost weights. It checks whether the relative ranking of partition
methods is stable, especially whether graph-context v3 remains competitive
when the proxy weights are perturbed.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
import tempfile
from pathlib import Path


SWEEP_WEIGHTS = [
    {
        "weight_case": "base_default",
        "high_fanout": 0.25,
        "boundary": 2.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "low_fanout",
        "high_fanout": 0.10,
        "boundary": 2.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "high_fanout",
        "high_fanout": 0.50,
        "boundary": 2.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "low_boundary",
        "high_fanout": 0.25,
        "boundary": 1.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "high_boundary",
        "high_fanout": 0.25,
        "boundary": 4.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "low_arch",
        "high_fanout": 0.25,
        "boundary": 2.0,
        "arch_criticality": 0.5,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "high_arch",
        "high_fanout": 0.25,
        "boundary": 2.0,
        "arch_criticality": 2.0,
        "semantic_uncertainty": 1.0,
    },
    {
        "weight_case": "low_uncertainty",
        "high_fanout": 0.25,
        "boundary": 2.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 0.2,
    },
    {
        "weight_case": "high_uncertainty",
        "high_fanout": 0.25,
        "boundary": 2.0,
        "arch_criticality": 1.0,
        "semantic_uncertainty": 2.0,
    },
    {
        "weight_case": "architecture_heavy",
        "high_fanout": 0.20,
        "boundary": 3.0,
        "arch_criticality": 2.0,
        "semantic_uncertainty": 1.5,
    },
    {
        "weight_case": "connectivity_heavy",
        "high_fanout": 0.60,
        "boundary": 1.0,
        "arch_criticality": 0.5,
        "semantic_uncertainty": 0.5,
    },
]


BENCHMARKS = [
    {
        "design": "ibex",
        "features_dir": "results/ibex_features",
        "assignments": [
            ("generic", "results/ibex_partition_v2_repaired/generic_balance_assignment.csv"),
            ("v2", "results/ibex_partition_v2_repaired/architecture_score_v2_assignment.csv"),
            ("v3_context", "results/ibex_partition_v3_context/architecture_score_v2_assignment.csv"),
            ("connectivity_only", "results/ibex_connectivity_only/architecture_score_v2_assignment.csv"),
        ],
    },
    {
        "design": "riscv32i",
        "features_dir": "results/riscv32i_features",
        "assignments": [
            ("generic", "results/riscv32i_partition_v2/generic_balance_assignment.csv"),
            ("v2", "results/riscv32i_partition_v2/architecture_score_v2_assignment.csv"),
            ("v3_context", "results/riscv32i_partition_v3_context/architecture_score_v2_assignment.csv"),
            ("connectivity_only", "results/riscv32i_connectivity_only/architecture_score_v2_assignment.csv"),
        ],
    },
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_proxy_eval(
    evaluator: Path,
    benchmark: dict[str, object],
    weights: dict[str, object],
    temp_dir: Path,
) -> list[dict[str, str]]:
    design = str(benchmark["design"])
    output_dir = temp_dir / f"{design}_{weights['weight_case']}"

    cmd = [
        sys.executable,
        str(evaluator),
        "--design",
        design,
        "--features-dir",
        str(benchmark["features_dir"]),
        "--high-fanout-weight",
        str(weights["high_fanout"]),
        "--boundary-weight",
        str(weights["boundary"]),
        "--arch-criticality-weight",
        str(weights["arch_criticality"]),
        "--semantic-uncertainty-weight",
        str(weights["semantic_uncertainty"]),
        "--output-dir",
        str(output_dir),
    ]
    for case, path in benchmark["assignments"]:  # type: ignore[index]
        cmd.extend(["--assignment", f"{case}={path}"])

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return read_csv(output_dir / f"{design}_3d_proxy_cost_summary.csv")


def summarize_ranking(rows: list[dict[str, str]]) -> dict[str, str]:
    ranked = sorted(rows, key=lambda row: float(row["riscv_3d_proxy_cost"]))
    best = ranked[0]
    second = ranked[1]
    generic = next(row for row in rows if row["case"] == "generic")
    v3 = next(row for row in rows if row["case"] == "v3_context")
    v2 = next(row for row in rows if row["case"] == "v2")
    connectivity = next(row for row in rows if row["case"] == "connectivity_only")

    return {
        "best_case": best["case"],
        "best_proxy_cost": best["riscv_3d_proxy_cost"],
        "second_case": second["case"],
        "second_proxy_cost": second["riscv_3d_proxy_cost"],
        "v3_rank": str(1 + [row["case"] for row in ranked].index("v3_context")),
        "v3_cost": v3["riscv_3d_proxy_cost"],
        "v3_reduction_vs_generic": v3["reduction_vs_generic_3d_proxy"],
        "v2_cost": v2["riscv_3d_proxy_cost"],
        "connectivity_only_cost": connectivity["riscv_3d_proxy_cost"],
        "generic_cost": generic["riscv_3d_proxy_cost"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evaluator", type=Path, default=Path("evaluation/evaluate_3d_proxy_cost.py"))
    parser.add_argument("--output", type=Path, default=Path("results/benchmark_summary/3d_proxy_cost_weight_sensitivity.csv"))
    args = parser.parse_args()

    all_rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="rv3d_proxy_sensitivity_") as temp_name:
        temp_dir = Path(temp_name)
        for weights in SWEEP_WEIGHTS:
            for benchmark in BENCHMARKS:
                rows = run_proxy_eval(args.evaluator, benchmark, weights, temp_dir)
                ranking = summarize_ranking(rows)
                all_rows.append(
                    {
                        "weight_case": weights["weight_case"],
                        "design": benchmark["design"],
                        "high_fanout_weight": weights["high_fanout"],
                        "boundary_weight": weights["boundary"],
                        "arch_criticality_weight": weights["arch_criticality"],
                        "semantic_uncertainty_weight": weights["semantic_uncertainty"],
                        **ranking,
                    }
                )

    fields = [
        "weight_case",
        "design",
        "high_fanout_weight",
        "boundary_weight",
        "arch_criticality_weight",
        "semantic_uncertainty_weight",
        "best_case",
        "best_proxy_cost",
        "second_case",
        "second_proxy_cost",
        "v3_rank",
        "v3_cost",
        "v3_reduction_vs_generic",
        "v2_cost",
        "connectivity_only_cost",
        "generic_cost",
    ]
    write_csv(args.output, all_rows, fields)

    win_count = sum(1 for row in all_rows if row["best_case"] == "v3_context")
    total = len(all_rows)
    print(args.output)
    print(f"v3_context best in {win_count}/{total} design-weight cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
