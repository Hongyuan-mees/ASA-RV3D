#!/usr/bin/env python3
"""Map gate-level instances to RISC-V architecture units.

This is the stage-2 mapper in the ASA-RV3D plan.

It is intentionally separate from the earlier architecture classifier:

  classifier/architecture_classifier.py
      assigns a useful architecture-like class.

  classifier/architecture_mapper.py
      maps each gate-level instance into the formal architecture template
      defined in configs/riscv_architecture_template.yaml.

The mapper uses only lightweight, explainable evidence:

  - instance/module/net name hints,
  - standard-cell hints,
  - previous classifier output when available,
  - graph-context confidence when available.

It does not train a model and does not change partition results. It creates a
more formal gate-level-to-architecture bridge for later scenario-aware 3D
planning.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_UNIT_ORDER = [
    "fetch",
    "decode_control",
    "execute_alu",
    "multdiv",
    "load_store",
    "register_file",
    "csr",
    "pipeline_state",
    "trap_debug",
    "clock_reset",
    "generated_control",
    "generated_datapath",
    "unclassified",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def parse_template(path: Path) -> dict[str, dict[str, object]]:
    """Parse the small project YAML template without requiring PyYAML.

    This is not a general YAML parser. It supports the simple structure used in
    configs/riscv_architecture_template.yaml: architecture_units -> unit ->
    scalar fields plus name_hints/cell_hints lists.
    """

    units: dict[str, dict[str, object]] = {}
    if not path.exists():
        return {}

    in_units = False
    current: str | None = None
    current_list: str | None = None

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped == "architecture_units:":
            in_units = True
            current = None
            current_list = None
            continue

        if in_units and re.match(r"^[a-zA-Z0-9_]+:", stripped):
            # Leaving architecture_units when another top-level key appears.
            if not line.startswith("  "):
                break

        if not in_units:
            continue

        if line.startswith("  ") and not line.startswith("    ") and stripped.endswith(":"):
            current = stripped[:-1]
            units[current] = {
                "name_hints": [],
                "cell_hints": [],
                "semantic_group": "infrastructure",
                "criticality_weight": 1.0,
            }
            current_list = None
            continue

        if current is None:
            continue

        if line.startswith("    ") and not line.startswith("      ") and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = scalar(value)
            current_list = None
            if key in {"name_hints", "cell_hints"}:
                current_list = key
            elif key == "criticality_weight":
                try:
                    units[current][key] = float(value)
                except ValueError:
                    units[current][key] = 1.0
            elif value:
                units[current][key] = value
            continue

        if current_list and stripped.startswith("- "):
            units[current][current_list].append(scalar(stripped[2:]))  # type: ignore[index]

    return units


def default_units() -> dict[str, dict[str, object]]:
    return {
        "fetch": {"semantic_group": "control", "criticality_weight": 2.0, "name_hints": ["fetch", "if_stage", "instr", "imem", "pc_", "pcq", "branch_target", "boot_addr"], "cell_hints": []},
        "decode_control": {"semantic_group": "control", "criticality_weight": 2.0, "name_hints": ["decode", "decoder", "ctrl", "controller", "opcode", "funct3", "funct7", "illegal_insn"], "cell_hints": []},
        "execute_alu": {"semantic_group": "datapath", "criticality_weight": 2.0, "name_hints": ["alu", "adder", "operand", "operator", "result", "compare", "cmp", "shift", "logic"], "cell_hints": []},
        "multdiv": {"semantic_group": "datapath", "criticality_weight": 2.0, "name_hints": ["mult", "div", "mul", "quotient", "remainder"], "cell_hints": []},
        "load_store": {"semantic_group": "datapath", "criticality_weight": 3.5, "name_hints": ["load_store", "lsu", "data_req", "data_gnt", "data_rdata", "data_wdata", "data_addr", "dmem"], "cell_hints": []},
        "register_file": {"semantic_group": "datapath", "criticality_weight": 4.0, "name_hints": ["rf_reg", "register_file", "regfile", "gpr", "waddr", "raddr", "wdata", "rdata"], "cell_hints": []},
        "csr": {"semantic_group": "control", "criticality_weight": 2.5, "name_hints": ["csr", "mstatus", "mtvec", "mepc", "mcause", "mtval", "mcycle", "minstret", "dcsr", "dscratch"], "cell_hints": []},
        "pipeline_state": {"semantic_group": "control", "criticality_weight": 3.0, "name_hints": ["id_stage", "ex_block", "wb_", "stall", "flush", "valid", "ready", "busy", "dff", "dfxtp", "dfr", "dfstp"], "cell_hints": []},
        "trap_debug": {"semantic_group": "control", "criticality_weight": 2.0, "name_hints": ["debug", "ebreak", "exception", "exc_", "irq", "interrupt", "trap", "nmi"], "cell_hints": []},
        "clock_reset": {"semantic_group": "control", "criticality_weight": 5.0, "name_hints": ["clk", "clock", "rst", "reset", "clkbuf", "clkinv"], "cell_hints": []},
        "generated_control": {"semantic_group": "infrastructure", "criticality_weight": 1.2, "name_hints": [], "cell_hints": ["nand", "nor", "and", "or", "mux", "inv", "buf"]},
        "generated_datapath": {"semantic_group": "infrastructure", "criticality_weight": 1.5, "name_hints": [], "cell_hints": ["xor", "xnor", "maj", "fa", "ha", "a21", "a22", "o21", "o22"]},
        "unclassified": {"semantic_group": "infrastructure", "criticality_weight": 1.0, "name_hints": [], "cell_hints": []},
    }


def load_previous_classes(features_dir: Path) -> dict[str, dict[str, str]]:
    path = features_dir / "architecture_instance_classes.csv"
    if not path.exists():
        return {}
    return {row["instance"]: row for row in read_csv(path)}


def load_context_scores(features_dir: Path) -> dict[str, float]:
    path = features_dir / "graph_context_scores.csv"
    if not path.exists():
        return {}
    scores = {}
    for row in read_csv(path):
        try:
            scores[row["instance"]] = float(row["semantic_context_score"])
        except (KeyError, ValueError):
            continue
    return scores


def text_blob(row: dict[str, str]) -> str:
    fields = [
        row.get("instance", ""),
        row.get("module", ""),
        row.get("cell_type", ""),
        row.get("cell", ""),
        row.get("category", ""),
        row.get("nets", ""),
    ]
    return " ".join(fields).lower()


def cell_blob(row: dict[str, str]) -> str:
    fields = [
        row.get("cell_type", ""),
        row.get("cell", ""),
        row.get("category", ""),
    ]
    return " ".join(fields).lower()


def hint_matches(blob: str, hint: str) -> bool:
    hint = hint.lower()
    if not hint:
        return False
    if hint.endswith("_") or hint.startswith("_"):
        return hint in blob
    return re.search(rf"(^|[^a-zA-Z0-9]){re.escape(hint)}($|[^a-zA-Z0-9])", blob) is not None or hint in blob


def score_unit(
    row: dict[str, str],
    unit: str,
    meta: dict[str, object],
    previous_class: str,
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    blob = text_blob(row)
    cblob = cell_blob(row)

    for hint in meta.get("name_hints", []):
        if hint_matches(blob, str(hint)):
            score += 2.0
            evidence.append(f"name:{hint}")

    for hint in meta.get("cell_hints", []):
        if hint_matches(cblob, str(hint)):
            score += 0.8
            evidence.append(f"cell:{hint}")

    if previous_class == unit:
        score += 3.0
        evidence.append("previous_classifier:exact")
    elif previous_class and previous_class != "unclassified":
        prev_group = semantic_group_from_unit(previous_class)
        unit_group = str(meta.get("semantic_group", "infrastructure"))
        if prev_group == unit_group:
            score += 0.5
            evidence.append("previous_classifier:group")

    return score, evidence


def semantic_group_from_unit(unit: str) -> str:
    if unit in {"fetch", "decode_control", "csr", "pipeline_state", "trap_debug", "clock_reset"}:
        return "control"
    if unit in {"execute_alu", "multdiv", "load_store", "register_file"}:
        return "datapath"
    return "infrastructure"


def map_instance(
    row: dict[str, str],
    units: dict[str, dict[str, object]],
    previous: dict[str, str],
    context_score: float,
) -> dict[str, object]:
    previous_class = previous.get("architecture_class", "")
    scored: list[tuple[str, float, list[str]]] = []

    for unit in DEFAULT_UNIT_ORDER:
        if unit not in units:
            continue
        score, evidence = score_unit(row, unit, units[unit], previous_class)
        scored.append((unit, score, evidence))

    scored.sort(key=lambda item: item[1], reverse=True)
    best_unit, best_score, best_evidence = scored[0]
    second_score = scored[1][1] if len(scored) > 1 else 0.0

    if best_score <= 0:
        best_unit = "unclassified"
        best_score = 0.0
        second_score = 0.0
        best_evidence = []

    margin = best_score - second_score
    confidence = min(1.0, (best_score / 6.0) * (0.5 + 0.5 * context_score))
    if best_unit == "unclassified":
        confidence = min(confidence, 0.25)

    meta = units.get(best_unit, units.get("unclassified", {}))
    return {
        "instance": row["instance"],
        "architecture_unit": best_unit,
        "semantic_group": meta.get("semantic_group", semantic_group_from_unit(best_unit)),
        "criticality_weight": meta.get("criticality_weight", 1.0),
        "mapping_score": f"{best_score:.3f}",
        "score_margin": f"{margin:.3f}",
        "mapping_confidence": f"{confidence:.6f}",
        "graph_context_score": f"{context_score:.6f}",
        "previous_architecture_class": previous_class or "none",
        "evidence": ";".join(best_evidence) if best_evidence else "none",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=Path("configs/riscv_architecture_template.yaml"))
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    features_dir = args.features_dir
    output_dir = args.output_dir or features_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    units = parse_template(args.template) or default_units()
    for unit, meta in default_units().items():
        units.setdefault(unit, meta)

    rows = read_csv(features_dir / "instance_features.csv")
    previous = load_previous_classes(features_dir)
    context_scores = load_context_scores(features_dir)

    mapped = []
    for row in rows:
        inst = row["instance"]
        mapped.append(
            map_instance(
                row=row,
                units=units,
                previous=previous.get(inst, {}),
                context_score=context_scores.get(inst, 0.5),
            )
        )

    instance_path = output_dir / "architecture_mapping_instances.csv"
    summary_path = output_dir / "architecture_mapping_summary.csv"
    manifest_path = output_dir / "architecture_mapping_manifest.json"

    fields = [
        "instance",
        "architecture_unit",
        "semantic_group",
        "criticality_weight",
        "mapping_score",
        "score_margin",
        "mapping_confidence",
        "graph_context_score",
        "previous_architecture_class",
        "evidence",
    ]
    write_csv(instance_path, mapped, fields)

    counts = Counter(row["architecture_unit"] for row in mapped)
    group_counts = Counter(row["semantic_group"] for row in mapped)
    confidence_by_unit: dict[str, list[float]] = defaultdict(list)
    for row in mapped:
        confidence_by_unit[str(row["architecture_unit"])].append(float(row["mapping_confidence"]))

    summary_rows = []
    total = len(mapped)
    for unit, count in counts.most_common():
        confidences = confidence_by_unit[unit]
        summary_rows.append(
            {
                "architecture_unit": unit,
                "instance_count": count,
                "fraction": f"{count / total if total else 0.0:.6f}",
                "semantic_group": units.get(unit, {}).get("semantic_group", semantic_group_from_unit(unit)),
                "criticality_weight": units.get(unit, {}).get("criticality_weight", 1.0),
                "mean_mapping_confidence": f"{sum(confidences) / len(confidences) if confidences else 0.0:.6f}",
            }
        )
    write_csv(
        summary_path,
        summary_rows,
        [
            "architecture_unit",
            "instance_count",
            "fraction",
            "semantic_group",
            "criticality_weight",
            "mean_mapping_confidence",
        ],
    )

    manifest = {
        "features_dir": str(features_dir),
        "template": str(args.template),
        "output_dir": str(output_dir),
        "instance_count": total,
        "architecture_unit_count": len(counts),
        "semantic_group_counts": dict(group_counts),
        "outputs": [str(instance_path), str(summary_path), str(manifest_path)],
        "note": "Architecture mapping is a formal gate-level-to-RISC-V-unit bridge, not a final partition result.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(instance_path)
    print(summary_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
