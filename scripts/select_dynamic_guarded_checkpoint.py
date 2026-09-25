#!/usr/bin/env python3
"""Select a safe checkpoint from dynamic constrained ASA refinement.

The dynamic local search can keep improving its internal architecture/scenario
objective after the timing-weighted crossing metric has stopped improving.  This
utility replays the accepted-move trace from the native timing-aware assignment,
recomputes area/cut/path/objective metrics for every prefix, and exports the
best checkpoint that satisfies the TritonPart-compatible hard guards.

The selected assignment should still be checked with the canonical independent
timing-crossing evaluator before being used as paper evidence.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import partition_tritonpart_compatible_dynamic_guarded_repair as dyn


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def apply_prefix(base_tier: dict[str, str], trace_rows: list[dict[str, str]], prefix: int) -> dict[str, str]:
    tier = dict(base_tier)
    for row in trace_rows[:prefix]:
        inst = dyn.normalize_name(row["instance"])
        tier[inst] = row["to_tier"]
    return tier


def metrics_for_tier(
    *,
    prefix: int,
    tier: dict[str, str],
    baseline: dict[str, float],
    net_to_instances: dict[str, list[str]],
    area: dict[str, int],
    paths: list[dyn.TimingPath],
    risk: dict[str, float],
    area_lo: float,
    area_hi: float,
) -> dict[str, object]:
    objective = dyn.total_objective(tier, net_to_instances, risk)
    crossing, crossing_conn = dyn.crossing_stats(tier, net_to_instances)
    astats = dyn.area_stats(tier, area)
    pstats = dyn.path_cut_stats(paths, tier)
    cut_regret = (
        (crossing - baseline["crossing_nets"]) / baseline["crossing_nets"]
        if baseline["crossing_nets"]
        else 0.0
    )
    conn_regret = (
        (crossing_conn - baseline["crossing_connections"])
        / baseline["crossing_connections"]
        if baseline["crossing_connections"]
        else 0.0
    )
    pavg_regret = (
        (pstats["P_avg_cut"] - baseline["P_avg_cut"]) / baseline["P_avg_cut"]
        if baseline["P_avg_cut"]
        else 0.0
    )
    pwst_delta = pstats["P_wst_cut"] - baseline["P_wst_cut"]
    objective_reduction = (
        (baseline["objective"] - objective) / baseline["objective"]
        if baseline["objective"]
        else 0.0
    )
    return {
        "prefix": prefix,
        "objective": f"{objective:.6f}",
        "objective_reduction": f"{objective_reduction:.6f}",
        "crossing_nets": crossing,
        "cut_regret": f"{cut_regret:.6f}",
        "crossing_connections_proxy": crossing_conn,
        "crossing_connection_regret": f"{conn_regret:.6f}",
        "area_balance_pass": str(dyn.area_pass(astats, area_lo, area_hi)).lower(),
        "area_weight_balance": f"{astats['area_weight_balance']:.6f}",
        "tier0_area_fraction": f"{astats['tier0_area_fraction']:.6f}",
        "tier1_area_fraction": f"{astats['tier1_area_fraction']:.6f}",
        "P_avg_cut": f"{pstats['P_avg_cut']:.6f}",
        "P_avg_cut_regret": f"{pavg_regret:.6f}",
        "P_wst_cut": f"{pstats['P_wst_cut']:.6f}",
        "P_wst_cut_delta": f"{pwst_delta:.6f}",
    }


def assignment_rows(rows: list[dict[str, str]], tier: dict[str, str]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        item = dict(row)
        item["tier"] = tier[dyn.normalize_name(row["instance"])]
        out.append(item)
    return out


def choose_checkpoint(rows: list[dict[str, object]], max_cut_regret: float) -> dict[str, object] | None:
    legal = []
    for row in rows:
        if row["area_balance_pass"] != "true":
            continue
        if float(row["cut_regret"]) > max_cut_regret:
            continue
        if float(row["P_avg_cut_regret"]) > 0.0:
            continue
        if float(row["P_wst_cut_delta"]) > 0.0:
            continue
        legal.append(row)
    if not legal:
        return None
    # Primary: maximize dynamically recomputed objective reduction.
    # Tie-breaks prefer lower cut/path exposure.
    return max(
        legal,
        key=lambda row: (
            float(row["objective_reduction"]),
            -float(row["cut_regret"]),
            -float(row["P_avg_cut"]),
            -float(row["P_wst_cut"]),
        ),
    )


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
    parser.add_argument("--area-lo", type=float, default=0.48)
    parser.add_argument("--area-hi", type=float, default=0.52)
    parser.add_argument(
        "--architecture-off",
        action="store_true",
        help="Disable recovered architecture semantics when recomputing checkpoint objectives.",
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

    checkpoint_rows: list[dict[str, object]] = []
    selected_tier: dict[str, str] | None = None
    for prefix in range(0, len(trace_rows) + 1):
        tier = apply_prefix(base_tier, trace_rows, prefix)
        checkpoint_rows.append(
            metrics_for_tier(
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
        )

    selected = choose_checkpoint(checkpoint_rows, args.max_cut_regret)
    if selected is not None:
        selected_tier = apply_prefix(base_tier, trace_rows, int(selected["prefix"]))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = args.output_dir / "dynamic_checkpoint_summary.csv"
    selected_path = args.output_dir / "dynamic_selected_checkpoint.csv"
    assignment_path = args.output_dir / "dynamic_selected_checkpoint_assignment.csv"
    write_csv(checkpoint_path, checkpoint_rows)
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

    selected_row = {
        "design": args.design,
        "scenario": args.scenario,
        "architecture_mode": architecture_mode,
        "status": "selected",
        **selected,
        "assignment_file": str(assignment_path),
    }
    write_csv(selected_path, [selected_row])
    assert selected_tier is not None
    write_csv(assignment_path, assignment_rows(rows, selected_tier), list(rows[0].keys()))
    print(
        "selected_checkpoint "
        f"prefix={selected['prefix']} "
        f"objective_reduction={selected['objective_reduction']} "
        f"cut_regret={selected['cut_regret']} "
        f"P_avg_cut={selected['P_avg_cut']} "
        f"P_wst_cut={selected['P_wst_cut']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
