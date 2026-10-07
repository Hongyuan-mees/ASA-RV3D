#!/usr/bin/env python3
"""Restore a native baseline assignment to the reconstructed area window.

This reviewer-response utility is deliberately scenario-independent. It does
not use design-context weights and does not optimize the ASA-RV3D objective.
It only asks whether a native timing-aware baseline that is just outside the
reconstructed area window can be brought back into the window with minimal tier
moves, optionally preserving raw-cut and timing-path guards.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.evaluate_timing_path_cuts import load_assignment as load_path_assignment  # noqa: E402
from evaluation.evaluate_timing_path_cuts import parse_timing_paths, transition_count  # noqa: E402
from evaluation.net_graph_utils import (  # noqa: E402
    assignment_tiers,
    crossing_stats,
    load_feature_net_graph,
    net_tier_counts,
    normalize_instance_name,
    read_csv,
)
from scripts.audit_native_baseline_feasibility import (  # noqa: E402
    area_violation,
    load_area_index,
    match_area,
)


def format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if math.isinf(value):
            return "inf"
        return f"{value:.6f}"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_value(row.get(key, "")) for key in fieldnames})


def finite_ratio(delta: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0 if delta <= 0 else math.inf
    return delta / baseline


def load_assignment_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"empty assignment: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
    if "instance" not in fieldnames or "tier" not in fieldnames:
        raise RuntimeError(f"assignment must contain instance,tier columns: {path}")
    return rows, fieldnames


def write_assignment(path: Path, rows: list[dict[str, str]], fieldnames: list[str], final_tiers: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            inst = normalize_instance_name(out.get("instance", ""))
            if inst in final_tiers:
                out["tier"] = final_tiers[inst]
            writer.writerow(out)


def area_stats(tiers: dict[str, str], area_by_instance: dict[str, float]) -> tuple[float, float, float]:
    tier0 = 0.0
    tier1 = 0.0
    for inst, area in area_by_instance.items():
        tier = tiers.get(inst)
        if tier == "tier0":
            tier0 += area
        elif tier == "tier1":
            tier1 += area
    total = tier0 + tier1
    return tier0, tier1, tier0 / total if total else 0.0


def area_stats_after_move(state: dict[str, object], area: float, from_tier: str, to_tier: str) -> tuple[float, float, float]:
    tier0 = float(state["tier0_area"])
    tier1 = float(state["tier1_area"])
    if from_tier == "tier0" and to_tier == "tier1":
        tier0 -= area
        tier1 += area
    elif from_tier == "tier1" and to_tier == "tier0":
        tier0 += area
        tier1 -= area
    else:
        raise RuntimeError(f"unsupported move direction: {from_tier}->{to_tier}")
    total = tier0 + tier1
    return tier0, tier1, tier0 / total if total else 0.0


def path_transition_counts(paths, tiers: dict[str, str]) -> list[int]:
    return [transition_count(path, tiers) for path in paths]


def summarize_path_counts(transitions: list[int], path_count: int) -> tuple[float, int, int, int, float]:
    if path_count <= 0:
        return 0.0, 0, 0, 0, 0.0
    total = sum(transitions)
    cut_paths = sum(1 for count in transitions if count > 0)
    return total / path_count, max(transitions) if transitions else 0, total, cut_paths, cut_paths / path_count


def build_inst_to_paths(paths) -> dict[str, list[int]]:
    inst_to_paths: dict[str, list[int]] = {}
    for index, path in enumerate(paths):
        for inst in set(path.instances):
            inst_to_paths.setdefault(inst, []).append(index)
    return inst_to_paths


def crossing_contribution(tiers: dict[str, str], instances: list[str]) -> tuple[int, int]:
    c0, c1 = net_tier_counts(tiers, instances)
    if c0 and c1:
        return 1, min(c0, c1)
    return 0, 0


def crossing_after_move(
    tiers: dict[str, str],
    inst: str,
    to_tier: str,
    net_to_instances: dict[str, list[str]],
    inst_to_nets: dict[str, list[str]],
    current_crossing_nets: int,
    current_crossing_connections: int,
) -> tuple[int, int]:
    next_tiers = dict(tiers)
    next_tiers[inst] = to_tier
    delta_nets = 0
    delta_connections = 0
    for net in inst_to_nets.get(inst, []):
        instances = net_to_instances[net]
        before_net, before_conn = crossing_contribution(tiers, instances)
        after_net, after_conn = crossing_contribution(next_tiers, instances)
        delta_nets += after_net - before_net
        delta_connections += after_conn - before_conn
    return current_crossing_nets + delta_nets, current_crossing_connections + delta_connections


def path_counts_after_move(
    tiers: dict[str, str],
    inst: str,
    to_tier: str,
    paths,
    inst_to_paths: dict[str, list[int]],
    current_counts: list[int],
) -> list[int]:
    affected = inst_to_paths.get(inst, [])
    if not affected:
        return current_counts
    next_tiers = dict(tiers)
    next_tiers[inst] = to_tier
    next_counts = list(current_counts)
    for path_index in affected:
        next_counts[path_index] = transition_count(paths[path_index], next_tiers)
    return next_counts


def make_state(
    *,
    tier0_area: float,
    tier1_area: float,
    crossing_nets: int,
    crossing_connections: int,
    transitions: list[int],
    path_count: int,
) -> dict[str, object]:
    total_area = tier0_area + tier1_area
    pavg, pwst, total_transitions, cut_path_count, cut_path_fraction = summarize_path_counts(transitions, path_count)
    return {
        "tier0_area": tier0_area,
        "tier1_area": tier1_area,
        "tier0_area_fraction": tier0_area / total_area if total_area else 0.0,
        "crossing_nets": crossing_nets,
        "crossing_connections_proxy": crossing_connections,
        "P_avg_cut": pavg,
        "P_wst_cut": pwst,
        "total_tier_transitions": total_transitions,
        "cut_path_count": cut_path_count,
        "cut_path_fraction": cut_path_fraction,
        "path_count": path_count,
    }


def evaluate_state(
    tiers: dict[str, str],
    area_by_instance: dict[str, float],
    net_to_instances: dict[str, list[str]],
    paths,
) -> tuple[dict[str, object], list[int]]:
    tier0_area, tier1_area, _tier0_fraction = area_stats(tiers, area_by_instance)
    crossing_nets, crossing_connections = crossing_stats(tiers, net_to_instances)
    transitions = path_transition_counts(paths, tiers)
    return make_state(
        tier0_area=tier0_area,
        tier1_area=tier1_area,
        crossing_nets=crossing_nets,
        crossing_connections=crossing_connections,
        transitions=transitions,
        path_count=len(paths),
    ), transitions


def move_direction(tier0_fraction: float, area_lo: float, area_hi: float) -> tuple[str | None, str | None]:
    if tier0_fraction > area_hi:
        return "tier0", "tier1"
    if tier0_fraction < area_lo:
        return "tier1", "tier0"
    return None, None


def violation_value(frac: float, lo: float, hi: float) -> float:
    value = area_violation(frac, lo, hi)
    return float(value) if isinstance(value, float) else math.inf


def guard_result(
    baseline: dict[str, object],
    final: dict[str, object],
    max_cut_regret: float,
    max_pavg_regret: float,
    max_pwst_delta: float,
) -> tuple[bool, str, float, float, float]:
    baseline_crossing = int(baseline["crossing_nets"])
    final_crossing = int(final["crossing_nets"])
    cut_regret = finite_ratio(final_crossing - baseline_crossing, baseline_crossing)
    pavg_regret = float(final["P_avg_cut"]) - float(baseline["P_avg_cut"])
    pwst_delta = float(final["P_wst_cut"]) - float(baseline["P_wst_cut"])
    reasons: list[str] = []
    if cut_regret > max_cut_regret + 1e-12:
        reasons.append("raw_cut")
    if pavg_regret > max_pavg_regret + 1e-12:
        reasons.append("P_avg_cut")
    if pwst_delta > max_pwst_delta + 1e-12:
        reasons.append("P_wst_cut")
    return not reasons, ";".join(reasons) if reasons else "pass", cut_regret, pavg_regret, pwst_delta


def candidate_rows(
    rows: list[dict[str, str]],
    tiers: dict[str, str],
    area_by_instance: dict[str, float],
    from_tier: str,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        inst = normalize_instance_name(row.get("instance", ""))
        if not inst or tiers.get(inst) != from_tier:
            continue
        area = area_by_instance.get(inst)
        if area is None or area <= 0:
            continue
        out.append(
            {
                "instance": inst,
                "area": area,
                "architecture_unit": row.get("architecture_unit", ""),
                "semantic_group": row.get("semantic_group", ""),
            }
        )
    return sorted(out, key=lambda item: str(item["instance"]))


def trial_state_for_move(
    *,
    current_state: dict[str, object],
    current_tiers: dict[str, str],
    current_transitions: list[int],
    inst: str,
    area: float,
    from_tier: str,
    to_tier: str,
    net_to_instances: dict[str, list[str]],
    inst_to_nets: dict[str, list[str]],
    paths,
    inst_to_paths: dict[str, list[int]],
) -> tuple[dict[str, object], list[int]]:
    tier0_area, tier1_area, _ = area_stats_after_move(current_state, area, from_tier, to_tier)
    crossing_nets, crossing_connections = crossing_after_move(
        current_tiers,
        inst,
        to_tier,
        net_to_instances,
        inst_to_nets,
        int(current_state["crossing_nets"]),
        int(current_state["crossing_connections_proxy"]),
    )
    transitions = path_counts_after_move(current_tiers, inst, to_tier, paths, inst_to_paths, current_transitions)
    return make_state(
        tier0_area=tier0_area,
        tier1_area=tier1_area,
        crossing_nets=crossing_nets,
        crossing_connections=crossing_connections,
        transitions=transitions,
        path_count=len(paths),
    ), transitions


def reject_bucket(reason: str) -> str:
    if reason in {"no_area_progress", "missing_area"}:
        return "rejected_area_candidates"
    if "raw_cut" in reason:
        return "rejected_cut_candidates"
    if "P_avg_cut" in reason or "P_wst_cut" in reason:
        return "rejected_path_candidates"
    return "rejected_area_candidates"


def restore_policy(
    *,
    policy: str,
    design: str,
    initial_assignment: Path,
    output_dir: Path,
    rows: list[dict[str, str]],
    fieldnames: list[str],
    initial_tiers: dict[str, str],
    area_by_instance: dict[str, float],
    net_to_instances: dict[str, list[str]],
    inst_to_nets: dict[str, list[str]],
    paths,
    area_lo: float,
    area_hi: float,
    max_cut_regret: float,
    max_pavg_regret: float,
    max_pwst_delta: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    start_time = time.perf_counter()
    current_tiers = dict(initial_tiers)
    baseline, current_transitions = evaluate_state(current_tiers, area_by_instance, net_to_instances, paths)
    current_state = dict(baseline)
    inst_to_paths = build_inst_to_paths(paths)

    move_rows: list[dict[str, object]] = []
    accepted_moves = 0
    accepted_area = 0.0
    scan_totals = {
        "scanned_candidates": 0,
        "accepted_candidates": 0,
        "rejected_area_candidates": 0,
        "rejected_cut_candidates": 0,
        "rejected_path_candidates": 0,
    }

    while True:
        current_fraction = float(current_state["tier0_area_fraction"])
        current_violation = violation_value(current_fraction, area_lo, area_hi)
        from_tier, to_tier = move_direction(current_fraction, area_lo, area_hi)
        if from_tier is None or to_tier is None:
            status = "already_feasible" if accepted_moves == 0 else f"restored_{policy}"
            guard_status = "not_needed" if accepted_moves == 0 else ("not_applied" if policy == "area_only" else "pass")
            break

        best: tuple[tuple[object, ...], dict[str, object], list[int], dict[str, object]] | None = None
        candidates = candidate_rows(rows, current_tiers, area_by_instance, from_tier)
        print(f"{policy}: step={accepted_moves + 1} tier0={current_fraction:.6f} violation={current_violation:.6f} candidates={len(candidates)}")

        for item in candidates:
            scan_totals["scanned_candidates"] += 1
            inst = str(item["instance"])
            area = float(item["area"])
            trial, trial_transitions = trial_state_for_move(
                current_state=current_state,
                current_tiers=current_tiers,
                current_transitions=current_transitions,
                inst=inst,
                area=area,
                from_tier=from_tier,
                to_tier=to_tier,
                net_to_instances=net_to_instances,
                inst_to_nets=inst_to_nets,
                paths=paths,
                inst_to_paths=inst_to_paths,
            )
            after_fraction = float(trial["tier0_area_fraction"])
            after_violation = violation_value(after_fraction, area_lo, area_hi)
            guard_ok, reason, cut_regret, pavg_regret, pwst_delta = guard_result(
                baseline,
                trial,
                max_cut_regret,
                max_pavg_regret,
                max_pwst_delta,
            )
            reject_reason = ""
            if after_violation >= current_violation - 1e-15:
                reject_reason = "no_area_progress"
                scan_totals[reject_bucket(reject_reason)] += 1
            elif policy == "guarded" and not guard_ok:
                reject_reason = reason
                scan_totals[reject_bucket(reject_reason)] += 1
            else:
                direct_feasible = area_lo <= after_fraction <= area_hi
                raw_increase = int(trial["crossing_nets"]) - int(baseline["crossing_nets"])
                rank = (
                    0 if direct_feasible else 1,
                    after_violation,
                    raw_increase,
                    pavg_regret,
                    pwst_delta,
                    area,
                    inst,
                )
                trial_row = make_move_row(
                    design=design,
                    policy=policy,
                    step=accepted_moves + 1,
                    item=item,
                    from_tier=from_tier,
                    to_tier=to_tier,
                    before=current_state,
                    after=trial,
                    area_violation_before=current_violation,
                    area_violation_after=after_violation,
                    cut_regret=cut_regret,
                    pavg_regret=pavg_regret,
                    pwst_delta=pwst_delta,
                    guard_result=reason if policy == "guarded" else "not_applied",
                    accepted=False,
                    reject_reason=reject_reason,
                )
                if best is None or rank < best[0]:
                    best = (rank, trial, trial_transitions, trial_row)
                continue

            move_rows.append(
                make_move_row(
                    design=design,
                    policy=policy,
                    step=accepted_moves + 1,
                    item=item,
                    from_tier=from_tier,
                    to_tier=to_tier,
                    before=current_state,
                    after=trial,
                    area_violation_before=current_violation,
                    area_violation_after=after_violation,
                    cut_regret=cut_regret,
                    pavg_regret=pavg_regret,
                    pwst_delta=pwst_delta,
                    guard_result=reason if policy == "guarded" else "not_applied",
                    accepted=False,
                    reject_reason=reject_reason,
                )
            )

        if best is None:
            status = "failed_no_legal_move"
            guard_status = "failed_guard_or_area" if policy == "guarded" else "failed_area"
            break

        _rank, selected_state, selected_transitions, selected_row = best
        selected_inst = str(selected_row["instance"])
        current_tiers[selected_inst] = to_tier
        current_state = selected_state
        current_transitions = selected_transitions
        accepted_moves += 1
        accepted_area += float(selected_row["area"])
        scan_totals["accepted_candidates"] += 1
        selected_row["accepted"] = True
        selected_row["reject_reason"] = ""
        move_rows.append(selected_row)

    final = current_state
    if policy == "guarded":
        guard_ok, guard_status_check, _cut_regret, _pavg_regret, _pwst_delta = guard_result(
            baseline,
            final,
            max_cut_regret,
            max_pavg_regret,
            max_pwst_delta,
        )
        if str(status).startswith("restored") and not guard_ok:
            status = "failed_guard_after_restore"
            guard_status = guard_status_check

    notes = (
        "area_strategy=minimal_perturbation_iterative;"
        f"runtime_sec={time.perf_counter() - start_time:.3f};"
        f"path_count={int(final['path_count'])}"
    )

    restored_assignment = output_dir / policy / "restored_assignment.csv"
    write_assignment(restored_assignment, rows, fieldnames, current_tiers)
    summary = summary_row(
        design=design,
        policy=policy,
        status=status,
        initial_assignment=initial_assignment,
        restored_assignment=restored_assignment,
        baseline=baseline,
        final=final,
        area_lo=area_lo,
        area_hi=area_hi,
        moved_instances=accepted_moves,
        total_moved_area=accepted_area,
        guard_status=guard_status,
        notes=notes,
        scan_totals=scan_totals,
        runtime_sec=time.perf_counter() - start_time,
    )
    return summary, move_rows


def make_move_row(
    *,
    design: str,
    policy: str,
    step: int,
    item: dict[str, object],
    from_tier: str,
    to_tier: str,
    before: dict[str, object],
    after: dict[str, object],
    area_violation_before: float,
    area_violation_after: float,
    cut_regret: float,
    pavg_regret: float,
    pwst_delta: float,
    guard_result: str,
    accepted: bool,
    reject_reason: str,
) -> dict[str, object]:
    return {
        "design": design,
        "policy": policy,
        "step": step,
        "instance": item.get("instance", ""),
        "architecture_unit": item.get("architecture_unit", ""),
        "semantic_group": item.get("semantic_group", ""),
        "from_tier": from_tier,
        "to_tier": to_tier,
        "area": item.get("area", ""),
        "area_violation_before": area_violation_before,
        "area_violation_after": area_violation_after,
        "tier0_area_fraction_before": before["tier0_area_fraction"],
        "tier0_area_fraction_after": after["tier0_area_fraction"],
        "raw_crossing_nets_before": before["crossing_nets"],
        "raw_crossing_nets_after": after["crossing_nets"],
        "raw_cut_regret_after": cut_regret,
        "crossing_connections_before": before["crossing_connections_proxy"],
        "crossing_connections_after": after["crossing_connections_proxy"],
        "mean_path_transitions_after": after["P_avg_cut"],
        "mean_path_transition_regret_after": pavg_regret,
        "max_path_transitions_after": after["P_wst_cut"],
        "max_path_transition_delta_after": pwst_delta,
        "crossing_path_fraction_after": after["cut_path_fraction"],
        "guard_result": guard_result,
        "accepted": accepted,
        "reject_reason": reject_reason,
    }


def aggregate_transition_delay(total_transitions: float, delay_ns: float) -> float:
    return total_transitions * delay_ns


def summary_row(
    *,
    design: str,
    policy: str,
    status: str,
    initial_assignment: Path,
    restored_assignment: Path,
    baseline: dict[str, object],
    final: dict[str, object],
    area_lo: float,
    area_hi: float,
    moved_instances: int,
    total_moved_area: float,
    guard_status: str,
    notes: str,
    scan_totals: dict[str, int],
    runtime_sec: float,
) -> dict[str, object]:
    baseline_crossing = int(baseline["crossing_nets"])
    final_crossing = int(final["crossing_nets"])
    baseline_connections = int(baseline["crossing_connections_proxy"])
    final_connections = int(final["crossing_connections_proxy"])
    return {
        "design": design,
        "policy": policy,
        "status": status,
        "initial_assignment_file": str(initial_assignment),
        "restored_assignment_file": str(restored_assignment),
        "area_lo": area_lo,
        "area_hi": area_hi,
        "baseline_tier0_area_fraction": baseline["tier0_area_fraction"],
        "final_tier0_area_fraction": final["tier0_area_fraction"],
        "area_violation_before": area_violation(float(baseline["tier0_area_fraction"]), area_lo, area_hi),
        "area_violation_after": area_violation(float(final["tier0_area_fraction"]), area_lo, area_hi),
        "reconstructed_area_pass": area_lo <= float(final["tier0_area_fraction"]) <= area_hi,
        "baseline_crossing_nets": baseline_crossing,
        "final_crossing_nets": final_crossing,
        "cut_regret": finite_ratio(final_crossing - baseline_crossing, baseline_crossing),
        "baseline_crossing_connections_proxy": baseline_connections,
        "final_crossing_connections_proxy": final_connections,
        "crossing_connection_regret": finite_ratio(final_connections - baseline_connections, baseline_connections),
        "baseline_crossing_path_fraction": baseline["cut_path_fraction"],
        "final_crossing_path_fraction": final["cut_path_fraction"],
        "baseline_P_avg_cut": baseline["P_avg_cut"],
        "final_P_avg_cut": final["P_avg_cut"],
        "P_avg_cut_regret": float(final["P_avg_cut"]) - float(baseline["P_avg_cut"]),
        "baseline_P_wst_cut": baseline["P_wst_cut"],
        "final_P_wst_cut": final["P_wst_cut"],
        "P_wst_cut_delta": float(final["P_wst_cut"]) - float(baseline["P_wst_cut"]),
        "baseline_total_tier_transitions": baseline["total_tier_transitions"],
        "final_total_tier_transitions": final["total_tier_transitions"],
        "aggregate_transition_delay_20ps": aggregate_transition_delay(float(final["total_tier_transitions"]), 0.020),
        "aggregate_transition_delay_50ps": aggregate_transition_delay(float(final["total_tier_transitions"]), 0.050),
        "aggregate_transition_delay_100ps": aggregate_transition_delay(float(final["total_tier_transitions"]), 0.100),
        "moved_instances": moved_instances,
        "total_moved_area": total_moved_area,
        "scanned_candidates": scan_totals["scanned_candidates"],
        "accepted_candidates": scan_totals["accepted_candidates"],
        "rejected_area_candidates": scan_totals["rejected_area_candidates"],
        "rejected_cut_candidates": scan_totals["rejected_cut_candidates"],
        "rejected_path_candidates": scan_totals["rejected_path_candidates"],
        "runtime_sec": runtime_sec,
        "guard_status": guard_status,
        "notes": notes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--initial-assignment", required=True, type=Path)
    parser.add_argument("--features-dir", required=True, type=Path)
    parser.add_argument("--instance-area", required=True, type=Path)
    parser.add_argument("--timing-report", required=True, type=Path)
    parser.add_argument("--policy", action="append", choices=("area_only", "guarded"), required=True)
    parser.add_argument("--area-lo", type=float, default=0.48)
    parser.add_argument("--area-hi", type=float, default=0.52)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--max-cut-regret", type=float, default=0.05)
    parser.add_argument("--max-pavg-regret", type=float, default=0.0)
    parser.add_argument("--max-pwst-delta", type=float, default=0.0)
    parser.add_argument("--output-root", type=Path, default=Path("results/scr1_core_tuned_baseline_feasibility_restoration"))
    parser.add_argument("--summary-output", type=Path, default=Path("results/benchmark_summary/scr1_core_tuned_feasibility_restoration_summary.csv"))
    parser.add_argument("--moves-output", type=Path, default=Path("results/benchmark_summary/scr1_core_tuned_feasibility_restoration_moves.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    initial_assignment = args.initial_assignment
    features_path = args.features_dir / "instance_features.csv"
    rows, fieldnames = load_assignment_rows(initial_assignment)
    initial_tiers = assignment_tiers(initial_assignment)
    assignment_instances = set(initial_tiers.keys())

    area_by_id, alias_to_ids, _area_rows, _skipped = load_area_index(args.instance_area)
    area_by_instance: dict[str, float] = {}
    missing_area = 0
    for row in rows:
        inst = normalize_instance_name(row.get("instance", ""))
        status, area = match_area(inst, area_by_id, alias_to_ids)
        if status == "matched" and area is not None:
            area_by_instance[inst] = area
        else:
            missing_area += 1
    if missing_area:
        raise RuntimeError(f"area matching failed for {missing_area} assignment instances")

    graph = load_feature_net_graph(features_path, assignment_instances)
    _path_tiers, aliases = load_path_assignment(initial_assignment)
    paths = parse_timing_paths(args.timing_report, aliases, args.max_paths)

    summary_rows: list[dict[str, object]] = []
    move_rows: list[dict[str, object]] = []
    for policy in args.policy:
        summary, moves = restore_policy(
            policy=policy,
            design=args.design,
            initial_assignment=initial_assignment,
            output_dir=args.output_root,
            rows=rows,
            fieldnames=fieldnames,
            initial_tiers=initial_tiers,
            area_by_instance=area_by_instance,
            net_to_instances=graph.net_to_instances,
            inst_to_nets=graph.inst_to_nets,
            paths=paths,
            area_lo=args.area_lo,
            area_hi=args.area_hi,
            max_cut_regret=args.max_cut_regret,
            max_pavg_regret=args.max_pavg_regret,
            max_pwst_delta=args.max_pwst_delta,
        )
        summary_rows.append(summary)
        move_rows.extend(moves)

    summary_fields = [
        "design",
        "policy",
        "status",
        "initial_assignment_file",
        "restored_assignment_file",
        "area_lo",
        "area_hi",
        "baseline_tier0_area_fraction",
        "final_tier0_area_fraction",
        "area_violation_before",
        "area_violation_after",
        "reconstructed_area_pass",
        "baseline_crossing_nets",
        "final_crossing_nets",
        "cut_regret",
        "baseline_crossing_connections_proxy",
        "final_crossing_connections_proxy",
        "crossing_connection_regret",
        "baseline_crossing_path_fraction",
        "final_crossing_path_fraction",
        "baseline_P_avg_cut",
        "final_P_avg_cut",
        "P_avg_cut_regret",
        "baseline_P_wst_cut",
        "final_P_wst_cut",
        "P_wst_cut_delta",
        "baseline_total_tier_transitions",
        "final_total_tier_transitions",
        "aggregate_transition_delay_20ps",
        "aggregate_transition_delay_50ps",
        "aggregate_transition_delay_100ps",
        "moved_instances",
        "total_moved_area",
        "scanned_candidates",
        "accepted_candidates",
        "rejected_area_candidates",
        "rejected_cut_candidates",
        "rejected_path_candidates",
        "runtime_sec",
        "guard_status",
        "notes",
    ]
    move_fields = [
        "design",
        "policy",
        "step",
        "instance",
        "architecture_unit",
        "semantic_group",
        "from_tier",
        "to_tier",
        "area",
        "area_violation_before",
        "area_violation_after",
        "tier0_area_fraction_before",
        "tier0_area_fraction_after",
        "raw_crossing_nets_before",
        "raw_crossing_nets_after",
        "raw_cut_regret_after",
        "crossing_connections_before",
        "crossing_connections_after",
        "mean_path_transitions_after",
        "mean_path_transition_regret_after",
        "max_path_transitions_after",
        "max_path_transition_delta_after",
        "crossing_path_fraction_after",
        "guard_result",
        "accepted",
        "reject_reason",
    ]
    write_csv(args.summary_output, summary_rows, summary_fields)
    write_csv(args.moves_output, move_rows, move_fields)

    print(args.summary_output)
    print(args.moves_output)
    for row in summary_rows:
        print(
            "{policy}: status={status} final_tier0={tier0} moves={moves} "
            "guard={guard} scanned={scanned} accepted={accepted} rejected_cut={cut} rejected_path={path}".format(
                policy=row["policy"],
                status=row["status"],
                tier0=format_value(row["final_tier0_area_fraction"]),
                moves=row["moved_instances"],
                guard=row["guard_status"],
                scanned=row["scanned_candidates"],
                accepted=row["accepted_candidates"],
                cut=row["rejected_cut_candidates"],
                path=row["rejected_path_candidates"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
