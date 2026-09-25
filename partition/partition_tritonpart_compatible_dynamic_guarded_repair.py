#!/usr/bin/env python3
"""Dynamic TritonPart-compatible ASA guarded refinement.

This is the next-step version after the Phase-2 trace-filter prototype.  It no
longer uses an old local-refinement trace or old per-move gains.  At every
iteration it recomputes candidate gains from the current assignment, checks the
same TritonPart-compatible guards, accepts the best legal move, and repeats.

The dynamic objective is intentionally lightweight and transparent:

* affected crossing nets are scored by architecture/scenario, physical, and
  timing context risk;
* the guard preserves OpenROAD-style area balance;
* raw cut regret and timing-path cut metrics are bounded against the native
  timing-aware TritonPart starting point.

It is a paper-facing prototype for constrained local refinement, not a signoff
3D physical-design tool.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
STD_CELL_RE = re.compile(r"\((sky130[^)]*|[A-Za-z0-9_]+__[^)]*)\)")
EDGE_MARKERS = {"^", "v", "r", "f"}


@dataclass
class TimingPath:
    index: int
    instances: list[str]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
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


def normalize_name(name: str) -> str:
    out = name.strip()
    if out.startswith("\\"):
        out = out[1:]
    return out


def parse_nets_field(value: str) -> list[str]:
    value = (value or "").strip().strip("[]")
    if not value:
        return []
    for sep in [";", "|", ","]:
        if sep in value:
            return [part.strip().strip("'\"") for part in value.split(sep) if part.strip().strip("'\"")]
    return [value.strip("'\"")]


def as_float(value: str | None) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def load_assignment(path: Path) -> tuple[list[dict[str, str]], dict[str, str], dict[str, int], dict[str, str], dict[str, str]]:
    rows = read_csv(path)
    tier: dict[str, str] = {}
    weight: dict[str, int] = {}
    arch_unit: dict[str, str] = {}
    semantic_group: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        tier[inst] = row["tier"]
        weight[inst] = int(float(row.get("weight", "1") or "1"))
        arch_unit[inst] = row.get("architecture_unit", "unclassified") or "unclassified"
        semantic_group[inst] = row.get("semantic_group", "infrastructure") or "infrastructure"
    return rows, tier, weight, arch_unit, semantic_group


def load_aliases(rows: list[dict[str, str]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        variants = {
            inst,
            inst.replace("\\[", "[").replace("\\]", "]"),
            inst.replace("[", "\\[").replace("]", "\\]"),
            inst.replace("/", "."),
            inst.replace(".", "/"),
        }
        for alias in variants:
            aliases[normalize_name(alias)] = inst
    return aliases


def load_area(path: Path) -> dict[str, int]:
    area: dict[str, int] = {}
    for row in read_csv(path):
        if row.get("status", "unique") != "unique":
            continue
        inst = normalize_name(row.get("variant") or row.get("instance") or row.get("canonical_instance", ""))
        if inst:
            area[inst] = int(float(row["area"]))
    return area


def load_context_scores(path: Path, score_names: list[str]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for row in read_csv(path):
        inst = normalize_name(row.get("instance", ""))
        if not inst:
            continue
        value = 0.0
        for name in score_names:
            if row.get(name) not in (None, ""):
                value = as_float(row.get(name))
                break
        scores[inst] = value
    return scores


def load_net_maps(features_dir: Path, assignment_instances: set[str]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    rows = read_csv(features_dir / "instance_features.csv")
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    inst_to_nets: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = normalize_name(row["instance"])
        if inst not in assignment_instances:
            continue
        for net in parse_nets_field(row.get("nets", "")):
            net_to_instances[net].append(inst)
            inst_to_nets[inst].append(net)
    net_to_instances = {net: insts for net, insts in net_to_instances.items() if len(insts) > 1}
    inst_to_nets = {
        inst: [net for net in nets if net in net_to_instances]
        for inst, nets in inst_to_nets.items()
        if any(net in net_to_instances for net in nets)
    }
    return net_to_instances, inst_to_nets


def scenario_unit_weight(unit: str, group: str, scenario: str) -> float:
    if scenario == "state_and_clock_protected":
        if unit == "clock_reset":
            return 8.0
        if unit == "pipeline_state":
            return 6.0
        if unit in {"csr", "trap_debug"}:
            return 4.0
        if group == "control":
            return 2.0
        if group == "datapath":
            return 1.5
        return 1.0
    if scenario == "memory_near_logic":
        if unit in {"register_file", "load_store"}:
            return 7.0
        if unit in {"execute_alu", "multdiv"}:
            return 3.0
        if group == "datapath":
            return 2.0
        return 1.0
    if scenario == "control_datapath_split":
        if group in {"control", "datapath"}:
            return 3.0
        return 1.0
    return 1.0


def instance_risk(
    inst: str,
    scenario: str,
    arch_unit: dict[str, str],
    semantic_group: dict[str, str],
    physical_scores: dict[str, float],
    timing_scores: dict[str, float],
) -> float:
    unit = arch_unit.get(inst, "unclassified")
    group = semantic_group.get(inst, "infrastructure")
    return (
        scenario_unit_weight(unit, group, scenario)
        + physical_scores.get(inst, 0.0)
        + 2.0 * timing_scores.get(inst, 0.0)
    )


def net_counts(tier: dict[str, str], insts: list[str]) -> tuple[int, int]:
    c0 = sum(1 for inst in insts if tier.get(inst) == "tier0")
    c1 = sum(1 for inst in insts if tier.get(inst) == "tier1")
    return c0, c1


def net_cost(tier: dict[str, str], insts: list[str], risk: dict[str, float]) -> float:
    c0, c1 = net_counts(tier, insts)
    if not c0 or not c1:
        return 0.0
    risk_sum = sum(risk.get(inst, 1.0) for inst in insts)
    return min(c0, c1) * risk_sum / max(1, len(insts))


def total_objective(tier: dict[str, str], net_to_instances: dict[str, list[str]], risk: dict[str, float]) -> float:
    return sum(net_cost(tier, insts, risk) for insts in net_to_instances.values())


def crossing_stats(tier: dict[str, str], net_to_instances: dict[str, list[str]]) -> tuple[int, int]:
    crossing_nets = 0
    crossing_connections = 0
    for insts in net_to_instances.values():
        c0, c1 = net_counts(tier, insts)
        if c0 and c1:
            crossing_nets += 1
            crossing_connections += min(c0, c1)
    return crossing_nets, crossing_connections


def area_stats(tier: dict[str, str], area: dict[str, int]) -> dict[str, float]:
    part_area = {"tier0": 0, "tier1": 0}
    matched = 0
    unmatched = 0
    for inst, part in tier.items():
        value = area.get(inst)
        if value is None:
            unmatched += 1
            continue
        matched += 1
        part_area[part] += value
    total = part_area["tier0"] + part_area["tier1"]
    lo = min(part_area["tier0"], part_area["tier1"])
    hi = max(part_area["tier0"], part_area["tier1"])
    return {
        "tier0_area": float(part_area["tier0"]),
        "tier1_area": float(part_area["tier1"]),
        "tier0_area_fraction": part_area["tier0"] / total if total else 0.0,
        "tier1_area_fraction": part_area["tier1"] / total if total else 0.0,
        "area_weight_balance": lo / hi if hi else 0.0,
        "matched_instances": float(matched),
        "unmatched_instances": float(unmatched),
    }


def area_pass(stats: dict[str, float], lo: float, hi: float) -> bool:
    return lo <= stats["tier0_area_fraction"] <= hi


def strip_numeric_columns(line: str) -> str:
    parts = line.strip().split()
    while parts and FLOAT_RE.fullmatch(parts[0]):
        parts.pop(0)
    while parts and parts[0] in EDGE_MARKERS:
        parts.pop(0)
    return " ".join(parts)


def candidate_from_description(desc: str) -> str | None:
    if not desc:
        return None
    if desc.startswith(("clock ", "data ", "library ", "external ", "input ", "output ", "#")):
        return None
    if "slack" in desc or "arrival" in desc or "required" in desc or "uncertainty" in desc:
        return None
    if STD_CELL_RE.search(desc):
        desc = STD_CELL_RE.sub("", desc).strip()
    parts = desc.split()
    while parts and parts[0] in EDGE_MARKERS:
        parts.pop(0)
    if not parts:
        return None
    token = parts[0].strip(",").lstrip("^v")
    if "/" not in token:
        return None
    return normalize_name(token.rsplit("/", 1)[0])


def resolve_instance(token: str, aliases: dict[str, str]) -> str | None:
    token = normalize_name(token)
    candidates = [
        token,
        token.replace("\\[", "[").replace("\\]", "]"),
        token.replace("[", "\\[").replace("]", "\\]"),
        token.replace("/", "."),
        token.replace(".", "/"),
    ]
    for cand in candidates:
        if cand in aliases:
            return aliases[cand]
    suffix = token.split("/")[-1].split(".")[-1]
    if suffix:
        matches = sorted({inst for alias, inst in aliases.items() if alias.endswith(suffix)})
        if len(matches) == 1:
            return matches[0]
    return None


def finish_timing_path(raw_instances: list[str], aliases: dict[str, str], index: int) -> TimingPath:
    instances = []
    for token in list(dict.fromkeys(raw_instances)):
        inst = resolve_instance(token, aliases)
        if inst:
            instances.append(inst)
    return TimingPath(index=index, instances=list(dict.fromkeys(instances)))


def parse_timing_paths(report: Path, aliases: dict[str, str], max_paths: int) -> list[TimingPath]:
    paths: list[TimingPath] = []
    current: list[str] | None = None
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Startpoint:"):
            if current is not None:
                paths.append(finish_timing_path(current, aliases, len(paths)))
                if len(paths) >= max_paths:
                    return paths
            current = []
            continue
        if current is None:
            continue
        token = candidate_from_description(strip_numeric_columns(line))
        if token:
            current.append(token)
    if current is not None and len(paths) < max_paths:
        paths.append(finish_timing_path(current, aliases, len(paths)))
    return paths


def transition_count(path: TimingPath, tier: dict[str, str]) -> int:
    seq = [inst for inst in path.instances if inst in tier]
    return sum(1 for a, b in zip(seq, seq[1:]) if tier[a] != tier[b])


def path_cut_stats(paths: list[TimingPath], tier: dict[str, str]) -> dict[str, float]:
    if not paths:
        return {"P_avg_cut": 0.0, "P_wst_cut": 0.0, "total_tier_transitions": 0.0}
    transitions = [transition_count(path, tier) for path in paths]
    return {
        "P_avg_cut": sum(transitions) / len(paths),
        "P_wst_cut": float(max(transitions) if transitions else 0),
        "total_tier_transitions": float(sum(transitions)),
    }


def build_inst_to_paths(paths: list[TimingPath]) -> dict[str, list[int]]:
    inst_to_paths: dict[str, list[int]] = defaultdict(list)
    for index, path in enumerate(paths):
        for inst in set(path.instances):
            inst_to_paths[inst].append(index)
    return inst_to_paths


def affected_path_stats(
    paths: list[TimingPath],
    path_transition: list[int],
    affected_indices: list[int],
    tier: dict[str, str],
) -> tuple[float, float, float]:
    if not paths:
        return 0.0, 0.0, 0.0
    total = sum(path_transition)
    worst = max(path_transition) if path_transition else 0
    for idx in affected_indices:
        old = path_transition[idx]
        new = transition_count(paths[idx], tier)
        total += new - old
    if affected_indices and worst in [path_transition[idx] for idx in affected_indices]:
        new_transitions = list(path_transition)
        for idx in affected_indices:
            new_transitions[idx] = transition_count(paths[idx], tier)
        worst = max(new_transitions) if new_transitions else 0
    else:
        for idx in affected_indices:
            worst = max(worst, transition_count(paths[idx], tier))
    return total / len(paths), float(worst), float(total)


def assignment_rows(rows: list[dict[str, str]], tier: dict[str, str]) -> list[dict[str, str]]:
    out = []
    for row in rows:
        item = dict(row)
        item["tier"] = tier[normalize_name(row["instance"])]
        out.append(item)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--initial-assignment", type=Path, required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--instance-area", type=Path, required=True)
    parser.add_argument("--timing-report", type=Path, required=True)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--max-iterations", type=int, default=500)
    parser.add_argument("--max-cut-regret", type=float, default=0.05)
    parser.add_argument("--max-pavg-regret", type=float, default=0.0)
    parser.add_argument("--max-pwst-delta", type=float, default=0.0)
    parser.add_argument("--area-lo", type=float, default=0.48)
    parser.add_argument("--area-hi", type=float, default=0.52)
    parser.add_argument(
        "--architecture-off",
        action="store_true",
        help="Disable recovered architecture semantics in the dynamic objective; physical and timing context remain enabled.",
    )
    parser.add_argument(
        "--progress-every-candidates",
        type=int,
        default=500,
        help="Print a heartbeat while scanning candidates. Use 0 to disable candidate-scan progress.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, tier, _weight, arch_unit, semantic_group = load_assignment(args.initial_assignment)
    architecture_mode = "architecture_off" if args.architecture_off else "architecture_on"
    if args.architecture_off:
        arch_unit = {inst: "unclassified" for inst in tier}
        semantic_group = {inst: "infrastructure" for inst in tier}
    aliases = load_aliases(rows)
    area = load_area(args.instance_area)
    net_to_instances, inst_to_nets = load_net_maps(args.features_dir, set(tier))
    physical = load_context_scores(
        args.features_dir / "physical_context_scores.csv",
        ["physical_context_score", "raw_physical_score", "mean_physical_context_score"],
    )
    timing = load_context_scores(
        args.features_dir / "timing_context_scores.csv",
        ["timing_context_score", "mean_timing_context_score"],
    )
    risk = {
        inst: instance_risk(inst, args.scenario, arch_unit, semantic_group, physical, timing)
        for inst in tier
    }

    paths = parse_timing_paths(args.timing_report, aliases, args.max_paths)
    inst_to_paths = build_inst_to_paths(paths)
    path_transition = [transition_count(path, tier) for path in paths]

    baseline_crossing, baseline_conn = crossing_stats(tier, net_to_instances)
    baseline_area = area_stats(tier, area)
    baseline_paths = path_cut_stats(paths, tier)
    baseline_objective = total_objective(tier, net_to_instances, risk)

    accepted_rows: list[dict[str, object]] = []
    rejected_no_legal = 0
    cumulative_gain = 0.0
    current_objective = baseline_objective

    candidate_pool = sorted(inst for inst in tier if inst_to_nets.get(inst))
    print(
        "dynamic_guarded_repair_start "
        f"design={args.design} scenario={args.scenario} "
        f"architecture_mode={architecture_mode} "
        f"instances={len(tier)} candidates={len(candidate_pool)} "
        f"paths={len(paths)} baseline_crossing={baseline_crossing} "
        f"baseline_objective={baseline_objective:.6f}",
        flush=True,
    )

    for iteration in range(1, args.max_iterations + 1):
        iteration_start = time.time()
        best: dict[str, object] | None = None
        scanned = 0
        legal = 0
        rejected_area = 0
        rejected_gain = 0
        rejected_cut = 0
        rejected_path = 0
        print(
            f"iteration {iteration}/{args.max_iterations}: scanning {len(candidate_pool)} candidates",
            flush=True,
        )
        for inst in candidate_pool:
            scanned += 1
            if args.progress_every_candidates and scanned % args.progress_every_candidates == 0:
                best_gain = float(best["objective_delta"]) if best is not None else 0.0
                print(
                    f"  iteration {iteration}: scanned={scanned}/{len(candidate_pool)} "
                    f"legal={legal} best_gain={best_gain:.6f} "
                    f"reject_area={rejected_area} reject_gain={rejected_gain} "
                    f"reject_cut={rejected_cut} reject_path={rejected_path}",
                    flush=True,
                )
            old_tier = tier[inst]
            new_tier = "tier1" if old_tier == "tier0" else "tier0"

            tier[inst] = new_tier
            astats = area_stats(tier, area)
            if not area_pass(astats, args.area_lo, args.area_hi):
                tier[inst] = old_tier
                rejected_area += 1
                continue

            affected_nets = inst_to_nets.get(inst, [])
            objective_delta = 0.0
            for net in affected_nets:
                insts = net_to_instances[net]
                tier[inst] = old_tier
                old_cost = net_cost(tier, insts, risk)
                tier[inst] = new_tier
                new_cost = net_cost(tier, insts, risk)
                objective_delta += old_cost - new_cost
            if objective_delta <= 1e-12:
                tier[inst] = old_tier
                rejected_gain += 1
                continue

            crossing, conn = crossing_stats(tier, net_to_instances)
            cut_regret = (crossing - baseline_crossing) / baseline_crossing if baseline_crossing else 0.0
            if cut_regret > args.max_cut_regret:
                tier[inst] = old_tier
                rejected_cut += 1
                continue

            affected_paths = inst_to_paths.get(inst, [])
            pavg, pwst, total_transitions = affected_path_stats(paths, path_transition, affected_paths, tier)
            pavg_regret = (
                (pavg - baseline_paths["P_avg_cut"]) / baseline_paths["P_avg_cut"]
                if baseline_paths["P_avg_cut"]
                else 0.0
            )
            pwst_delta = pwst - baseline_paths["P_wst_cut"]
            if pavg_regret > args.max_pavg_regret or pwst_delta > args.max_pwst_delta:
                tier[inst] = old_tier
                rejected_path += 1
                continue

            legal += 1
            if best is None or objective_delta > float(best["objective_delta"]):
                best = {
                    "instance": inst,
                    "from_tier": old_tier,
                    "to_tier": new_tier,
                    "objective_delta": objective_delta,
                    "crossing_nets_after": crossing,
                    "crossing_connections_after": conn,
                    "cut_regret_after": cut_regret,
                    "tier0_area_fraction_after": astats["tier0_area_fraction"],
                    "area_weight_balance_after": astats["area_weight_balance"],
                    "P_avg_cut_after": pavg,
                    "P_avg_cut_regret_after": pavg_regret,
                    "P_wst_cut_after": pwst,
                    "P_wst_cut_delta_after": pwst_delta,
                    "total_tier_transitions_after": total_transitions,
                }
            tier[inst] = old_tier

        if best is None:
            rejected_no_legal += 1
            print(
                f"iteration {iteration}: stop no legal move "
                f"scanned={scanned} legal={legal} "
                f"reject_area={rejected_area} reject_gain={rejected_gain} "
                f"reject_cut={rejected_cut} reject_path={rejected_path} "
                f"elapsed_s={time.time() - iteration_start:.1f}",
                flush=True,
            )
            break

        inst = str(best["instance"])
        tier[inst] = str(best["to_tier"])
        for idx in inst_to_paths.get(inst, []):
            path_transition[idx] = transition_count(paths[idx], tier)
        gain = float(best["objective_delta"])
        cumulative_gain += gain
        current_objective -= gain
        accepted_rows.append(
            {
                "iteration": iteration,
                "instance": inst,
                "architecture_unit": arch_unit.get(inst, ""),
                "semantic_group": semantic_group.get(inst, ""),
                "from_tier": best["from_tier"],
                "to_tier": best["to_tier"],
                "objective_delta": f"{gain:.6f}",
                "objective_after": f"{current_objective:.6f}",
                "crossing_nets_after": best["crossing_nets_after"],
                "cut_regret_after": f"{float(best['cut_regret_after']):.6f}",
                "tier0_area_fraction_after": f"{float(best['tier0_area_fraction_after']):.6f}",
                "P_avg_cut_after": f"{float(best['P_avg_cut_after']):.6f}",
                "P_wst_cut_after": f"{float(best['P_wst_cut_after']):.6f}",
                "scanned_candidates": scanned,
                "legal_candidates": legal,
                "rejected_area_candidates": rejected_area,
                "rejected_gain_candidates": rejected_gain,
                "rejected_cut_candidates": rejected_cut,
                "rejected_path_candidates": rejected_path,
            }
        )
        print(
            f"iteration {iteration}: accepted instance={inst} "
            f"gain={gain:.6f} objective_after={current_objective:.6f} "
            f"crossing={best['crossing_nets_after']} "
            f"cut_regret={float(best['cut_regret_after']):.6f} "
            f"area_tier0={float(best['tier0_area_fraction_after']):.6f} "
            f"P_avg={float(best['P_avg_cut_after']):.6f} "
            f"P_wst={float(best['P_wst_cut_after']):.6f} "
            f"legal={legal} elapsed_s={time.time() - iteration_start:.1f}",
            flush=True,
        )

    final_crossing, final_conn = crossing_stats(tier, net_to_instances)
    final_area = area_stats(tier, area)
    final_paths = path_cut_stats(paths, tier)
    final_objective = total_objective(tier, net_to_instances, risk)

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    assignment_path = output / "tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
    trace_path = output / "tritonpart_compatible_dynamic_guarded_repair_trace.csv"
    summary_path = output / "tritonpart_compatible_dynamic_guarded_repair_summary.csv"

    write_csv(assignment_path, assignment_rows(rows, tier), list(rows[0].keys()))
    write_csv(
        trace_path,
        accepted_rows,
        [
            "iteration",
            "instance",
            "architecture_unit",
            "semantic_group",
            "from_tier",
            "to_tier",
            "objective_delta",
            "objective_after",
            "crossing_nets_after",
            "cut_regret_after",
            "tier0_area_fraction_after",
            "P_avg_cut_after",
            "P_wst_cut_after",
            "scanned_candidates",
            "legal_candidates",
            "rejected_area_candidates",
            "rejected_gain_candidates",
            "rejected_cut_candidates",
            "rejected_path_candidates",
        ],
    )
    write_csv(
        summary_path,
        [
            {
                "design": args.design,
                "scenario": args.scenario,
                "architecture_mode": architecture_mode,
                "baseline_objective": f"{baseline_objective:.6f}",
                "final_objective": f"{final_objective:.6f}",
                "objective_reduction": f"{(baseline_objective - final_objective) / baseline_objective if baseline_objective else 0.0:.6f}",
                "baseline_crossing_nets": baseline_crossing,
                "final_crossing_nets": final_crossing,
                "cut_regret": f"{(final_crossing - baseline_crossing) / baseline_crossing if baseline_crossing else 0.0:.6f}",
                "baseline_crossing_connections_proxy": baseline_conn,
                "final_crossing_connections_proxy": final_conn,
                "crossing_connection_regret": f"{(final_conn - baseline_conn) / baseline_conn if baseline_conn else 0.0:.6f}",
                "initial_area_balance_pass": str(area_pass(baseline_area, args.area_lo, args.area_hi)).lower(),
                "final_area_balance_pass": str(area_pass(final_area, args.area_lo, args.area_hi)).lower(),
                "final_area_weight_balance": f"{final_area['area_weight_balance']:.6f}",
                "final_tier0_area_fraction": f"{final_area['tier0_area_fraction']:.6f}",
                "baseline_P_avg_cut": f"{baseline_paths['P_avg_cut']:.6f}",
                "final_P_avg_cut": f"{final_paths['P_avg_cut']:.6f}",
                "P_avg_cut_regret": f"{(final_paths['P_avg_cut'] - baseline_paths['P_avg_cut']) / baseline_paths['P_avg_cut'] if baseline_paths['P_avg_cut'] else 0.0:.6f}",
                "baseline_P_wst_cut": f"{baseline_paths['P_wst_cut']:.6f}",
                "final_P_wst_cut": f"{final_paths['P_wst_cut']:.6f}",
                "P_wst_cut_delta": f"{final_paths['P_wst_cut'] - baseline_paths['P_wst_cut']:.6f}",
                "accepted_moves": len(accepted_rows),
                "stopped_no_legal_move": str(rejected_no_legal > 0).lower(),
                "cumulative_dynamic_gain": f"{cumulative_gain:.6f}",
                "assignment_file": str(assignment_path),
            }
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
