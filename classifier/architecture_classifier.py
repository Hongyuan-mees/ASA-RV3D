#!/usr/bin/env python3
"""Classify extracted Ibex instances into coarse architecture-aware groups.

This classifier intentionally uses transparent rules instead of a trained model.
It is the first bridge between gate-level ORFS data and the project goal:
architecture-aware 2-tier partitioning.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Rule:
    label: str
    weight: int
    pattern: re.Pattern[str]
    description: str


RULES: tuple[Rule, ...] = (
    Rule("clock_reset", 8, re.compile(r"\b(clk|clock|rst|reset)\b|clk_|rst_|reset_", re.I), "clock/reset signal names"),
    Rule("register_file", 10, re.compile(r"rf_reg|register_file|regfile|gpr|waddr|raddr|wdata|rdata", re.I), "integer register file names"),
    Rule("csr", 9, re.compile(r"csr|cs_register|mstatus|mtvec|mepc|mcause|mtval|mcycle|minstret|dcsr|dscratch", re.I), "CSR and privileged-state names"),
    Rule("fetch", 8, re.compile(r"if_stage|fetch|instr|imem|pc_|pcq|branch_target|boot_addr", re.I), "instruction fetch and PC-related names"),
    Rule("decode_control", 8, re.compile(r"decoder|decode|controller|ctrl|illegal_insn|opcode|funct3|funct7", re.I), "decode and control names"),
    Rule("execute_alu", 9, re.compile(r"\balu\b|adder|operand|operator|result|cmp|compare|logic|shift", re.I), "execute and ALU names"),
    Rule("multdiv", 8, re.compile(r"mult|div|mul|quotient|remainder", re.I), "multiply/divide names"),
    Rule("load_store", 8, re.compile(r"load_store|lsu|data_req|data_gnt|data_rdata|data_wdata|data_addr|dmem", re.I), "load/store names"),
    Rule("trap_debug", 7, re.compile(r"debug|ebreak|exception|exc_|irq|interrupt|trap|nmi", re.I), "trap, interrupt, and debug names"),
    Rule("pipeline_state", 6, re.compile(r"id_stage|ex_block|wb_|stall|flush|valid|ready|busy", re.I), "pipeline control/state names"),
)


CELL_HINTS: tuple[Rule, ...] = (
    Rule("pipeline_state", 3, re.compile(r"dff|dfxtp|dfr|dfstp|dlxtp|lat", re.I), "sequential cell hint"),
    Rule("clock_reset", 3, re.compile(r"clkbuf|clkinv", re.I), "clock buffer cell hint"),
    Rule("generated_datapath", 2, re.compile(r"xor|xnor|maj|fa|ha|a21|a22|o21|o22", re.I), "datapath-like standard cell hint"),
    Rule("generated_control", 1, re.compile(r"nand|nor|and|or|mux|inv|buf", re.I), "control/glue standard cell hint"),
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def score_row(row: dict[str, str]) -> tuple[str, int, str]:
    text = " ".join(
        [
            row.get("module", ""),
            row.get("instance", ""),
            row.get("cell_type", ""),
            row.get("category", ""),
            row.get("arch_class", ""),
            row.get("nets", ""),
        ]
    )

    scores: Counter[str] = Counter()
    matched: list[str] = []
    for rule in RULES:
        if rule.pattern.search(text):
            scores[rule.label] += rule.weight
            matched.append(rule.label)

    cell_type = row.get("cell_type", "")
    category = row.get("category", "")
    for rule in CELL_HINTS:
        if rule.pattern.search(cell_type) or rule.pattern.search(category):
            scores[rule.label] += rule.weight
            matched.append(rule.label)

    if not scores:
        return "unclassified", 0, ""

    label, confidence = scores.most_common(1)[0]
    return label, confidence, ";".join(sorted(set(matched)))


def classify(input_csv: Path, output_dir: Path) -> dict[str, object]:
    rows = read_csv(input_csv)
    output_rows: list[dict[str, object]] = []
    label_counts: Counter[str] = Counter()
    category_by_label: dict[str, Counter[str]] = defaultdict(Counter)
    module_by_label: dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        label, confidence, matched_rules = score_row(row)
        label_counts[label] += 1
        category_by_label[label][row.get("category", "")] += 1
        module_by_label[label][row.get("module", "")] += 1
        output_rows.append(
            {
                "module": row.get("module", ""),
                "instance": row.get("instance", ""),
                "cell_type": row.get("cell_type", ""),
                "cell_category": row.get("category", ""),
                "architecture_class": label,
                "confidence": confidence,
                "matched_rules": matched_rules,
                "net_count": row.get("net_count", ""),
            }
        )

    write_csv(
        output_dir / "architecture_instance_classes.csv",
        output_rows,
        [
            "module",
            "instance",
            "cell_type",
            "cell_category",
            "architecture_class",
            "confidence",
            "matched_rules",
            "net_count",
        ],
    )

    summary_rows = []
    total = sum(label_counts.values())
    for label, count in sorted(label_counts.items()):
        summary_rows.append(
            {
                "architecture_class": label,
                "instance_count": count,
                "fraction": f"{(count / total):.6f}" if total else "0.000000",
                "top_cell_category": category_by_label[label].most_common(1)[0][0] if category_by_label[label] else "",
                "top_module": module_by_label[label].most_common(1)[0][0] if module_by_label[label] else "",
            }
        )

    write_csv(
        output_dir / "architecture_summary.csv",
        summary_rows,
        ["architecture_class", "instance_count", "fraction", "top_cell_category", "top_module"],
    )

    manifest = {
        "input_csv": str(input_csv),
        "output_dir": str(output_dir),
        "total_instances": total,
        "class_counts": dict(sorted(label_counts.items())),
        "rules": [
            {
                "label": rule.label,
                "weight": rule.weight,
                "pattern": rule.pattern.pattern,
                "description": rule.description,
            }
            for rule in RULES + CELL_HINTS
        ],
        "outputs": [
            "architecture_instance_classes.csv",
            "architecture_summary.csv",
            "architecture_classifier_manifest.json",
        ],
    }
    (output_dir / "architecture_classifier_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features-dir",
        type=Path,
        default=Path("results") / "ibex_features",
        help="Directory containing instance_features.csv.",
    )
    parser.add_argument("--input-csv", type=Path, default=None, help="Override input instance_features.csv path.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Output directory. Defaults to --features-dir.")
    args = parser.parse_args()

    features_dir = args.features_dir.resolve()
    input_csv = (args.input_csv or (features_dir / "instance_features.csv")).resolve()
    output_dir = (args.output_dir or features_dir).resolve()

    if not input_csv.exists():
        raise FileNotFoundError(f"Missing instance feature CSV: {input_csv}")

    manifest = classify(input_csv, output_dir)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
