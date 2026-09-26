#!/usr/bin/env python3
"""Normalized dynamic TritonPart-compatible ASA guarded refinement.

This is the next-step version after the Phase-2 trace-filter prototype.  It no
longer uses an old local-refinement trace or old per-move gains.  At every
iteration it recomputes candidate gains from the current assignment, checks the
same TritonPart-compatible guards, accepts the best legal move, and repeats.

This experimental variant keeps the same area/cut/path guards as Phase-3, but
normalizes the architecture, physical, and timing signals before combining them:

    risk = 1 + lambda_arch * A_norm
             + lambda_physical * P_norm
             + lambda_timing * T_norm

where each signal is scaled to [0, 1] across instances in the current design.
The purpose is to test whether the previous Phase-3 objective was dominated by
raw architecture weights.
* the guard preserves OpenROAD-style area balance;
* raw cut regret and timing-path cut metrics are bounded against the native
  timing-aware TritonPart starting point.

It is a paper-facing prototype for constrained local refinement, not a signoff
3D physical-design tool.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.net_graph_utils import (  # noqa: E402
    crossing_stats as shared_crossing_stats,
    load_feature_net_graph,
    net_tier_counts,
)


FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")
STD_CELL_RE = re.compile(r"\((sky130[^)]*|[A-Za-z0-9_]+__[^)]*)\)")
EDGE_MARKERS = {"^", "v", "r", "f"}

TRACE_FIELDNAMES = [
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
    "iteration_elapsed_s",
    "cumulative_elapsed_s",
]


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


def write_csv_atomic(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def write_json_atomic(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


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
    graph = load_feature_net_graph(features_dir / "instance_features.csv", assignment_instances)
    return graph.net_to_instances, graph.inst_to_nets


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


def normalize_scores(values: dict[str, float], instances: set[str]) -> dict[str, float]:
    selected = [values.get(inst, 0.0) for inst in instances]
    if not selected:
        return {inst: 0.0 for inst in instances}
    lo = min(selected)
    hi = max(selected)
    if hi <= lo:
        return {inst: 0.0 for inst in instances}
    return {inst: (values.get(inst, 0.0) - lo) / (hi - lo) for inst in instances}


def normalized_risk_components(
    instances: set[str],
    scenario: str,
    arch_unit: dict[str, str],
    semantic_group: dict[str, str],
    physical_scores: dict[str, float],
    timing_scores: dict[str, float],
    lambda_arch: float,
    lambda_physical: float,
    lambda_timing: float,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    arch_raw = {
        inst: scenario_unit_weight(
            arch_unit.get(inst, "unclassified"),
            semantic_group.get(inst, "infrastructure"),
            scenario,
        )
        for inst in instances
    }
    physical_raw = {inst: physical_scores.get(inst, 0.0) for inst in instances}
    timing_raw = {inst: timing_scores.get(inst, 0.0) for inst in instances}

    arch_norm = normalize_scores(arch_raw, instances)
    physical_norm = normalize_scores(physical_raw, instances)
    timing_norm = normalize_scores(timing_raw, instances)
    risk = {
        inst: 1.0
        + lambda_arch * arch_norm.get(inst, 0.0)
        + lambda_physical * physical_norm.get(inst, 0.0)
        + lambda_timing * timing_norm.get(inst, 0.0)
        for inst in instances
    }
    return risk, arch_norm, physical_norm, timing_norm


def component_summary(
    arch_norm: dict[str, float],
    physical_norm: dict[str, float],
    timing_norm: dict[str, float],
    lambda_arch: float,
    lambda_physical: float,
    lambda_timing: float,
) -> dict[str, float]:
    instances = set(arch_norm) | set(physical_norm) | set(timing_norm)
    arch_sum = sum(lambda_arch * arch_norm.get(inst, 0.0) for inst in instances)
    physical_sum = sum(lambda_physical * physical_norm.get(inst, 0.0) for inst in instances)
    timing_sum = sum(lambda_timing * timing_norm.get(inst, 0.0) for inst in instances)
    total = arch_sum + physical_sum + timing_sum
    return {
        "normalized_arch_sum": arch_sum,
        "normalized_physical_sum": physical_sum,
        "normalized_timing_sum": timing_sum,
        "normalized_arch_fraction": arch_sum / total if total else 0.0,
        "normalized_physical_fraction": physical_sum / total if total else 0.0,
        "normalized_timing_fraction": timing_sum / total if total else 0.0,
    }


def net_counts(tier: dict[str, str], insts: list[str]) -> tuple[int, int]:
    return net_tier_counts(tier, insts)


def net_cost(tier: dict[str, str], insts: list[str], risk: dict[str, float]) -> float:
    c0, c1 = net_counts(tier, insts)
    if not c0 or not c1:
        return 0.0
    risk_sum = sum(risk.get(inst, 1.0) for inst in insts)
    return min(c0, c1) * risk_sum / max(1, len(insts))


def total_objective(tier: dict[str, str], net_to_instances: dict[str, list[str]], risk: dict[str, float]) -> float:
    return sum(net_cost(tier, insts, risk) for insts in net_to_instances.values())


def crossing_stats(tier: dict[str, str], net_to_instances: dict[str, list[str]]) -> tuple[int, int]:
    return shared_crossing_stats(tier, net_to_instances)


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


def area_stats_from_parts(tier0_area: int, tier1_area: int, matched: int, unmatched: int) -> dict[str, float]:
    total = tier0_area + tier1_area
    lo = min(tier0_area, tier1_area)
    hi = max(tier0_area, tier1_area)
    return {
        "tier0_area": float(tier0_area),
        "tier1_area": float(tier1_area),
        "tier0_area_fraction": tier0_area / total if total else 0.0,
        "tier1_area_fraction": tier1_area / total if total else 0.0,
        "area_weight_balance": lo / hi if hi else 0.0,
        "matched_instances": float(matched),
        "unmatched_instances": float(unmatched),
    }


def current_area_parts(tier: dict[str, str], area: dict[str, int]) -> tuple[int, int, int, int]:
    tier0_area = 0
    tier1_area = 0
    matched = 0
    unmatched = 0
    for inst, part in tier.items():
        value = area.get(inst)
        if value is None:
            unmatched += 1
            continue
        matched += 1
        if part == "tier0":
            tier0_area += value
        elif part == "tier1":
            tier1_area += value
    return tier0_area, tier1_area, matched, unmatched


def area_pass(stats: dict[str, float], lo: float, hi: float) -> bool:
    return lo <= stats["tier0_area_fraction"] <= hi


def crossing_delta_for_move(
    *,
    tier: dict[str, str],
    net_to_instances: dict[str, list[str]],
    affected_nets: list[str],
    inst: str,
    old_tier: str,
    new_tier: str,
) -> tuple[int, int]:
    """Return crossing-net and crossing-connection deltas for one trial move."""

    delta_crossing = 0
    delta_connections = 0
    for net in affected_nets:
        insts = net_to_instances[net]
        old_c0, old_c1 = net_counts(tier, insts)
        old_crossing = bool(old_c0 and old_c1)
        old_connections = min(old_c0, old_c1) if old_crossing else 0

        if old_tier == "tier0":
            new_c0 = old_c0 - 1
            new_c1 = old_c1 + 1
        else:
            new_c0 = old_c0 + 1
            new_c1 = old_c1 - 1
        new_crossing = bool(new_c0 and new_c1)
        new_connections = min(new_c0, new_c1) if new_crossing else 0

        delta_crossing += int(new_crossing) - int(old_crossing)
        delta_connections += new_connections - old_connections
    return delta_crossing, delta_connections


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


def save_resume_state(
    *,
    output: Path,
    checkpoint_dir: Path,
    assignment_rows_template: list[dict[str, str]],
    tier: dict[str, str],
    trace_rows: list[dict[str, object]],
    design: str,
    scenario: str,
    architecture_mode: str,
    initial_assignment: Path,
    iteration: int,
    objective: float,
    cumulative_gain: float,
    trace_path: Path,
    checkpoint_every: int,
) -> None:
    if checkpoint_every <= 0 or iteration % checkpoint_every != 0:
        return
    checkpoint_path = checkpoint_dir / f"checkpoint_{iteration:04d}_assignment.csv"
    write_csv_atomic(checkpoint_path, assignment_rows(assignment_rows_template, tier), list(assignment_rows_template[0].keys()))
    write_csv_atomic(trace_path, trace_rows, TRACE_FIELDNAMES)
    manifest = {
        "design": design,
        "scenario": scenario,
        "architecture_mode": architecture_mode,
        "original_initial_assignment": str(initial_assignment),
        "last_completed_iteration": iteration,
        "latest_checkpoint": str(checkpoint_path),
        "trace_path": str(trace_path),
        "objective": f"{objective:.6f}",
        "cumulative_dynamic_gain": f"{cumulative_gain:.6f}",
        "checkpoint_every": checkpoint_every,
        "updated_at_unix": time.time(),
    }
    write_json_atomic(output / "resume_manifest.json", manifest)


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
    parser.add_argument("--lambda-arch", type=float, default=1.0)
    parser.add_argument("--lambda-physical", type=float, default=1.0)
    parser.add_argument("--lambda-timing", type=float, default=1.0)
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
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=1,
        help="Save resumable assignment checkpoint every N accepted moves. Use 0 to disable.",
    )
    parser.add_argument(
        "--validate-incremental",
        action="store_true",
        help="After each accepted move, recompute full area/crossing stats and assert incremental state matches.",
    )
    parser.add_argument(
        "--convergence-window",
        type=int,
        default=0,
        help=(
            "Stop after this many accepted moves if their cumulative gain is "
            "below --min-relative-gain times the baseline objective. Use 0 to disable."
        ),
    )
    parser.add_argument(
        "--min-relative-gain",
        type=float,
        default=0.001,
        help=(
            "Minimum recent gain fraction used with --convergence-window. "
            "For example, 0.001 means the last window must improve at least 0.1% of baseline objective."
        ),
    )
    parser.add_argument(
        "--resume-from",
        type=Path,
        help=(
            "Resume from a previously written resume_manifest.json. The original "
            "--initial-assignment remains the baseline; only the current tier "
            "state is restored from the latest checkpoint."
        ),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    assignment_path = output / "tritonpart_compatible_dynamic_guarded_repair_assignment.csv"
    trace_path = output / "tritonpart_compatible_dynamic_guarded_repair_trace.csv"
    summary_path = output / "tritonpart_compatible_dynamic_guarded_repair_summary.csv"
    checkpoint_dir = output / "checkpoints"

    resume_manifest: dict[str, object] = {}
    resume_checkpoint: Path | None = None
    resume_trace_path: Path | None = None
    if args.resume_from:
        resume_manifest = json.loads(args.resume_from.read_text(encoding="utf-8"))
        resume_initial = Path(str(resume_manifest.get("original_initial_assignment", args.initial_assignment)))
        if str(args.initial_assignment) != str(resume_initial):
            print(
                "resume overrides initial assignment baseline "
                f"from {args.initial_assignment} to {resume_initial}",
                flush=True,
            )
        args.initial_assignment = resume_initial
        resume_checkpoint = Path(str(resume_manifest["latest_checkpoint"]))
        resume_trace_path = Path(str(resume_manifest.get("trace_path", trace_path)))

    rows, tier, _weight, arch_unit, semantic_group = load_assignment(args.initial_assignment)
    baseline_tier = dict(tier)
    if resume_checkpoint:
        _checkpoint_rows, checkpoint_tier, _checkpoint_weight, _checkpoint_arch, _checkpoint_group = load_assignment(resume_checkpoint)
        missing_checkpoint_instances = sorted(set(tier) - set(checkpoint_tier))
        if missing_checkpoint_instances:
            raise SystemExit(
                f"resume checkpoint is missing {len(missing_checkpoint_instances)} baseline instances; "
                f"first missing: {missing_checkpoint_instances[:5]}"
            )
        tier = {inst: checkpoint_tier[inst] for inst in tier}
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
    risk, arch_norm, physical_norm, timing_norm = normalized_risk_components(
        set(tier),
        args.scenario,
        arch_unit,
        semantic_group,
        physical,
        timing,
        args.lambda_arch,
        args.lambda_physical,
        args.lambda_timing,
    )
    contribution = component_summary(
        arch_norm,
        physical_norm,
        timing_norm,
        args.lambda_arch,
        args.lambda_physical,
        args.lambda_timing,
    )

    paths = parse_timing_paths(args.timing_report, aliases, args.max_paths)
    inst_to_paths = build_inst_to_paths(paths)
    path_transition = [transition_count(path, tier) for path in paths]

    baseline_crossing, baseline_conn = crossing_stats(baseline_tier, net_to_instances)
    baseline_area = area_stats(baseline_tier, area)
    baseline_paths = path_cut_stats(paths, baseline_tier)
    baseline_objective = total_objective(baseline_tier, net_to_instances, risk)
    current_crossing, current_conn = crossing_stats(tier, net_to_instances)
    current_tier0_area, current_tier1_area, area_matched, area_unmatched = current_area_parts(tier, area)

    accepted_rows: list[dict[str, object]] = []
    if resume_trace_path and resume_trace_path.exists():
        accepted_rows = [dict(row) for row in read_csv(resume_trace_path)]
    rejected_no_legal = 0
    cumulative_gain = sum(as_float(str(row.get("objective_delta", "0"))) for row in accepted_rows)
    current_objective = baseline_objective
    if accepted_rows:
        current_objective = total_objective(tier, net_to_instances, risk)

    candidate_pool = sorted(inst for inst in tier if inst_to_nets.get(inst))
    print(
        "dynamic_guarded_repair_start "
        f"design={args.design} scenario={args.scenario} "
        f"architecture_mode={architecture_mode} "
        f"risk_mode=normalized "
        f"lambda_arch={args.lambda_arch} "
        f"lambda_physical={args.lambda_physical} "
        f"lambda_timing={args.lambda_timing} "
        f"instances={len(tier)} candidates={len(candidate_pool)} "
        f"paths={len(paths)} baseline_crossing={baseline_crossing} "
        f"baseline_objective={baseline_objective:.6f}",
        flush=True,
    )

    completed_iterations = int(resume_manifest.get("last_completed_iteration", 0)) if resume_manifest else 0
    start_iteration = completed_iterations + 1
    run_start = time.time()
    stopped_converged = False
    final_recent_gain_fraction = 0.0
    if resume_manifest:
        print(
            "resume_dynamic_guarded_repair "
            f"from={args.resume_from} start_iteration={start_iteration} "
            f"checkpoint={resume_checkpoint}",
            flush=True,
        )

    for iteration in range(start_iteration, args.max_iterations + 1):
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

            inst_area = area.get(inst, 0)
            if old_tier == "tier0":
                trial_tier0_area = current_tier0_area - inst_area
                trial_tier1_area = current_tier1_area + inst_area
            else:
                trial_tier0_area = current_tier0_area + inst_area
                trial_tier1_area = current_tier1_area - inst_area
            astats = area_stats_from_parts(trial_tier0_area, trial_tier1_area, area_matched, area_unmatched)
            if not area_pass(astats, args.area_lo, args.area_hi):
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

            tier[inst] = old_tier
            crossing_delta, conn_delta = crossing_delta_for_move(
                tier=tier,
                net_to_instances=net_to_instances,
                affected_nets=affected_nets,
                inst=inst,
                old_tier=old_tier,
                new_tier=new_tier,
            )
            crossing = current_crossing + crossing_delta
            conn = current_conn + conn_delta
            tier[inst] = new_tier
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
        old_tier = str(best["from_tier"])
        tier[inst] = str(best["to_tier"])
        inst_area = area.get(inst, 0)
        if old_tier == "tier0":
            current_tier0_area -= inst_area
            current_tier1_area += inst_area
        else:
            current_tier0_area += inst_area
            current_tier1_area -= inst_area
        current_crossing = int(best["crossing_nets_after"])
        current_conn = int(best["crossing_connections_after"])
        for idx in inst_to_paths.get(inst, []):
            path_transition[idx] = transition_count(paths[idx], tier)
        if args.validate_incremental:
            check_crossing, check_conn = crossing_stats(tier, net_to_instances)
            check_tier0, check_tier1, check_matched, check_unmatched = current_area_parts(tier, area)
            if (check_crossing, check_conn) != (current_crossing, current_conn):
                raise AssertionError(
                    "incremental crossing mismatch "
                    f"incremental={(current_crossing, current_conn)} full={(check_crossing, check_conn)}"
                )
            if (check_tier0, check_tier1, check_matched, check_unmatched) != (
                current_tier0_area,
                current_tier1_area,
                area_matched,
                area_unmatched,
            ):
                raise AssertionError(
                    "incremental area mismatch "
                    f"incremental={(current_tier0_area, current_tier1_area, area_matched, area_unmatched)} "
                    f"full={(check_tier0, check_tier1, check_matched, check_unmatched)}"
                )
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
                "iteration_elapsed_s": f"{time.time() - iteration_start:.3f}",
                "cumulative_elapsed_s": f"{time.time() - run_start:.3f}",
            }
        )
        save_resume_state(
            output=output,
            checkpoint_dir=checkpoint_dir,
            assignment_rows_template=rows,
            tier=tier,
            trace_rows=accepted_rows,
            design=args.design,
            scenario=args.scenario,
            architecture_mode=architecture_mode,
            initial_assignment=args.initial_assignment,
            iteration=iteration,
            objective=current_objective,
            cumulative_gain=cumulative_gain,
            trace_path=trace_path,
            checkpoint_every=args.checkpoint_every,
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
        if args.convergence_window > 0 and len(accepted_rows) >= args.convergence_window:
            recent_rows = accepted_rows[-args.convergence_window :]
            recent_gain = sum(as_float(str(row.get("objective_delta", "0"))) for row in recent_rows)
            final_recent_gain_fraction = recent_gain / baseline_objective if baseline_objective else 0.0
            if final_recent_gain_fraction < args.min_relative_gain:
                stopped_converged = True
                print(
                    "convergence_stop "
                    f"iteration={iteration} window={args.convergence_window} "
                    f"recent_gain={recent_gain:.6f} "
                    f"recent_gain_fraction={final_recent_gain_fraction:.6f} "
                    f"min_relative_gain={args.min_relative_gain:.6f}",
                    flush=True,
                )
                break

    final_crossing, final_conn = crossing_stats(tier, net_to_instances)
    final_area = area_stats(tier, area)
    final_paths = path_cut_stats(paths, tier)
    final_objective = total_objective(tier, net_to_instances, risk)

    write_csv(assignment_path, assignment_rows(rows, tier), list(rows[0].keys()))
    write_csv(
        trace_path,
        accepted_rows,
        TRACE_FIELDNAMES,
    )
    write_csv(
        summary_path,
        [
            {
                "design": args.design,
                "scenario": args.scenario,
                "architecture_mode": architecture_mode,
                "risk_mode": "normalized",
                "lambda_arch": f"{args.lambda_arch:.6f}",
                "lambda_physical": f"{args.lambda_physical:.6f}",
                "lambda_timing": f"{args.lambda_timing:.6f}",
                "normalized_arch_sum": f"{contribution['normalized_arch_sum']:.6f}",
                "normalized_physical_sum": f"{contribution['normalized_physical_sum']:.6f}",
                "normalized_timing_sum": f"{contribution['normalized_timing_sum']:.6f}",
                "normalized_arch_fraction": f"{contribution['normalized_arch_fraction']:.6f}",
                "normalized_physical_fraction": f"{contribution['normalized_physical_fraction']:.6f}",
                "normalized_timing_fraction": f"{contribution['normalized_timing_fraction']:.6f}",
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
                "stopped_converged": str(stopped_converged).lower(),
                "convergence_window": args.convergence_window,
                "min_relative_gain": f"{args.min_relative_gain:.6f}",
                "final_recent_gain_fraction": f"{final_recent_gain_fraction:.6f}",
                "cumulative_dynamic_gain": f"{cumulative_gain:.6f}",
                "assignment_file": str(assignment_path),
            }
        ],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
