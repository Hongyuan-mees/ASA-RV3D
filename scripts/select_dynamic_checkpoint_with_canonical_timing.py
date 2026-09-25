#!/usr/bin/env python3
"""Select dynamic ASA checkpoint using the canonical timing-crossing evaluator.

The lightweight checkpoint selector only checks area/cut/path guards and the
dynamic objective.  This stricter selector additionally calls
evaluation/evaluate_timing_crossing.py for each legal prefix, so the selected
checkpoint is filtered by the same timing-weighted crossing metric used in the
paper-facing result tables.
"""

from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from pathlib import Path

import partition_tritonpart_compatible_dynamic_guarded_repair as dyn
import select_dynamic_guarded_checkpoint as base


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


def run_timing_crossing(
    *,
    design: str,
    features_dir: Path,
    initial_assignment: Path,
    candidate_assignment: Path,
    output: Path,
) -> dict[str, dict[str, str]]:
    cmd = [
        sys.executable,
        "evaluation/evaluate_timing_crossing.py",
        "--design",
        design,
        "--features-dir",
        str(features_dir),
        "--timing",
        str(features_dir / "timing_context_scores.csv"),
        "--assignment",
        f"native_timing_aware={initial_assignment}",
        "--assignment",
        f"dynamic_checkpoint={candidate_assignment}",
        "--output",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    rows = read_csv(output)
    return {row["case"]: row for row in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--initial-assignment", type=Path, required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--instance-area", type=Path, required=True)
    parser.add_argument("--timing-report", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--max-cut-regret", type=float, default=0.05)
    parser.add_argument("--max-timing-weighted-regret", type=float, default=0.0)
    parser.add_argument("--area-lo", type=float, default=0.48)
    parser.add_argument("--area-hi", type=float, default=0.52)
    parser.add_argument(
        "--architecture-off",
        action="store_true",
        help="Disable recovered architecture semantics when recomputing checkpoint objectives.",
    )
    parser.add_argument(
        "--top-objective-prefixes",
        type=int,
        default=0,
        help="Optionally evaluate only the top-N legal prefixes by dynamic objective reduction. 0 evaluates all legal prefixes.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, base_tier, _weight, arch_unit, semantic_group = dyn.load_assignment(args.initial_assignment)
    architecture_mode = "architecture_off" if args.architecture_off else "architecture_on"
    if args.architecture_off:
        arch_unit = {inst: "unclassified" for inst in base_tier}
        semantic_group = {inst: "infrastructure" for inst in base_tier}
    trace_rows = read_csv(args.trace)
    aliases = dyn.load_aliases(rows)
    area = dyn.load_area(args.instance_area)
    net_to_instances, _inst_to_nets = dyn.load_net_maps(args.features_dir, set(base_tier))
    physical = dyn.load_context_scores(
        args.features_dir / "physical_context_scores.csv",
        ["physical_context_score", "raw_physical_score", "mean_physical_context_score"],
    )
    timing = dyn.load_context_scores(
        args.features_dir / "timing_context_scores.csv",
        ["timing_context_score", "mean_timing_context_score"],
    )
    risk = {
        inst: dyn.instance_risk(inst, args.scenario, arch_unit, semantic_group, physical, timing)
        for inst in base_tier
    }
    paths = dyn.parse_timing_paths(args.timing_report, aliases, args.max_paths)

    baseline_crossing, baseline_conn = dyn.crossing_stats(base_tier, net_to_instances)
    baseline_paths = dyn.path_cut_stats(paths, base_tier)
    baseline = {
        "objective": dyn.total_objective(base_tier, net_to_instances, risk),
        "crossing_nets": float(baseline_crossing),
        "crossing_connections": float(baseline_conn),
        "P_avg_cut": baseline_paths["P_avg_cut"],
        "P_wst_cut": baseline_paths["P_wst_cut"],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_dir = args.output_dir / "candidate_assignments"
    eval_dir = args.output_dir / "candidate_timing_crossing"
    checkpoint_rows: list[dict[str, object]] = []
    for prefix in range(0, len(trace_rows) + 1):
        tier = base.apply_prefix(base_tier, trace_rows, prefix)
        row = base.metrics_for_tier(
            prefix=prefix,
            tier=tier,
            baseline=baseline,
            net_to_instances=net_to_instances,
            area=area,
            paths=paths,
            risk=risk,
            area_lo=args.area_lo,
            area_hi=args.area_hi,
        )
        if row["area_balance_pass"] != "true":
            row["candidate_status"] = "reject_area"
        elif float(row["cut_regret"]) > args.max_cut_regret:
            row["candidate_status"] = "reject_cut"
        elif float(row["P_avg_cut_regret"]) > 0.0 or float(row["P_wst_cut_delta"]) > 0.0:
            row["candidate_status"] = "reject_path"
        else:
            row["candidate_status"] = "legal_before_timing"
        checkpoint_rows.append(row)

    legal = [row for row in checkpoint_rows if row["candidate_status"] == "legal_before_timing"]
    if args.top_objective_prefixes > 0:
        legal = sorted(legal, key=lambda row: float(row["objective_reduction"]), reverse=True)[
            : args.top_objective_prefixes
        ]
    legal_prefixes = {int(row["prefix"]) for row in legal}

    baseline_timing_weighted = None
    evaluated_rows: list[dict[str, object]] = []
    selected: dict[str, object] | None = None
    selected_tier: dict[str, str] | None = None
    for row in checkpoint_rows:
        prefix = int(row["prefix"])
        if prefix not in legal_prefixes:
            evaluated_rows.append(row)
            continue
        tier = base.apply_prefix(base_tier, trace_rows, prefix)
        assignment = candidate_dir / f"prefix_{prefix:04d}_assignment.csv"
        timing_out = eval_dir / f"prefix_{prefix:04d}_timing_crossing.csv"
        write_csv(assignment, base.assignment_rows(rows, tier), list(rows[0].keys()))
        by_case = run_timing_crossing(
            design=args.design,
            features_dir=args.features_dir,
            initial_assignment=args.initial_assignment,
            candidate_assignment=assignment,
            output=timing_out,
        )
        native = by_case["native_timing_aware"]
        candidate = by_case["dynamic_checkpoint"]
        if baseline_timing_weighted is None:
            baseline_timing_weighted = float(native["timing_weighted_crossing"])
        candidate_timing = float(candidate["timing_weighted_crossing"])
        timing_regret = (
            (candidate_timing - baseline_timing_weighted) / baseline_timing_weighted
            if baseline_timing_weighted
            else 0.0
        )
        enriched = {
            **row,
            "candidate_status": (
                "legal"
                if timing_regret <= args.max_timing_weighted_regret
                else "reject_timing_weighted"
            ),
            "native_timing_weighted_crossing": f"{baseline_timing_weighted:.6f}",
            "candidate_timing_weighted_crossing": f"{candidate_timing:.6f}",
            "timing_weighted_regret": f"{timing_regret:.6f}",
            "candidate_timing_crossing_nets": candidate["timing_crossing_nets"],
            "candidate_high_timing_crossing_nets": candidate["high_timing_crossing_nets"],
            "candidate_assignment": str(assignment),
            "timing_crossing_csv": str(timing_out),
        }
        evaluated_rows.append(enriched)
        if enriched["candidate_status"] == "legal":
            if selected is None or (
                float(enriched["objective_reduction"]),
                -float(enriched["timing_weighted_regret"]),
                -float(enriched["cut_regret"]),
            ) > (
                float(selected["objective_reduction"]),
                -float(selected["timing_weighted_regret"]),
                -float(selected["cut_regret"]),
            ):
                selected = enriched
                selected_tier = tier

    summary_path = args.output_dir / "dynamic_canonical_checkpoint_summary.csv"
    selected_path = args.output_dir / "dynamic_canonical_selected_checkpoint.csv"
    selected_assignment = args.output_dir / "dynamic_canonical_selected_checkpoint_assignment.csv"
    write_csv(summary_path, evaluated_rows)
    if selected is None:
        write_csv(
            selected_path,
            [
                {
                    "design": args.design,
                    "scenario": args.scenario,
                    "architecture_mode": architecture_mode,
                    "status": "no_legal_checkpoint",
                }
            ],
        )
        return 2
    assert selected_tier is not None
    write_csv(selected_assignment, base.assignment_rows(rows, selected_tier), list(rows[0].keys()))
    selected_row = {
        "design": args.design,
        "scenario": args.scenario,
        "architecture_mode": architecture_mode,
        "status": "selected",
        **selected,
        "assignment_file": str(selected_assignment),
    }
    write_csv(selected_path, [selected_row])
    print(
        "selected_canonical_checkpoint "
        f"prefix={selected['prefix']} "
        f"objective_reduction={selected['objective_reduction']} "
        f"timing_weighted_regret={selected['timing_weighted_regret']} "
        f"cut_regret={selected['cut_regret']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
