#!/usr/bin/env python3
"""Path-aware guarded repair over an existing ASA-RV3D assignment.

This script is a downstream-validation branch for the paper plan.  It starts
from the current timing-regret ASA-RV3D result and performs conservative local
moves that reduce tier transitions on OpenSTA critical paths while preserving
balance and limiting net-crossing side effects.

It does not replace the main TritonPart + ASA-RV3D result.  It is intended to
test whether an additional path-continuity guard can recover downstream timing
benefit when net-level timing-weighted crossing is not enough.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path


SCENARIOS = [
    "control_datapath_split",
    "memory_near_logic",
    "state_and_clock_protected",
]
FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
STD_CELL_RE = re.compile(r"\((sky130[^)]*|[A-Za-z0-9_]+__[^)]*)\)")
EDGE_MARKERS = {"^", "v", "r", "f"}


@dataclass
class TimingPath:
    index: int
    startpoint: str
    endpoint: str
    slack: float | None
    instances: list[str]
    weight: float


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


def normalize_name(name: str) -> str:
    name = name.strip()
    if name.startswith("\\"):
        name = name[1:]
    return name


def default_start_assignment(design: str, scenario: str) -> Path:
    return (
        Path("results")
        / f"{design}_tritonpart_timing_regret_guarded_repair"
        / scenario
        / "tritonpart_timing_regret_guarded_repair_assignment.csv"
    )


def default_output_dir(design: str, scenario: str) -> Path:
    return Path("results") / f"{design}_tritonpart_path_aware_guarded_repair" / scenario


def load_assignment(path: Path) -> tuple[list[dict[str, str]], dict[str, str], dict[str, int], dict[str, str]]:
    rows = read_csv(path)
    tier: dict[str, str] = {}
    weight: dict[str, int] = {}
    aliases: dict[str, str] = {}
    for row in rows:
        inst = normalize_name(row["instance"])
        tier[inst] = row["tier"]
        weight[inst] = int(float(row.get("weight", "1") or "1"))
        for alias in {
            inst,
            inst.replace("\\[", "[").replace("\\]", "]"),
            inst.replace("[", "\\[").replace("]", "\\]"),
            inst.replace("/", "."),
            inst.replace(".", "/"),
        }:
            aliases[normalize_name(alias)] = inst
    return rows, tier, weight, aliases


def balance_ratio(tier: dict[str, str], weight: dict[str, int]) -> tuple[float, float]:
    tier0 = sum(1 for t in tier.values() if t == "tier0")
    tier1 = sum(1 for t in tier.values() if t == "tier1")
    w0 = sum(weight[i] for i, t in tier.items() if t == "tier0")
    w1 = sum(weight[i] for i, t in tier.items() if t == "tier1")
    inst_ratio = min(tier0, tier1) / max(tier0, tier1) if tier0 and tier1 else 0.0
    weight_ratio = min(w0, w1) / max(w0, w1) if w0 and w1 else 0.0
    return inst_ratio, weight_ratio


def parse_nets_field(value: str) -> list[str]:
    value = (value or "").strip()
    if not value:
        return []
    value = value.strip("[]")
    for sep in [";", "|"]:
        if sep in value:
            return [x.strip().strip("'\"") for x in value.split(sep) if x.strip().strip("'\"")]
    # Most RV3D feature files store whitespace-safe net names.  Comma is risky
    # because some net names contain punctuation, but it is still useful here.
    if "," in value:
        return [x.strip().strip("'\"") for x in value.split(",") if x.strip().strip("'\"")]
    return [value.strip("'\"")]


def load_net_to_instances(features_dir: Path, assignment_instances: set[str]) -> dict[str, list[str]]:
    path = features_dir / "instance_features.csv"
    rows = read_csv(path)
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        inst = normalize_name(row["instance"])
        if inst not in assignment_instances:
            continue
        for net in parse_nets_field(row.get("nets", "")):
            net_to_instances[net].append(inst)
    return {net: insts for net, insts in net_to_instances.items() if len(insts) > 1}


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


def finish_path(raw: dict[str, object], aliases: dict[str, str], index: int, max_paths: int) -> TimingPath:
    raw_instances = list(dict.fromkeys(raw["instances"]))  # type: ignore[arg-type]
    instances: list[str] = []
    for token in raw_instances:
        inst = resolve_instance(str(token), aliases)
        if inst:
            instances.append(inst)
    # Rank-weighted criticality.  Top paths matter more, but lower-ranked paths
    # still influence the guard.
    rank_weight = (max_paths - index) / max_paths if max_paths > 0 else 1.0
    return TimingPath(
        index=index,
        startpoint=str(raw.get("startpoint", "")),
        endpoint=str(raw.get("endpoint", "")),
        slack=raw.get("slack"),  # type: ignore[arg-type]
        instances=list(dict.fromkeys(instances)),
        weight=max(0.05, rank_weight),
    )


def parse_timing_paths(report: Path, aliases: dict[str, str], max_paths: int) -> list[TimingPath]:
    paths: list[TimingPath] = []
    current: dict[str, object] | None = None
    for line in report.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Startpoint:"):
            if current is not None:
                paths.append(finish_path(current, aliases, len(paths), max_paths))
                if len(paths) >= max_paths:
                    return paths
            current = {"startpoint": line.split("Startpoint:", 1)[1].strip(), "endpoint": "", "slack": None, "instances": []}
            continue
        if current is None:
            continue
        if line.startswith("Endpoint:"):
            current["endpoint"] = line.split("Endpoint:", 1)[1].strip()
            continue
        if " slack " in f" {line} " or line.strip().endswith(" slack (VIOLATED)") or line.strip().endswith(" slack (MET)"):
            nums = FLOAT_RE.findall(line)
            if nums:
                current["slack"] = float(nums[-1])
            continue
        token = candidate_from_description(strip_numeric_columns(line))
        if token:
            current["instances"].append(token)  # type: ignore[index]
    if current is not None and len(paths) < max_paths:
        paths.append(finish_path(current, aliases, len(paths), max_paths))
    return paths


def build_path_edges(paths: list[TimingPath]) -> dict[tuple[str, str], float]:
    edge_weight: dict[tuple[str, str], float] = defaultdict(float)
    for path in paths:
        seq = path.instances
        for a, b in zip(seq, seq[1:]):
            if a == b:
                continue
            edge = tuple(sorted((a, b)))
            edge_weight[edge] += path.weight
    return dict(edge_weight)


def path_transition_cost(tier: dict[str, str], edge_weight: dict[tuple[str, str], float]) -> float:
    return sum(w for (a, b), w in edge_weight.items() if tier.get(a) and tier.get(b) and tier[a] != tier[b])


def path_transition_count(path: TimingPath, tier: dict[str, str]) -> int:
    seq = [inst for inst in path.instances if inst in tier]
    return sum(1 for a, b in zip(seq, seq[1:]) if tier[a] != tier[b])


def build_instance_to_paths(paths: list[TimingPath]) -> dict[str, list[int]]:
    inst_to_paths: dict[str, list[int]] = defaultdict(list)
    for idx, path in enumerate(paths):
        for inst in set(path.instances):
            inst_to_paths[inst].append(idx)
    return inst_to_paths


def crossing_connection_proxy(tier: dict[str, str], net_to_instances: dict[str, list[str]]) -> int:
    total = 0
    for insts in net_to_instances.values():
        c0 = sum(1 for inst in insts if tier.get(inst) == "tier0")
        c1 = sum(1 for inst in insts if tier.get(inst) == "tier1")
        if c0 and c1:
            total += min(c0, c1)
    return total


def delta_path_cost(inst: str, tier: dict[str, str], incident: dict[str, list[tuple[str, float]]]) -> float:
    old_tier = tier[inst]
    new_tier = "tier1" if old_tier == "tier0" else "tier0"
    delta = 0.0
    for other, weight in incident.get(inst, []):
        other_tier = tier.get(other)
        if not other_tier:
            continue
        old_cross = old_tier != other_tier
        new_cross = new_tier != other_tier
        delta += (1 if new_cross else 0) * weight - (1 if old_cross else 0) * weight
    return delta


def delta_path_crossing_stats(
    inst: str,
    tier: dict[str, str],
    paths: list[TimingPath],
    inst_to_paths: dict[str, list[int]],
) -> tuple[int, int]:
    old_tier = tier[inst]
    new_tier = "tier1" if old_tier == "tier0" else "tier0"
    crossing_delta = 0
    transition_delta = 0
    for path_idx in inst_to_paths.get(inst, []):
        path = paths[path_idx]
        old_count = path_transition_count(path, tier)
        tier[inst] = new_tier
        new_count = path_transition_count(path, tier)
        tier[inst] = old_tier
        crossing_delta += (1 if new_count > 0 else 0) - (1 if old_count > 0 else 0)
        transition_delta += new_count - old_count
    return crossing_delta, transition_delta


def delta_net_proxy(inst: str, tier: dict[str, str], inst_to_nets: dict[str, list[str]], net_to_instances: dict[str, list[str]]) -> int:
    old_tier = tier[inst]
    new_tier = "tier1" if old_tier == "tier0" else "tier0"
    delta = 0
    for net in inst_to_nets.get(inst, []):
        insts = net_to_instances[net]
        c0 = sum(1 for x in insts if tier.get(x) == "tier0")
        c1 = sum(1 for x in insts if tier.get(x) == "tier1")
        old_cost = min(c0, c1) if c0 and c1 else 0
        if old_tier == "tier0":
            c0 -= 1
            c1 += 1
        else:
            c1 -= 1
            c0 += 1
        new_cost = min(c0, c1) if c0 and c1 else 0
        delta += new_cost - old_cost
    return delta


def summarize_paths(tier: dict[str, str], paths: list[TimingPath]) -> dict[str, object]:
    crossing = 0
    transitions: list[int] = []
    for path in paths:
        seq = [inst for inst in path.instances if inst in tier]
        count = sum(1 for a, b in zip(seq, seq[1:]) if tier[a] != tier[b])
        transitions.append(count)
        if count:
            crossing += 1
    total = len(paths)
    return {
        "path_count": total,
        "crossing_path_count": crossing,
        "crossing_path_fraction": f"{crossing / total:.6f}" if total else "0.000000",
        "mean_tier_transitions": f"{sum(transitions) / total:.6f}" if total else "0.000000",
        "max_tier_transitions": max(transitions) if transitions else 0,
    }


def format_assignment_rows(rows: list[dict[str, str]], tier: dict[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        inst = normalize_name(row["instance"])
        new_row = dict(row)
        new_row["tier"] = tier[inst]
        out.append(new_row)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--scenario", required=True, choices=SCENARIOS)
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--start-assignment", type=Path)
    parser.add_argument("--timing-report", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--max-moves", type=int, default=500)
    parser.add_argument("--min-instance-balance", type=float, default=0.90)
    parser.add_argument("--min-weight-balance", type=float, default=0.90)
    parser.add_argument("--net-regret-weight", type=float, default=0.02)
    parser.add_argument("--max-net-regret", type=int, default=80)
    parser.add_argument("--min-path-gain", type=float, default=0.10)
    parser.add_argument("--path-crossing-weight", type=float, default=25.0)
    parser.add_argument("--path-transition-weight", type=float, default=1.0)
    parser.add_argument("--enable-path-block-moves", action="store_true")
    parser.add_argument("--max-path-block-size", type=int, default=80)
    parser.add_argument("--path-block-passes", type=int, default=3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    features_dir = args.features_dir or Path("results") / f"{args.design}_features"
    start_assignment = args.start_assignment or default_start_assignment(args.design, args.scenario)
    timing_report = args.timing_report or Path("results") / "timing_reports" / f"{args.design}_report_checks_max.rpt"
    output_dir = args.output_dir or default_output_dir(args.design, args.scenario)

    rows, tier, weight, aliases = load_assignment(start_assignment)
    original_tier = dict(tier)
    initial_instance_balance, initial_weight_balance = balance_ratio(tier, weight)
    effective_min_instance = args.min_instance_balance if initial_instance_balance >= args.min_instance_balance else initial_instance_balance
    effective_min_weight = args.min_weight_balance if initial_weight_balance >= args.min_weight_balance else initial_weight_balance

    net_to_instances = load_net_to_instances(features_dir, set(tier))
    inst_to_nets: dict[str, list[str]] = defaultdict(list)
    for net, insts in net_to_instances.items():
        for inst in insts:
            inst_to_nets[inst].append(net)

    paths = parse_timing_paths(timing_report, aliases, args.max_paths)
    edge_weight = build_path_edges(paths)
    inst_to_paths = build_instance_to_paths(paths)
    incident: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for (a, b), w in edge_weight.items():
        incident[a].append((b, w))
        incident[b].append((a, w))

    initial_path_cost = path_transition_cost(tier, edge_weight)
    initial_net_proxy = crossing_connection_proxy(tier, net_to_instances)
    current_net_proxy = initial_net_proxy
    trace: list[dict[str, object]] = []

    candidates = sorted(incident, key=lambda inst: sum(w for _, w in incident[inst]), reverse=True)
    for move_index in range(args.max_moves):
        best: tuple[float, float, int, int, int, str] | None = None
        for inst in candidates:
            old = tier[inst]
            tier[inst] = "tier1" if old == "tier0" else "tier0"
            inst_balance, w_balance = balance_ratio(tier, weight)
            tier[inst] = old
            if inst_balance < effective_min_instance or w_balance < effective_min_weight:
                continue

            d_path = delta_path_cost(inst, tier, incident)
            d_crossing_paths, d_transition_count = delta_path_crossing_stats(inst, tier, paths, inst_to_paths)
            path_score = (
                args.path_crossing_weight * d_crossing_paths
                + args.path_transition_weight * d_transition_count
                + d_path
            )
            if path_score > -args.min_path_gain:
                continue
            d_net = delta_net_proxy(inst, tier, inst_to_nets, net_to_instances)
            if current_net_proxy + d_net > initial_net_proxy + args.max_net_regret:
                continue
            score = path_score + args.net_regret_weight * d_net
            if best is None or score < best[0]:
                best = (score, d_path, d_net, d_crossing_paths, d_transition_count, inst)

        if best is None:
            break
        score, d_path, d_net, d_crossing_paths, d_transition_count, inst = best
        tier[inst] = "tier1" if tier[inst] == "tier0" else "tier0"
        current_net_proxy += d_net
        inst_balance, w_balance = balance_ratio(tier, weight)
        trace.append(
            {
                "move_index": move_index,
                "instance": inst,
                "score": f"{score:.6f}",
                "path_cost_delta": f"{d_path:.6f}",
                "crossing_path_count_delta": d_crossing_paths,
                "path_transition_count_delta": d_transition_count,
                "net_proxy_delta": d_net,
                "net_proxy": current_net_proxy,
                "instance_balance": f"{inst_balance:.6f}",
                "weight_balance": f"{w_balance:.6f}",
            }
        )

    block_trace: list[dict[str, object]] = []
    if args.enable_path_block_moves:
        for block_pass in range(args.path_block_passes):
            accepted_in_pass = 0
            path_order = sorted(
                range(len(paths)),
                key=lambda idx: (path_transition_count(paths[idx], tier), paths[idx].weight),
                reverse=True,
            )
            for path_idx in path_order:
                path = paths[path_idx]
                seq = [inst for inst in path.instances if inst in tier]
                old_transitions = path_transition_count(path, tier)
                if old_transitions == 0:
                    continue
                counts = Counter(tier[inst] for inst in seq)
                if not counts:
                    continue
                candidate_targets = [target for target, _ in counts.most_common()]
                if len(candidate_targets) == 1:
                    continue

                best_block: tuple[float, str, list[str], int, int, int] | None = None
                for target_tier in candidate_targets:
                    block = list(dict.fromkeys(inst for inst in seq if tier[inst] != target_tier))
                    if not block or len(block) > args.max_path_block_size:
                        continue

                    old_tiers = {inst: tier[inst] for inst in block}
                    old_path_cost = path_transition_cost(tier, edge_weight)
                    old_net_proxy = crossing_connection_proxy(tier, net_to_instances)
                    old_crossing_paths = summarize_paths(tier, paths)["crossing_path_count"]

                    for inst in block:
                        tier[inst] = target_tier
                    inst_balance, w_balance = balance_ratio(tier, weight)
                    new_transitions = path_transition_count(path, tier)
                    new_path_cost = path_transition_cost(tier, edge_weight)
                    new_net_proxy = crossing_connection_proxy(tier, net_to_instances)
                    new_crossing_paths = summarize_paths(tier, paths)["crossing_path_count"]

                    for inst, old_tier in old_tiers.items():
                        tier[inst] = old_tier

                    if inst_balance < effective_min_instance or w_balance < effective_min_weight:
                        continue
                    if new_net_proxy > initial_net_proxy + args.max_net_regret:
                        continue
                    path_cost_delta = new_path_cost - old_path_cost
                    transition_delta = new_transitions - old_transitions
                    crossing_delta = int(new_crossing_paths) - int(old_crossing_paths)
                    if crossing_delta > 0:
                        continue
                    score = (
                        args.path_crossing_weight * crossing_delta
                        + args.path_transition_weight * transition_delta
                        + path_cost_delta
                        + args.net_regret_weight * (new_net_proxy - old_net_proxy)
                    )
                    if score >= -args.min_path_gain:
                        continue
                    if best_block is None or score < best_block[0]:
                        best_block = (score, target_tier, block, crossing_delta, transition_delta, new_net_proxy - old_net_proxy)

                if best_block is None:
                    continue
                score, target_tier, block, crossing_delta, transition_delta, net_delta = best_block
                for inst in block:
                    tier[inst] = target_tier
                current_net_proxy = crossing_connection_proxy(tier, net_to_instances)
                inst_balance, w_balance = balance_ratio(tier, weight)
                block_trace.append(
                    {
                        "block_pass": block_pass,
                        "path_index": path_idx,
                        "target_tier": target_tier,
                        "block_size": len(block),
                        "score": f"{score:.6f}",
                        "crossing_path_count_delta": crossing_delta,
                        "path_transition_count_delta": transition_delta,
                        "net_proxy_delta": net_delta,
                        "net_proxy": current_net_proxy,
                        "instance_balance": f"{inst_balance:.6f}",
                        "weight_balance": f"{w_balance:.6f}",
                        "moved_instances": ";".join(block[:20]),
                    }
                )
                accepted_in_pass += 1
            if accepted_in_pass == 0:
                break

    final_path_cost = path_transition_cost(tier, edge_weight)
    final_net_proxy = crossing_connection_proxy(tier, net_to_instances)
    final_instance_balance, final_weight_balance = balance_ratio(tier, weight)

    assignment_out = output_dir / "tritonpart_path_aware_guarded_repair_assignment.csv"
    assignment_rows = format_assignment_rows(rows, tier)
    write_csv(assignment_out, assignment_rows, list(rows[0].keys()))

    summary_rows = []
    for case, case_tier in [("starting_asa_rv3d", original_tier), ("path_aware_asa_rv3d", tier)]:
        path_summary = summarize_paths(case_tier, paths)
        inst_balance, w_balance = balance_ratio(case_tier, weight)
        net_proxy = crossing_connection_proxy(case_tier, net_to_instances)
        row = {
            "design": args.design,
            "scenario": args.scenario,
            "case": case,
            "assignment_file": str(start_assignment if case == "starting_asa_rv3d" else assignment_out),
            "path_transition_cost": f"{path_transition_cost(case_tier, edge_weight):.6f}",
            "net_crossing_connection_proxy": net_proxy,
            "instance_balance": f"{inst_balance:.6f}",
            "weight_balance": f"{w_balance:.6f}",
            **path_summary,
        }
        summary_rows.append(row)
    write_csv(
        output_dir / "path_aware_comparison.csv",
        summary_rows,
        [
            "design",
            "scenario",
            "case",
            "assignment_file",
            "path_count",
            "crossing_path_count",
            "crossing_path_fraction",
            "mean_tier_transitions",
            "max_tier_transitions",
            "path_transition_cost",
            "net_crossing_connection_proxy",
            "instance_balance",
            "weight_balance",
        ],
    )
    write_csv(
        output_dir / "path_aware_refinement_trace.csv",
        trace,
        [
            "move_index",
            "instance",
            "score",
            "path_cost_delta",
            "crossing_path_count_delta",
            "path_transition_count_delta",
            "net_proxy_delta",
            "net_proxy",
            "instance_balance",
            "weight_balance",
        ],
    )
    write_csv(
        output_dir / "path_block_refinement_trace.csv",
        block_trace,
        [
            "block_pass",
            "path_index",
            "target_tier",
            "block_size",
            "score",
            "crossing_path_count_delta",
            "path_transition_count_delta",
            "net_proxy_delta",
            "net_proxy",
            "instance_balance",
            "weight_balance",
            "moved_instances",
        ],
    )

    manifest = {
        "design": args.design,
        "scenario": args.scenario,
        "features_dir": str(features_dir),
        "start_assignment": str(start_assignment),
        "timing_report": str(timing_report),
        "output_dir": str(output_dir),
        "max_paths": args.max_paths,
        "max_moves": args.max_moves,
        "initial_path_transition_cost": initial_path_cost,
        "final_path_transition_cost": final_path_cost,
        "initial_net_crossing_connection_proxy": initial_net_proxy,
        "final_net_crossing_connection_proxy": final_net_proxy,
        "initial_instance_balance": initial_instance_balance,
        "initial_weight_balance": initial_weight_balance,
        "final_instance_balance": final_instance_balance,
        "final_weight_balance": final_weight_balance,
        "moves": len(trace),
        "path_block_moves": len(block_trace),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "path_aware_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(output_dir / "path_aware_manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
