#!/usr/bin/env python3
"""Shared net graph and crossing utilities for RV3D evaluations.

The Phase-3 flow uses crossing counts both inside optimizers and in reporting
evaluators.  Keeping the feature-table parsing, instance normalization, and
crossing definitions in one module prevents small count drift between tools.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


NULL_TOKENS = {"", "nan", "none", "null"}


@dataclass(frozen=True)
class NetGraph:
    net_to_instances: dict[str, list[str]]
    inst_to_nets: dict[str, list[str]]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def normalize_instance_name(name: str) -> str:
    name = (name or "").strip()
    if name.startswith("\\"):
        name = name[1:]
    return name


def normalize_lookup_name(name: str) -> str:
    """Canonical key used for cross-tool instance matching."""

    name = normalize_instance_name(name)
    return (
        name.replace("\\", "")
        .replace("$", "")
        .replace("*", "")
        .replace("/", ".")
        .strip()
    )


def split_nets(value: str) -> list[str]:
    if not value:
        return []
    value = value.strip().strip("[]")
    raw = re.split(r"[;|,\s]+", value)
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        net = item.strip().strip("'\"")
        if net.lower() in NULL_TOKENS:
            continue
        if net not in seen:
            seen.add(net)
            out.append(net)
    return out


def assignment_tiers(path: Path) -> dict[str, str]:
    exact_tiers: dict[str, str] = {}
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    for row in read_csv(path):
        inst = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        tier = row.get("tier") or row.get("partition") or row.get("block") or row.get("part") or ""
        if not inst or not tier:
            continue
        if tier in {"0", "part0", "partition0"}:
            tier = "tier0"
        elif tier in {"1", "part1", "partition1"}:
            tier = "tier1"
        norm = normalize_instance_name(inst)
        exact_tiers[norm] = tier
        alias_candidates[normalize_lookup_name(inst)].add(norm)
    tiers = dict(exact_tiers)
    for alias, instances in alias_candidates.items():
        if len(instances) == 1:
            inst = next(iter(instances))
            tiers[alias] = exact_tiers[inst]
    return tiers


def build_assignment_aliases(instances: set[str]) -> dict[str, str]:
    alias_candidates: dict[str, set[str]] = defaultdict(set)
    for inst in instances:
        norm = normalize_instance_name(inst)
        variants = {
            norm,
            normalize_lookup_name(norm),
            norm.replace("\\[", "[").replace("\\]", "]"),
            norm.replace("[", "\\[").replace("]", "\\]"),
            norm.replace("/", "."),
            norm.replace(".", "/"),
        }
        for alias in variants:
            alias_candidates[normalize_instance_name(alias)].add(norm)
            alias_candidates[normalize_lookup_name(alias)].add(norm)
    aliases: dict[str, str] = {}
    for alias, matched in alias_candidates.items():
        if len(matched) == 1:
            aliases[alias] = next(iter(matched))
    return aliases


def resolve_instance(name: str, aliases: dict[str, str]) -> str | None:
    keys = [
        normalize_instance_name(name),
        normalize_lookup_name(name),
        normalize_instance_name(name).replace("\\[", "[").replace("\\]", "]"),
        normalize_instance_name(name).replace("[", "\\[").replace("]", "\\]"),
        normalize_instance_name(name).replace("/", "."),
        normalize_instance_name(name).replace(".", "/"),
    ]
    for key in keys:
        if key in aliases:
            return aliases[key]
        lookup = normalize_lookup_name(key)
        if lookup in aliases:
            return aliases[lookup]
    return None


def load_feature_net_graph(
    features_path: Path,
    assignment_instances: set[str],
    *,
    net_columns: tuple[str, ...] = (
        "nets",
        "net_names",
        "connected_nets",
        "incident_nets",
        "fanout_nets",
        "input_nets",
        "output_nets",
    ),
) -> NetGraph:
    aliases = build_assignment_aliases(assignment_instances)
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    inst_to_nets: dict[str, list[str]] = defaultdict(list)

    for row in read_csv(features_path):
        raw_inst = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        inst = resolve_instance(raw_inst, aliases)
        if not inst:
            continue

        nets: list[str] = []
        for column in net_columns:
            nets.extend(split_nets(row.get(column, "")))
        for net in sorted(set(nets)):
            net_to_instances[net].append(inst)

    filtered_net_to_instances: dict[str, list[str]] = {}
    for net, insts in net_to_instances.items():
        unique = list(dict.fromkeys(insts))
        if len(unique) > 1:
            filtered_net_to_instances[net] = unique
            for inst in unique:
                inst_to_nets[inst].append(net)

    filtered_inst_to_nets = {
        inst: sorted(set(nets))
        for inst, nets in inst_to_nets.items()
        if nets
    }
    return NetGraph(filtered_net_to_instances, filtered_inst_to_nets)


def tier_for_instance(inst: str, tiers: dict[str, str]) -> str:
    return tiers.get(inst) or tiers.get(normalize_lookup_name(inst), "")


def net_tier_counts(tiers: dict[str, str], instances: list[str]) -> tuple[int, int]:
    c0 = 0
    c1 = 0
    for inst in instances:
        tier = tier_for_instance(inst, tiers)
        if tier == "tier0":
            c0 += 1
        elif tier == "tier1":
            c1 += 1
    return c0, c1


def net_is_crossing(tiers: dict[str, str], instances: list[str]) -> bool:
    c0, c1 = net_tier_counts(tiers, instances)
    return bool(c0 and c1)


def crossing_stats(tiers: dict[str, str], net_to_instances: dict[str, list[str]]) -> tuple[int, int]:
    crossing_nets = 0
    crossing_connections = 0
    for instances in net_to_instances.values():
        c0, c1 = net_tier_counts(tiers, instances)
        if c0 and c1:
            crossing_nets += 1
            crossing_connections += min(c0, c1)
    return crossing_nets, crossing_connections
