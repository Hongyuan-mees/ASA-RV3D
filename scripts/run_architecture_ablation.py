#!/usr/bin/env python3
"""Run an architecture-semantics ablation for ASA-RV3D.

Goal
----
Compare the current ASA-RV3D timing-regret repair against the same repair flow
with architecture semantics neutralized.  This answers whether the
"architecture-semantic-aware" part contributes beyond timing/physical repair.

The script intentionally avoids editing committed feature files.  It creates a
temporary architecture-neutral feature overlay under `work/`, runs the existing
timing-regret repair script with that overlay, and then re-evaluates the
architecture-off assignment under the original full feature set.  This matters:
the internal objective from a neutralized-feature run is not comparable with the
full ASA-RV3D objective because the scenario/architecture terms have changed
scale.

Compared cases
--------------
- tritonpart: connectivity-first initial assignment.
- architecture_off_asa: timing/physical guarded repair with neutralized
  architecture labels and criticality weights.
- full_asa: current ASA-RV3D timing-regret guarded repair.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import subprocess
from pathlib import Path
from statistics import mean


DEFAULT_DESIGNS = ("riscv32i", "ibex", "picorv32", "scr1_core_tuned")
DEFAULT_SCENARIOS = (
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
)

NEUTRAL_ARCH_UNIT = "unclassified"
NEUTRAL_SEMANTIC_GROUP = "infrastructure"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def fmt(value: float | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        if value == "":
            return ""
        try:
            value = float(value)
        except ValueError:
            return value
    return f"{value:.6f}"


def neutralize_value(column: str, value: str) -> str:
    name = column.lower()
    if name in {"architecture_unit", "arch_unit", "unit"}:
        return NEUTRAL_ARCH_UNIT
    if name in {"architecture_class", "arch_class"}:
        return NEUTRAL_ARCH_UNIT
    if name in {"semantic_group", "group"}:
        return NEUTRAL_SEMANTIC_GROUP
    if name in {"criticality_weight", "architecture_weight", "arch_weight"}:
        return "1.0"
    if name in {"mapping_confidence", "classification_confidence"}:
        return "0.0"
    if name in {
        "boundary_likelihood_score",
        "semantic_context_score",
        "mean_boundary_likelihood_score",
        "mean_semantic_context_score",
    }:
        return "0.0"
    return value


def neutralize_csv(src: Path, dst: Path) -> None:
    rows = read_csv(src)
    if not rows:
        shutil.copy2(src, dst)
        return
    fieldnames = list(rows[0].keys())
    out_rows: list[dict[str, str]] = []
    for row in rows:
        out_rows.append({key: neutralize_value(key, row.get(key, "")) for key in fieldnames})
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)


def link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    try:
        os.symlink(src.resolve(), dst)
    except OSError:
        shutil.copy2(src, dst)


def make_noarch_feature_overlay(features_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    neutralized_files = {
        "architecture_mapping_instances.csv",
        "architecture_instance_classes.csv",
        "architecture_mapping_summary.csv",
        "architecture_summary.csv",
        "graph_context_scores.csv",
        "graph_context_summary.csv",
        "instance_features.csv",
    }
    for src in features_dir.iterdir():
        if not src.is_file():
            continue
        dst = output_dir / src.name
        if src.name in neutralized_files:
            neutralize_csv(src, dst)
        else:
            link_or_copy(src, dst)


def run_command(cmd: list[str], dry_run: bool = False) -> int:
    print("+ " + " ".join(cmd))
    if dry_run:
        return 0
    proc = subprocess.run(cmd, check=False)
    return proc.returncode


def find_row(path: Path, preferred: list[str]) -> dict[str, str]:
    rows = read_csv(path)
    by_strategy = {row.get("strategy", ""): row for row in rows}
    for name in preferred:
        if name in by_strategy:
            return by_strategy[name]
    if rows:
        return rows[-1]
    raise RuntimeError(f"empty comparison file: {path}")


def full_result_dir(design: str, scenario: str) -> Path:
    return Path("results") / f"{design}_tritonpart_timing_regret_guarded_repair" / scenario


def ablation_result_dir(design: str, scenario: str) -> Path:
    return Path("results") / f"{design}_tritonpart_architecture_off_timing_regret_guarded_repair" / scenario


def ablation_eval_dir(design: str, scenario: str) -> Path:
    return Path("work") / "architecture_ablation_full_objective_eval" / design / scenario


def tritonpart_assignment(design: str) -> Path:
    return Path("results") / f"{design}_tritonpart_baseline" / "tritonpart_assignment.csv"


def full_assignment(design: str, scenario: str) -> Path:
    return full_result_dir(design, scenario) / "tritonpart_timing_regret_guarded_repair_assignment.csv"


def ablation_assignment(design: str, scenario: str) -> Path:
    return ablation_result_dir(design, scenario) / "tritonpart_timing_regret_guarded_repair_assignment.csv"


def comparison_file(result_dir: Path) -> Path:
    return result_dir / "partition_comparison.csv"


def get_float(row: dict[str, str], key: str) -> float | None:
    value = row.get(key, "")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def metric(row: dict[str, str], *names: str) -> str:
    for name in names:
        if row.get(name, "") != "":
            return row[name]
    return ""


def collect_timing_crossing(
    design: str,
    scenario: str,
    features_dir: Path,
    output_path: Path,
    dry_run: bool,
) -> dict[str, dict[str, str]]:
    evaluator = Path("evaluation/evaluate_timing_crossing.py")
    timing = features_dir / "timing_context_scores.csv"
    if not evaluator.exists() or not timing.exists():
        return {}

    cmd = [
        "python3",
        str(evaluator),
        "--design",
        design,
        "--features-dir",
        str(features_dir),
        "--timing",
        str(timing),
        "--assignment",
        f"tritonpart={tritonpart_assignment(design)}",
        "--assignment",
        f"architecture_off_asa={ablation_assignment(design, scenario)}",
        "--assignment",
        f"full_asa={full_assignment(design, scenario)}",
        "--output",
        str(output_path),
    ]
    if run_command(cmd, dry_run=dry_run) != 0:
        return {}
    if dry_run or not output_path.exists():
        return {}
    return {row["case"]: row for row in read_csv(output_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", dest="designs")
    parser.add_argument("--scenario", action="append", dest="scenarios")
    parser.add_argument("--work-dir", type=Path, default=Path("work/architecture_ablation_noarch_features"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--skip-run", action="store_true", help="Only summarize existing ablation outputs.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    designs = tuple(args.designs or DEFAULT_DESIGNS)
    scenarios = tuple(args.scenarios or DEFAULT_SCENARIOS)

    summary_rows: list[dict[str, object]] = []
    missing_rows: list[dict[str, object]] = []

    for design in designs:
        original_features = Path("results") / f"{design}_features"
        noarch_features = args.work_dir / design
        if not original_features.exists():
            missing_rows.append({"design": design, "scenario": "", "missing": str(original_features)})
            continue

        if not args.skip_run:
            make_noarch_feature_overlay(original_features, noarch_features)

        for scenario in scenarios:
            full_dir = full_result_dir(design, scenario)
            arch_off_dir = ablation_result_dir(design, scenario)
            arch_off_eval_dir = ablation_eval_dir(design, scenario)
            full_comparison = comparison_file(full_dir)
            arch_off_comparison = comparison_file(arch_off_dir)
            arch_off_eval_comparison = comparison_file(arch_off_eval_dir)

            required = [
                tritonpart_assignment(design),
                full_assignment(design, scenario),
                full_comparison,
            ]
            missing = [str(path) for path in required if not path.exists()]
            if missing:
                missing_rows.append({"design": design, "scenario": scenario, "missing": "; ".join(missing)})
                continue

            if not args.skip_run:
                cmd = [
                    "python3",
                    "partition/partition_tritonpart_timing_regret_guarded_repair.py",
                    "--design",
                    design,
                    "--scenario",
                    scenario,
                    "--features-dir",
                    str(noarch_features),
                    "--tritonpart-assignment",
                    str(tritonpart_assignment(design)),
                    "--output-dir",
                    str(arch_off_dir),
                ]
                rc = run_command(cmd, dry_run=args.dry_run)
                if rc != 0:
                    missing_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "missing": f"architecture-off repair failed with code {rc}",
                        }
                    )
                    continue

                # Re-score the architecture-off assignment under the original
                # full feature set without making additional moves.  This gives
                # a comparable objective and scenario/architecture cost.
                eval_cmd = [
                    "python3",
                    "partition/partition_tritonpart_timing_regret_guarded_repair.py",
                    "--design",
                    design,
                    "--scenario",
                    scenario,
                    "--features-dir",
                    str(original_features),
                    "--tritonpart-assignment",
                    str(ablation_assignment(design, scenario)),
                    "--output-dir",
                    str(arch_off_eval_dir),
                    "--max-moves-per-pass",
                    "0",
                ]
                rc = run_command(eval_cmd, dry_run=args.dry_run)
                if rc != 0:
                    missing_rows.append(
                        {
                            "design": design,
                            "scenario": scenario,
                            "missing": f"architecture-off full-objective eval failed with code {rc}",
                        }
                    )
                    continue

            if args.dry_run:
                continue
            if not arch_off_comparison.exists():
                missing_rows.append({"design": design, "scenario": scenario, "missing": str(arch_off_comparison)})
                continue
            if not arch_off_eval_comparison.exists():
                missing_rows.append({"design": design, "scenario": scenario, "missing": str(arch_off_eval_comparison)})
                continue

            full_initial = find_row(full_comparison, ["tritonpart_initial"])
            full_final = find_row(
                full_comparison,
                ["tritonpart_timing_regret_guarded_repair", "tritonpart_guarded_repair"],
            )
            arch_off_internal_final = find_row(
                arch_off_comparison,
                ["tritonpart_timing_regret_guarded_repair", "tritonpart_guarded_repair"],
            )
            arch_off_eval = find_row(
                arch_off_eval_comparison,
                ["tritonpart_initial", "tritonpart_timing_regret_guarded_repair", "tritonpart_guarded_repair"],
            )

            timing_crossing_path = (
                args.output_dir / f"{design}_{scenario}_architecture_ablation_timing_crossing.csv"
            )
            timing_crossing = collect_timing_crossing(
                design,
                scenario,
                original_features,
                timing_crossing_path,
                dry_run=args.dry_run,
            )

            tri_tw = metric(timing_crossing.get("tritonpart", {}), "timing_weighted_crossing")
            off_tw = metric(timing_crossing.get("architecture_off_asa", {}), "timing_weighted_crossing")
            full_tw = metric(timing_crossing.get("full_asa", {}), "timing_weighted_crossing")

            off_internal_obj = get_float(
                arch_off_internal_final,
                "timing_augmented_objective",
            ) or get_float(arch_off_internal_final, "physical_augmented_objective")
            off_obj = get_float(arch_off_eval, "timing_augmented_objective") or get_float(
                arch_off_eval, "physical_augmented_objective"
            )
            full_obj = get_float(full_final, "timing_augmented_objective") or get_float(
                full_final, "physical_augmented_objective"
            )
            initial_obj = get_float(full_initial, "timing_augmented_objective") or get_float(
                full_initial, "physical_augmented_objective"
            )

            summary_rows.append(
                {
                    "design": design,
                    "scenario": scenario,
                    "tritonpart_objective": fmt(initial_obj),
                    "architecture_off_internal_objective": fmt(off_internal_obj),
                    "architecture_off_objective": fmt(off_obj),
                    "full_asa_objective": fmt(full_obj),
                    "architecture_off_objective_reduction_vs_tritonpart": fmt(
                        ((initial_obj - off_obj) / initial_obj) if initial_obj and off_obj is not None else None
                    ),
                    "full_asa_objective_reduction_vs_tritonpart": fmt(
                        ((initial_obj - full_obj) / initial_obj) if initial_obj and full_obj is not None else None
                    ),
                    "full_minus_architecture_off_objective_delta": fmt(
                        (full_obj - off_obj) if full_obj is not None and off_obj is not None else None
                    ),
                    "tritonpart_crossing_proxy": metric(full_initial, "crossing_connections_proxy"),
                    "architecture_off_crossing_proxy": metric(arch_off_eval, "crossing_connections_proxy"),
                    "full_asa_crossing_proxy": metric(full_final, "crossing_connections_proxy"),
                    "tritonpart_timing_weighted_crossing": tri_tw,
                    "architecture_off_timing_weighted_crossing": off_tw,
                    "full_asa_timing_weighted_crossing": full_tw,
                    "architecture_off_timing_penalty": metric(arch_off_eval, "timing_context_crossing_penalty"),
                    "full_asa_timing_penalty": metric(full_final, "timing_context_crossing_penalty"),
                    "architecture_off_physical_penalty": metric(arch_off_eval, "physical_context_crossing_penalty"),
                    "full_asa_physical_penalty": metric(full_final, "physical_context_crossing_penalty"),
                    "architecture_off_scenario_objective": metric(arch_off_eval, "scenario_objective"),
                    "full_asa_scenario_objective": metric(full_final, "scenario_objective"),
                    "architecture_off_instance_balance": metric(arch_off_eval, "instance_balance_ratio"),
                    "full_asa_instance_balance": metric(full_final, "instance_balance_ratio"),
                    "architecture_off_weight_balance": metric(arch_off_eval, "weight_balance_ratio"),
                    "full_asa_weight_balance": metric(full_final, "weight_balance_ratio"),
                    "architecture_off_assignment": str(ablation_assignment(design, scenario)),
                    "full_asa_assignment": str(full_assignment(design, scenario)),
                }
            )

    fieldnames = [
        "design",
        "scenario",
        "tritonpart_objective",
        "architecture_off_internal_objective",
        "architecture_off_objective",
        "full_asa_objective",
        "architecture_off_objective_reduction_vs_tritonpart",
        "full_asa_objective_reduction_vs_tritonpart",
        "full_minus_architecture_off_objective_delta",
        "tritonpart_crossing_proxy",
        "architecture_off_crossing_proxy",
        "full_asa_crossing_proxy",
        "tritonpart_timing_weighted_crossing",
        "architecture_off_timing_weighted_crossing",
        "full_asa_timing_weighted_crossing",
        "architecture_off_timing_penalty",
        "full_asa_timing_penalty",
        "architecture_off_physical_penalty",
        "full_asa_physical_penalty",
        "architecture_off_scenario_objective",
        "full_asa_scenario_objective",
        "architecture_off_instance_balance",
        "full_asa_instance_balance",
        "architecture_off_weight_balance",
        "full_asa_weight_balance",
        "architecture_off_assignment",
        "full_asa_assignment",
    ]
    if summary_rows:
        write_csv(args.output_dir / "architecture_ablation_summary.csv", summary_rows, fieldnames)

    def mean_float(key: str) -> str:
        values = []
        for row in summary_rows:
            try:
                if row[key] != "":
                    values.append(float(row[key]))
            except (KeyError, ValueError, TypeError):
                pass
        return fmt(mean(values) if values else None)

    rollup_rows = [
        {"metric": "cases", "value": len(summary_rows)},
        {"metric": "designs", "value": ",".join(sorted({str(row["design"]) for row in summary_rows}))},
        {
            "metric": "full_asa_better_objective_cases",
            "value": sum(
                1
                for row in summary_rows
                if row.get("full_minus_architecture_off_objective_delta", "") != ""
                and float(row["full_minus_architecture_off_objective_delta"]) < 0
            ),
        },
        {
            "metric": "architecture_off_better_objective_cases",
            "value": sum(
                1
                for row in summary_rows
                if row.get("full_minus_architecture_off_objective_delta", "") != ""
                and float(row["full_minus_architecture_off_objective_delta"]) > 0
            ),
        },
        {
            "metric": "full_asa_better_timing_weighted_crossing_cases",
            "value": sum(
                1
                for row in summary_rows
                if row.get("full_asa_timing_weighted_crossing", "") != ""
                and row.get("architecture_off_timing_weighted_crossing", "") != ""
                and float(row["full_asa_timing_weighted_crossing"])
                < float(row["architecture_off_timing_weighted_crossing"])
            ),
        },
        {
            "metric": "architecture_off_better_timing_weighted_crossing_cases",
            "value": sum(
                1
                for row in summary_rows
                if row.get("full_asa_timing_weighted_crossing", "") != ""
                and row.get("architecture_off_timing_weighted_crossing", "") != ""
                and float(row["architecture_off_timing_weighted_crossing"])
                < float(row["full_asa_timing_weighted_crossing"])
            ),
        },
        {
            "metric": "mean_architecture_off_objective_reduction_vs_tritonpart",
            "value": mean_float("architecture_off_objective_reduction_vs_tritonpart"),
        },
        {
            "metric": "mean_full_asa_objective_reduction_vs_tritonpart",
            "value": mean_float("full_asa_objective_reduction_vs_tritonpart"),
        },
        {
            "metric": "mean_full_minus_architecture_off_objective_delta",
            "value": mean_float("full_minus_architecture_off_objective_delta"),
        },
        {
            "metric": "mean_architecture_off_scenario_objective",
            "value": mean_float("architecture_off_scenario_objective"),
        },
        {
            "metric": "mean_full_asa_scenario_objective",
            "value": mean_float("full_asa_scenario_objective"),
        },
        {
            "metric": "mean_architecture_off_timing_weighted_crossing",
            "value": mean_float("architecture_off_timing_weighted_crossing"),
        },
        {
            "metric": "mean_full_asa_timing_weighted_crossing",
            "value": mean_float("full_asa_timing_weighted_crossing"),
        },
        {
            "metric": "mean_architecture_off_weight_balance",
            "value": mean_float("architecture_off_weight_balance"),
        },
        {
            "metric": "mean_full_asa_weight_balance",
            "value": mean_float("full_asa_weight_balance"),
        },
    ]
    write_csv(args.output_dir / "architecture_ablation_rollup.csv", rollup_rows, ["metric", "value"])
    write_csv(
        args.output_dir / "architecture_ablation_missing_inputs.csv",
        missing_rows,
        ["design", "scenario", "missing"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
