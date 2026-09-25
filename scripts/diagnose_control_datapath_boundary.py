#!/usr/bin/env python3
"""Diagnose why control/datapath boundary crossings are zero.

This script inspects crossing nets and reports whether each crossing net touches
control-like instances, datapath-like instances, both, or neither.  It is a
diagnostic only; it does not write result tables.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


CONTROL_WORDS = ("control", "decoder", "decode", "branch", "fetch")
DATAPATH_WORDS = (
    "datapath",
    "alu",
    "operand",
    "writedata",
    "readdata",
    "cpuregs",
    "regfile",
    "register_file",
    "load",
    "store",
    "mem",
    "lsu",
)


def normalize_name(name: str) -> str:
    return name.strip().replace("\\", "").replace("$", "").replace("*", "").replace("/", ".")


def split_nets(value: str) -> list[str]:
    return [x for x in re.split(r"[;|,\s]+", value.strip()) if x]


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_assignment(path: Path) -> dict[str, str]:
    tiers: dict[str, str] = {}
    for row in read_rows(path):
        inst = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        tier = row.get("tier") or row.get("partition") or row.get("block") or row.get("part") or ""
        if not inst or not tier:
            continue
        if tier in {"0", "part0", "partition0"}:
            tier = "tier0"
        elif tier in {"1", "part1", "partition1"}:
            tier = "tier1"
        tiers[inst] = tier
        tiers[normalize_name(inst)] = tier
    return tiers


def classify(row: dict[str, str]) -> tuple[bool, bool, str]:
    text = " ".join(
        [
            row.get("module", ""),
            row.get("instance", ""),
            row.get("cell_type", ""),
            row.get("category", ""),
            row.get("arch_class", ""),
            row.get("nets", ""),
        ]
    ).lower()
    control = any(word in text for word in CONTROL_WORDS)
    datapath = any(word in text for word in DATAPATH_WORDS)
    label = []
    if control:
        label.append("control")
    if datapath:
        label.append("datapath")
    return control, datapath, "+".join(label) or "other"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=25)
    args = parser.parse_args()

    tiers = load_assignment(args.assignment)
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    inst_class: dict[str, tuple[bool, bool, str]] = {}

    for row in read_rows(args.features):
        inst = row.get("instance") or row.get("inst") or row.get("name") or row.get("cell") or ""
        if not inst:
            continue
        cls = classify(row)
        inst_class[inst] = cls
        inst_class[normalize_name(inst)] = cls
        for net in split_nets(row.get("nets", "")):
            net_to_instances[net].append(inst)

    counts = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    for net, instances in net_to_instances.items():
        tier_set = {
            tiers.get(inst) or tiers.get(normalize_name(inst))
            for inst in instances
            if tiers.get(inst) or tiers.get(normalize_name(inst))
        }
        if len(tier_set) <= 1:
            continue
        control_tiers = set()
        datapath_tiers = set()
        labels = Counter()
        for inst in instances:
            tier = tiers.get(inst) or tiers.get(normalize_name(inst))
            control, datapath, label = inst_class.get(inst) or inst_class.get(normalize_name(inst), (False, False, "unknown"))
            labels[label] += 1
            if control and tier:
                control_tiers.add(tier)
            if datapath and tier:
                datapath_tiers.add(tier)
        if control_tiers and datapath_tiers and (control_tiers - datapath_tiers or datapath_tiers - control_tiers):
            bucket = "strict_control_datapath_boundary"
        elif control_tiers and datapath_tiers:
            bucket = "control_and_datapath_same_tier_only"
        elif control_tiers:
            bucket = "control_only_crossing"
        elif datapath_tiers:
            bucket = "datapath_only_crossing"
        else:
            bucket = "neither_control_nor_datapath"
        counts[bucket] += 1
        if len(samples[bucket]) < args.samples:
            samples[bucket].append(
                f"{net}: tiers={sorted(t for t in tier_set if t)} control_tiers={sorted(control_tiers)} "
                f"datapath_tiers={sorted(datapath_tiers)} labels={dict(labels.most_common(6))}"
            )

    print("crossing_net_class_counts")
    for key, value in counts.most_common():
        print(f"{key},{value}")
    print()
    for bucket, rows in samples.items():
        print(f"sample_{bucket}")
        for row in rows:
            print(row)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
