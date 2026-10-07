#!/usr/bin/env python3
"""Restore a native baseline assignment to the reconstructed area window.

This reviewer-response utility is deliberately scenario-independent.  It does
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
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.evaluate_timing_path_cuts import parse_timing_paths, transition_count  # noqa: E402
from evaluation.net_graph_utils import (  # noqa: E402
    assignment_tiers,
    crossing_stats,
    load_feature_net_graph,
    normalize_instance_name,
    read_csv,
)
from scripts.audit_native_baseline_feasibility import (  # noqa: E402
    area_violation,
    load_area_index,
    match_area,
    normalize_tier,
)


PHYSICAL_ONLY_TOKENS = (
    "FILLER",
    "FILL",
    "TAP",
    "WELLTAP",
    "DECAP",
    "ENDCAP",
    "ANTENNA",
)


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: format_value(row.get(key, "")) for key in fieldnames})


def format_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def finite_ratio(delta: float, baseline: float) -> float:
    if baseline == 0:
        if delta <= 0:
            return 0.0
        return math.inf
    return delta / baseline


def is_physical_only(row: dict[str, str]) -> bool:
    blob = " ".join(str(row.get(key, "")) for key in ("instance", "cell_type", "category", "architecture_unit", "semantic_group"))
    upper = blob.upper()
    return any(token in upper for token in PHYSICAL_ONLY_TOKENS)


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


def path_metrics(paths, tiers: dict[str, str]) -> tuple[float, int, int]:
    if not paths:
        return 0.0, 0, 0
    transitions = [transition_count(path, tiers) for path in paths]
    return sum(transitions) / len(paths), max(transitions), sum(transitions)


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
    fraction = tier0 / total if total else 0.0
    return tier0, tier1, fraction


def guard_result(
    *,
    baseline_crossing: int,
    final_crossing: int,
    baseline_pavg: float,
    final_pavg: float,
    baseline_pwst: int,
    final_pwst: int,
    max_cut_regret: float,
    max_pavg_regret: float,
    max_pwst_delta: float,
) -> tuple[bool, str, float, float, float]:
    cut_regret = finite_ratio(final_crossing - baseline_crossing, baseline_crossing)
    pavg_regret = final_pavg - baseline_pavg
    pwst_delta = final_pwst - baseline_pwst
    reasons: list[str] = []
    if cut_regret > max_cut_regret + 1e-12:
        reasons.append("raw_cut")
    if pavg_regret > max_pavg_regret + 1e-12:
        reasons.append("P_avg_cut")
    if pwst_delta > max_pwst_delta:
        reasons.append("P_wst_cut")
    return not reasons, ";".join(reasons) if reasons else "pass", cut_regret, pavg_regret, float(pwst_delta)


def move_direction(tier0_fraction: float, area_lo: float, area_hi: float) -> tuple[str | None, str | None]:
    if tier0_fraction > area_hi:
        return "tier0", "tier1"
    if tier0_fraction < area_lo:
        return "tier1", "tier0"
    return None, None


def target_area_shift(tier0_area: float, tier1_area: float, area_lo: float, area_hi: float) -> float:
    total = tier0_area + tier1_area
    fraction = tier0_area / total if total else 0.0
    if fraction > area_hi:
        return tier0_area - area_hi * total
    if fraction < area_lo:
        return area_lo * total - tier0_area
    return 0.0


def collect_candidates(
    rows: list[dict[str, str]],
    tiers: dict[str, str],
    area_by_instance: dict[str, float],
    from_tier: str,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for row in rows:
        inst = normalize_instance_name(row.get("instance", ""))
        if not inst or tiers.get(inst) != from_tier:
            continue
        area = area_by_instance.get(inst)
        if area is None or area <= 0:
            continue
        candidates.append(
            {
                "instance": inst,
                "area": area,
                "architecture_unit": row.get("architecture_unit", ""),
                "semantic_group": row.get("semantic_group", ""),
                "physical_only": is_physical_only(row),
            }
        )
    non_physical = [item for item in candidates if not item["physical_only"]]
    return non_physical or candidates


def evaluate_state(
    tiers: dict[str, str],
    area_by_instance: dict[str, float],
    net_to_instances: dict[str, list[str]],
    paths,
) -> dict[str, object]:
    tier0_area, tier1_area, tier0_fraction = area_stats(tiers, area_by_instance)
    crossing_nets, crossing_connections = crossing_stats(tiers, net_to_instances)
    pavg, pwst, total_transitions = path_metrics(paths, tiers)
    return {
        "tier0_area": tier0_area,
        "tier1_area": tier1_area,
        "tier0_area_fraction": tier0_fraction,
        "crossing_nets": crossing_nets,
        "crossing_connections_proxy": crossing_connections,
        "P_avg_cut": pavg,
        "P_wst_cut": pwst,
        "total_tier_transitions": total_transitions,
    }


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
    paths,
    area_lo: float,
    area_hi: float,
    max_cut_regret: float,
    max_pavg_regret: float,
    max_pwst_delta: float,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    current_tiers = dict(initial_tiers)
    baseline = evaluate_state(current_tiers, area_by_instance, net_to_instances, paths)
    from_tier, to_tier = move_direction(float(baseline["tier0_area_fraction"]), area_lo, area_hi)
    moves: list[dict[str, object]] = []
    guard_status = "not_needed"
    notes = ""

    if from_tier is None or to_tier is None:
        final = baseline
        restored_assignment = output_dir / policy / "restored_assignment.csv"
        write_assignment(restored_assignment, rows, fieldnames, current_tiers)
        summary = summary_row(
            design=design,
            policy=policy,
            status="already_feasible",
            initial_assignment=initial_assignment,
            restored_assignment=restored_assignment,
            baseline=baseline,
            final=final,
            area_lo=area_lo,
            area_hi=area_hi,
            moved_instances=0,
            total_moved_area=0.0,
            guard_status=guard_status,
            notes=notes,
        )
        return summary, moves

    required_shift = target_area_shift(float(baseline["tier0_area"]), float(baseline["tier1_area"]), area_lo, area_hi)
    candidates = collect_candidates(rows, current_tiers, area_by_instance, from_tier)
    if not candidates:
        final = baseline
        restored_assignment = output_dir / policy / "restored_assignment.csv"
        write_assignment(restored_assignment, rows, fieldnames, current_tiers)
        summary = summary_row(
            design=design,
            policy=policy,
            status="failed_no_candidates",
            initial_assignment=initial_assignment,
            restored_assignment=restored_assignment,
            baseline=baseline,
            final=final,
            area_lo=area_lo,
            area_hi=area_hi,
            moved_instances=0,
            total_moved_area=0.0,
            guard_status="failed_no_candidates",
            notes=f"required_area_shift={required_shift:.6f}",
        )
        return summary, moves

    def candidate_order(item: dict[str, object]) -> tuple[float, float]:
        area = float(item["area"])
        return (0 if area >= required_shift else 1, abs(area - required_shift))

    accepted_area = 0.0
    status = "failed_no_legal_move"
    guard_status = "failed_no_legal_move"
    max_rounds = min(10, len(candidates))

    for move_index in range(1, max_rounds + 1):
        current = evaluate_state(current_tiers, area_by_instance, net_to_instances, paths)
        if area_lo <= float(current["tier0_area_fraction"]) <= area_hi:
            status = "restored"
            guard_status = "pass"
            break

        current_required = target_area_shift(float(current["tier0_area"]), float(current["tier1_area"]), area_lo, area_hi)
        remaining = [item for item in candidates if current_tiers.get(str(item["instance"])) == from_tier]
        remaining.sort(key=lambda item: (0 if float(item["area"]) >= current_required else 1, abs(float(item["area"]) - current_required)))

        best: tuple[tuple[float, float, int], dict[str, object], dict[str, object], str, float, float, float] | None = None
        inspected = 0
        for item in remaining:
            inspected += 1
            if inspected > 2500:
                break
            inst = str(item["instance"])
            trial_tiers = dict(current_tiers)
            trial_tiers[inst] = to_tier
            trial = evaluate_state(trial_tiers, area_by_instance, net_to_instances, paths)
            trial_fraction = float(trial["tier0_area_fraction"])
            violation = area_violation(trial_fraction, area_lo, area_hi)
            area_pass = isinstance(violation, float) and violation == 0.0
            guard_ok = True
            reason = "area_pass" if area_pass else "area_window"
            cut_regret = finite_ratio(int(trial["crossing_nets"]) - int(baseline["crossing_nets"]), int(baseline["crossing_nets"]))
            pavg_regret = float(trial["P_avg_cut"]) - float(baseline["P_avg_cut"])
            pwst_delta = float(trial["P_wst_cut"]) - float(baseline["P_wst_cut"])
            if policy == "guarded":
                guard_ok, reason, cut_regret, pavg_regret, pwst_delta = guard_result(
                    baseline_crossing=int(baseline["crossing_nets"]),
                    final_crossing=int(trial["crossing_nets"]),
                    baseline_pavg=float(baseline["P_avg_cut"]),
                    final_pavg=float(trial["P_avg_cut"]),
                    baseline_pwst=int(baseline["P_wst_cut"]),
                    final_pwst=int(trial["P_wst_cut"]),
                    max_cut_regret=max_cut_regret,
                    max_pavg_regret=max_pavg_regret,
                    max_pwst_delta=max_pwst_delta,
                )
            legal = area_pass and (policy == "area_only" or guard_ok)
            if not legal:
                continue
            score = (
                abs(trial_fraction - (area_hi if from_tier == "tier0" else area_lo)),
                max(0.0, cut_regret),
                int(trial["crossing_nets"]),
            )
            if best is None or score < best[0]:
                best = (score, item, trial, reason, cut_regret, pavg_regret, pwst_delta)

        if best is None:
            guard_status = "failed_guard_or_area"
            break

        _, item, trial, reason, cut_regret, pavg_regret, pwst_delta = best
        inst = str(item["instance"])
        current_tiers[inst] = to_tier
        accepted_area += float(item["area"])
        moves.append(
            {
                "design": design,
                "policy": policy,
                "move_index": move_index,
                "instance": inst,
                "architecture_unit": item.get("architecture_unit", ""),
                "semantic_group": item.get("semantic_group", ""),
                "from_tier": from_tier,
                "to_tier": to_tier,
                "area": float(item["area"]),
                "tier0_area_fraction_after": trial["tier0_area_fraction"],
                "crossing_nets_after": trial["crossing_nets"],
                "cut_regret_after": cut_regret,
                "P_avg_cut_after": trial["P_avg_cut"],
                "P_avg_cut_regret_after": pavg_regret,
                "P_wst_cut_after": trial["P_wst_cut"],
                "P_wst_cut_delta_after": pwst_delta,
                "accepted": True,
                "reason": reason,
            }
        )

    final = evaluate_state(current_tiers, area_by_instance, net_to_instances, paths)
    final_violation = area_violation(float(final["tier0_area_fraction"]), area_lo, area_hi)
    if isinstance(final_violation, float) and final_violation == 0.0:
        if policy == "guarded":
            ok, reason, _, _, _ = guard_result(
                baseline_crossing=int(baseline["crossing_nets"]),
                final_crossing=int(final["crossing_nets"]),
                baseline_pavg=float(baseline["P_avg_cut"]),
                final_pavg=float(final["P_avg_cut"]),
                baseline_pwst=int(baseline["P_wst_cut"]),
                final_pwst=int(final["P_wst_cut"]),
                max_cut_regret=max_cut_regret,
                max_pavg_regret=max_pavg_regret,
                max_pwst_delta=max_pwst_delta,
            )
            status = "restored_guarded" if ok else "restored_area_only_guard_failed"
            guard_status = reason
        else:
            status = "restored_area_only"
            guard_status = "not_applied"
    elif status == "failed_no_legal_move":
        notes = f"required_area_shift={required_shift:.6f};candidate_count={len(candidates)}"

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
        moved_instances=len(moves),
        total_moved_area=accepted_area,
        guard_status=guard_status,
        notes=notes,
    )
    return summary, moves


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
) -> dict[str, object]:
    baseline_crossing = int(baseline["crossing_nets"])
    final_crossing = int(final["crossing_nets"])
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
        "baseline_crossing_connections_proxy": baseline["crossing_connections_proxy"],
        "final_crossing_connections_proxy": final["crossing_connections_proxy"],
        "crossing_connection_regret": finite_ratio(
            int(final["crossing_connections_proxy"]) - int(baseline["crossing_connections_proxy"]),
            int(baseline["crossing_connections_proxy"]),
        ),
        "baseline_P_avg_cut": baseline["P_avg_cut"],
        "final_P_avg_cut": final["P_avg_cut"],
        "P_avg_cut_regret": float(final["P_avg_cut"]) - float(baseline["P_avg_cut"]),
        "baseline_P_wst_cut": baseline["P_wst_cut"],
        "final_P_wst_cut": final["P_wst_cut"],
        "P_wst_cut_delta": float(final["P_wst_cut"]) - float(baseline["P_wst_cut"]),
        "moved_instances": moved_instances,
        "total_moved_area": total_moved_area,
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
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("results/scr1_core_tuned_baseline_feasibility_restoration"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("results/benchmark_summary/scr1_core_tuned_feasibility_restoration_summary.csv"),
    )
    parser.add_argument(
        "--moves-output",
        type=Path,
        default=Path("results/benchmark_summary/scr1_core_tuned_feasibility_restoration_moves.csv"),
    )
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
    from evaluation.evaluate_timing_path_cuts import load_assignment as load_path_assignment  # noqa: WPS433

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
        "baseline_P_avg_cut",
        "final_P_avg_cut",
        "P_avg_cut_regret",
        "baseline_P_wst_cut",
        "final_P_wst_cut",
        "P_wst_cut_delta",
        "moved_instances",
        "total_moved_area",
        "guard_status",
        "notes",
    ]
    move_fields = [
        "design",
        "policy",
        "move_index",
        "instance",
        "architecture_unit",
        "semantic_group",
        "from_tier",
        "to_tier",
        "area",
        "tier0_area_fraction_after",
        "crossing_nets_after",
        "cut_regret_after",
        "P_avg_cut_after",
        "P_avg_cut_regret_after",
        "P_wst_cut_after",
        "P_wst_cut_delta_after",
        "accepted",
        "reason",
    ]
    write_csv(args.summary_output, summary_rows, summary_fields)
    write_csv(args.moves_output, move_rows, move_fields)

    print(args.summary_output)
    print(args.moves_output)
    for row in summary_rows:
        print(
            "{policy}: status={status} final_tier0={tier0} moves={moves} guard={guard}".format(
                policy=row["policy"],
                status=row["status"],
                tier0=format_value(row["final_tier0_area_fraction"]),
                moves=row["moved_instances"],
                guard=row["guard_status"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
