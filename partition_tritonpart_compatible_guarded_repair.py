#!/usr/bin/env python3
"""TritonPart-compatible ASA-on-native guarded refinement.

This Phase-2 prototype turns the Phase-1 replay evidence into an online guarded
acceptance rule.  It consumes an existing ASA local-refinement trace as the
candidate move order, but it does not simply take a prefix.  Each candidate move
is accepted only if it:

* has positive ASA repair gain,
* preserves OpenROAD/TritonPart-compatible area balance,
* keeps raw cut regret within a fixed budget.

Timing/path metrics are evaluated after the resulting assignment with the
existing timing-crossing and path-cut evaluators.  This keeps this script
strictly focused on feasibility and connectivity guards while preserving the
original trace order from the timing-regret guarded repair.
"""

from __future__ import annotations

import argparse
import csv
import re
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


def load_assignment(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = read_csv(path)
    tier = {normalize_name(row["instance"]): row["tier"] for row in rows}
    return rows, tier


def load_assignment_aliases(rows: list[dict[str, str]]) -> dict[str, str]:
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
        status = row.get("status", "unique")
        if status != "unique":
            continue
        inst = normalize_name(row.get("variant") or row.get("instance") or row.get("canonical_instance", ""))
        if not inst:
            continue
        value = int(float(row["area"]))
        area[inst] = value
    return area


def load_net_to_instances(features_dir: Path, assignment_instances: set[str]) -> dict[str, list[str]]:
    rows = read_csv(features_dir / "instance_features.csv")
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


def finish_timing_path(raw_instances: list[str], aliases: dict[str, str], index: int) -> TimingPath:
    instances: list[str] = []
    for token in list(dict.fromkeys(raw_instances)):
        inst = resolve_instance(token, aliases)
        if inst:
            instances.append(inst)
    return TimingPath(index=index, instances=list(dict.fromkeys(instances)))


def transition_count(path: TimingPath, tier: dict[str, str]) -> int:
    seq = [inst for inst in path.instances if inst in tier]
    return sum(1 for a, b in zip(seq, seq[1:]) if tier[a] != tier[b])


def path_cut_stats(paths: list[TimingPath], tier: dict[str, str]) -> dict[str, float]:
    if not paths:
        return {
            "P_avg_cut": 0.0,
            "P_wst_cut": 0.0,
            "cut_path_fraction": 0.0,
            "total_tier_transitions": 0.0,
        }
    transitions = [transition_count(path, tier) for path in paths]
    total = sum(transitions)
    return {
        "P_avg_cut": total / len(paths),
        "P_wst_cut": float(max(transitions) if transitions else 0),
        "cut_path_fraction": sum(1 for count in transitions if count > 0) / len(paths),
        "total_tier_transitions": float(total),
    }


def crossing_stats(tier: dict[str, str], net_to_instances: dict[str, list[str]]) -> tuple[int, int]:
    crossing_nets = 0
    crossing_connections = 0
    for insts in net_to_instances.values():
        c0 = sum(1 for inst in insts if tier.get(inst) == "tier0")
        c1 = sum(1 for inst in insts if tier.get(inst) == "tier1")
        if c0 and c1:
            crossing_nets += 1
            crossing_connections += min(c0, c1)
    return crossing_nets, crossing_connections


def area_stats(tier: dict[str, str], area: dict[str, int]) -> dict[str, float]:
    tier_area = {"tier0": 0, "tier1": 0}
    matched = 0
    unmatched = 0
    for inst, part in tier.items():
        value = area.get(inst)
        if value is None:
            unmatched += 1
            continue
        matched += 1
        tier_area[part] += value
    total = tier_area["tier0"] + tier_area["tier1"]
    lo = min(tier_area["tier0"], tier_area["tier1"])
    hi = max(tier_area["tier0"], tier_area["tier1"])
    return {
        "tier0_area": float(tier_area["tier0"]),
        "tier1_area": float(tier_area["tier1"]),
        "tier0_area_fraction": tier_area["tier0"] / total if total else 0.0,
        "tier1_area_fraction": tier_area["tier1"] / total if total else 0.0,
        "area_weight_balance": lo / hi if hi else 0.0,
        "matched_instances": float(matched),
        "unmatched_instances": float(unmatched),
    }


def area_pass(stats: dict[str, float], lo: float, hi: float) -> bool:
    return lo <= stats["tier0_area_fraction"] <= hi


def assignment_rows(rows: list[dict[str, str]], tier: dict[str, str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in rows:
        new_row = dict(row)
        new_row["tier"] = tier[normalize_name(row["instance"])]
        out.append(new_row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--initial-assignment", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--instance-area", type=Path, required=True)
    parser.add_argument("--timing-report", type=Path)
    parser.add_argument("--max-paths", type=int, default=100)
    parser.add_argument("--max-cut-regret", type=float, default=0.05)
    parser.add_argument("--max-pavg-regret", type=float, default=0.0)
    parser.add_argument("--max-pwst-delta", type=float, default=0.0)
    parser.add_argument("--area-lo", type=float, default=0.48)
    parser.add_argument("--area-hi", type=float, default=0.52)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    rows, initial_tier = load_assignment(args.initial_assignment)
    aliases = load_assignment_aliases(rows)
    tier = dict(initial_tier)
    trace = read_csv(args.trace)
    area = load_area(args.instance_area)
    net_to_instances = load_net_to_instances(args.features_dir, set(tier))

    baseline_crossing, baseline_conn = crossing_stats(tier, net_to_instances)
    initial_area = area_stats(tier, area)
    timing_paths = parse_timing_paths(args.timing_report, aliases, args.max_paths) if args.timing_report else []
    baseline_paths = path_cut_stats(timing_paths, tier)
    if not area_pass(initial_area, args.area_lo, args.area_hi):
        print(
            "warning: initial assignment is outside the requested area window; "
            "the guarded repair will not be a primary comparable success unless it re-enters the window."
        )

    accepted = 0
    rejected_gain = 0
    rejected_area = 0
    rejected_cut = 0
    rejected_path = 0
    cumulative_gain = 0.0
    cumulative_scenario_gain = 0.0
    cumulative_physical_gain = 0.0
    cumulative_timing_gain = 0.0
    trace_rows: list[dict[str, object]] = []

    for index, move in enumerate(trace, start=1):
        inst = normalize_name(move["instance"])
        if inst not in tier:
            continue
        gain = as_float(move.get("gain"))
        if gain <= 0.0:
            rejected_gain += 1
            continue
        to_tier = move.get("to_tier", "")
        if to_tier not in {"tier0", "tier1"}:
            continue
        from_tier = tier[inst]
        if from_tier == to_tier:
            continue

        candidate = dict(tier)
        candidate[inst] = to_tier
        candidate_area = area_stats(candidate, area)
        if not area_pass(candidate_area, args.area_lo, args.area_hi):
            rejected_area += 1
            trace_rows.append(
                {
                    "candidate_index": index,
                    "instance": inst,
                    "architecture_unit": move.get("architecture_unit", ""),
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "accepted": "false",
                    "reject_reason": "area_balance",
                    "cut_regret_after": "",
                    "tier0_area_fraction_after": f"{candidate_area['tier0_area_fraction']:.6f}",
                    "gain": f"{gain:.6f}",
                }
            )
            continue

        candidate_crossing, candidate_conn = crossing_stats(candidate, net_to_instances)
        cut_regret = (candidate_crossing - baseline_crossing) / baseline_crossing if baseline_crossing else 0.0
        if cut_regret > args.max_cut_regret:
            rejected_cut += 1
            trace_rows.append(
                {
                    "candidate_index": index,
                    "instance": inst,
                    "architecture_unit": move.get("architecture_unit", ""),
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "accepted": "false",
                    "reject_reason": "cut_regret",
                    "cut_regret_after": f"{cut_regret:.6f}",
                    "tier0_area_fraction_after": f"{candidate_area['tier0_area_fraction']:.6f}",
                    "gain": f"{gain:.6f}",
                }
            )
            continue

        candidate_paths = path_cut_stats(timing_paths, candidate) if timing_paths else baseline_paths
        pavg_regret = (
            (candidate_paths["P_avg_cut"] - baseline_paths["P_avg_cut"]) / baseline_paths["P_avg_cut"]
            if baseline_paths["P_avg_cut"]
            else 0.0
        )
        pwst_delta = candidate_paths["P_wst_cut"] - baseline_paths["P_wst_cut"]
        if pavg_regret > args.max_pavg_regret or pwst_delta > args.max_pwst_delta:
            rejected_path += 1
            trace_rows.append(
                {
                    "candidate_index": index,
                    "instance": inst,
                    "architecture_unit": move.get("architecture_unit", ""),
                    "from_tier": from_tier,
                    "to_tier": to_tier,
                    "accepted": "false",
                    "reject_reason": "path_cut",
                    "cut_regret_after": f"{cut_regret:.6f}",
                    "tier0_area_fraction_after": f"{candidate_area['tier0_area_fraction']:.6f}",
                    "P_avg_cut_after": f"{candidate_paths['P_avg_cut']:.6f}",
                    "P_avg_cut_regret_after": f"{pavg_regret:.6f}",
                    "P_wst_cut_after": f"{candidate_paths['P_wst_cut']:.6f}",
                    "P_wst_cut_delta_after": f"{pwst_delta:.6f}",
                    "gain": f"{gain:.6f}",
                }
            )
            continue

        tier = candidate
        accepted += 1
        cumulative_gain += gain
        cumulative_scenario_gain += as_float(move.get("scenario_gain"))
        cumulative_physical_gain += as_float(move.get("physical_gain"))
        cumulative_timing_gain += as_float(move.get("timing_gain"))
        trace_rows.append(
            {
                "candidate_index": index,
                "instance": inst,
                "architecture_unit": move.get("architecture_unit", ""),
                "from_tier": from_tier,
                "to_tier": to_tier,
                "accepted": "true",
                "reject_reason": "",
                "cut_regret_after": f"{cut_regret:.6f}",
                "tier0_area_fraction_after": f"{candidate_area['tier0_area_fraction']:.6f}",
                "P_avg_cut_after": f"{candidate_paths['P_avg_cut']:.6f}",
                "P_avg_cut_regret_after": f"{pavg_regret:.6f}",
                "P_wst_cut_after": f"{candidate_paths['P_wst_cut']:.6f}",
                "P_wst_cut_delta_after": f"{pwst_delta:.6f}",
                "gain": f"{gain:.6f}",
            }
        )

    final_crossing, final_conn = crossing_stats(tier, net_to_instances)
    final_area = area_stats(tier, area)
    final_paths = path_cut_stats(timing_paths, tier)
    final_cut_regret = (final_crossing - baseline_crossing) / baseline_crossing if baseline_crossing else 0.0
    final_conn_regret = (final_conn - baseline_conn) / baseline_conn if baseline_conn else 0.0

    args.output_dir.mkdir(parents=True, exist_ok=True)
    assignment_path = args.output_dir / "tritonpart_compatible_guarded_repair_assignment.csv"
    trace_path = args.output_dir / "tritonpart_compatible_guarded_repair_trace.csv"
    summary_path = args.output_dir / "tritonpart_compatible_guarded_repair_summary.csv"
    trace_fieldnames = [
        "candidate_index",
        "instance",
        "architecture_unit",
        "from_tier",
        "to_tier",
        "accepted",
        "reject_reason",
        "cut_regret_after",
        "tier0_area_fraction_after",
        "P_avg_cut_after",
        "P_avg_cut_regret_after",
        "P_wst_cut_after",
        "P_wst_cut_delta_after",
        "gain",
    ]

    write_csv(assignment_path, assignment_rows(rows, tier), list(rows[0].keys()))
    write_csv(trace_path, trace_rows, trace_fieldnames)
    write_csv(
        summary_path,
        [
            {
                "design": args.design,
                "scenario": args.scenario,
                "baseline_crossing_nets": baseline_crossing,
                "final_crossing_nets": final_crossing,
                "cut_regret": f"{final_cut_regret:.6f}",
                "baseline_crossing_connections_proxy": baseline_conn,
                "final_crossing_connections_proxy": final_conn,
                "crossing_connection_regret": f"{final_conn_regret:.6f}",
                "initial_area_balance_pass": str(area_pass(initial_area, args.area_lo, args.area_hi)).lower(),
                "final_area_balance_pass": str(area_pass(final_area, args.area_lo, args.area_hi)).lower(),
                "final_area_weight_balance": f"{final_area['area_weight_balance']:.6f}",
                "final_tier0_area_fraction": f"{final_area['tier0_area_fraction']:.6f}",
                "final_tier1_area_fraction": f"{final_area['tier1_area_fraction']:.6f}",
                "accepted_moves": accepted,
                "rejected_gain_moves": rejected_gain,
                "rejected_area_moves": rejected_area,
                "rejected_cut_moves": rejected_cut,
                "rejected_path_moves": rejected_path,
                "baseline_P_avg_cut": f"{baseline_paths['P_avg_cut']:.6f}",
                "final_P_avg_cut": f"{final_paths['P_avg_cut']:.6f}",
                "P_avg_cut_regret": f"{((final_paths['P_avg_cut'] - baseline_paths['P_avg_cut']) / baseline_paths['P_avg_cut']) if baseline_paths['P_avg_cut'] else 0.0:.6f}",
                "baseline_P_wst_cut": f"{baseline_paths['P_wst_cut']:.6f}",
                "final_P_wst_cut": f"{final_paths['P_wst_cut']:.6f}",
                "P_wst_cut_delta": f"{final_paths['P_wst_cut'] - baseline_paths['P_wst_cut']:.6f}",
                "cumulative_gain": f"{cumulative_gain:.6f}",
                "cumulative_scenario_gain": f"{cumulative_scenario_gain:.6f}",
                "cumulative_physical_gain": f"{cumulative_physical_gain:.6f}",
                "cumulative_timing_gain": f"{cumulative_timing_gain:.6f}",
                "assignment_file": str(assignment_path),
            }
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
