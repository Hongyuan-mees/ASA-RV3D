#!/usr/bin/env python3
"""Extract lightweight features from an ORFS Ibex baseline run.

The script reads public ORFS outputs outside this repository and writes compact
CSV/JSON summaries under this project. It does not copy raw DEF/ODB/GDS/SPEF
artifacts into Git.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


IDENT = r"(?:\\\S+|[A-Za-z_$][A-Za-z0-9_$]*)"
MODULE_RE = re.compile(r"\bmodule\s+(?P<name>[A-Za-z_][A-Za-z0-9_$]*)\b(?P<body>.*?)\bendmodule\b", re.S)
INSTANCE_RE = re.compile(rf"^\s*(?P<cell>{IDENT})\s+(?P<inst>{IDENT})\s*\(", re.S)
PIN_RE = re.compile(r"\.(?P<pin>[A-Za-z_][A-Za-z0-9_$]*)\s*\(\s*(?P<net>.*?)\s*\)", re.S)


@dataclass(frozen=True)
class InstanceFeature:
    module: str
    instance: str
    cell_type: str
    category: str
    arch_class: str
    net_count: int
    nets: str


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def clean_ident(value: str) -> str:
    value = value.strip()
    if value.startswith("\\"):
        return value[1:].strip()
    return value


def normalize_net(value: str) -> str:
    value = re.sub(r"\s+", "", value.strip())
    if value.startswith("\\"):
        return value[1:]
    return value


def iter_semicolon_statements(body: str) -> Iterable[str]:
    current: list[str] = []
    for char in body:
        current.append(char)
        if char == ";":
            statement = "".join(current).strip()
            current = []
            if statement:
                yield statement


def categorize_cell(cell_type: str) -> str:
    name = cell_type.lower()
    if any(token in name for token in ("dff", "dfxtp", "dfr", "dfstp", "dlxtp", "lat")):
        return "sequential"
    if "clkbuf" in name or "clkinv" in name:
        return "clock_buffer"
    if "tap" in name:
        return "tap"
    if "fill" in name or "decap" in name:
        return "fill_or_decap"
    if "diode" in name or "antenna" in name:
        return "antenna"
    if "buf" in name:
        return "buffer"
    if "inv" in name:
        return "inverter"
    return "combinational"


def infer_arch_class(instance: str) -> str:
    name = instance.lower()
    rules = [
        ("alu", "execute_alu"),
        ("mult", "execute_multdiv"),
        ("div", "execute_multdiv"),
        ("rf_reg", "register_file"),
        ("register_file", "register_file"),
        ("decoder", "decoder_control"),
        ("controller", "decoder_control"),
        ("cs_register", "csr"),
        ("csr", "csr"),
        ("load_store", "load_store"),
        ("lsu", "load_store"),
        ("if_stage", "instruction_fetch"),
        ("fetch", "instruction_fetch"),
        ("id_stage", "decode_execute"),
        ("ex_block", "decode_execute"),
    ]
    for token, label in rules:
        if token in name:
            return label
    return "other"


def parse_netlist(verilog_path: Path) -> list[InstanceFeature]:
    text = strip_comments(verilog_path.read_text(encoding="utf-8", errors="replace"))
    features: list[InstanceFeature] = []

    for module_match in MODULE_RE.finditer(text):
        module = module_match.group("name")
        body = module_match.group("body")
        for statement in iter_semicolon_statements(body):
            match = INSTANCE_RE.match(statement)
            if not match:
                continue
            cell_type = clean_ident(match.group("cell"))
            instance = clean_ident(match.group("inst"))
            if cell_type in {"assign", "input", "output", "wire", "reg"}:
                continue

            nets = []
            for pin_match in PIN_RE.finditer(statement):
                net = normalize_net(pin_match.group("net"))
                if net and net not in {"", "1'b0", "1'b1"}:
                    nets.append(net)

            unique_nets = sorted(set(nets))
            features.append(
                InstanceFeature(
                    module=module,
                    instance=instance,
                    cell_type=cell_type,
                    category=categorize_cell(cell_type),
                    arch_class=infer_arch_class(instance),
                    net_count=len(unique_nets),
                    nets=";".join(unique_nets),
                )
            )

    return features


def parse_key_value_reports(flow_dir: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    report_dir = flow_dir / "reports" / "sky130hd" / "ibex" / "base"
    log_dir = flow_dir / "logs" / "sky130hd" / "ibex" / "base"

    finish = report_dir / "6_finish.rpt"
    if finish.exists():
        text = finish.read_text(encoding="utf-8", errors="replace")
        patterns = {
            "tns_max": r"tns max\s+(-?\d+(?:\.\d+)?)",
            "wns_max": r"wns max\s+(-?\d+(?:\.\d+)?)",
            "worst_slack_max": r"worst slack max\s+(-?\d+(?:\.\d+)?)",
            "core_clock_period_min": r"core_clock period_min =\s+(\d+(?:\.\d+)?)",
            "core_clock_fmax": r"core_clock period_min =\s+\d+(?:\.\d+)? fmax =\s+(\d+(?:\.\d+)?)",
        }
        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                values[key] = match.group(1)

    route_drc = report_dir / "5_route_drc.rpt"
    if route_drc.exists():
        values["route_drc_report_lines"] = str(len(route_drc.read_text(encoding="utf-8", errors="replace").splitlines()))

    report_log = log_dir / "6_report.log"
    if report_log.exists():
        text = report_log.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"Design area\s+(\d+)\s+um\^2\s+(\d+)% utilization", text)
        if match:
            values["design_area_um2"] = match.group(1)
            values["utilization_percent"] = match.group(2)
        if "GUI-0077" in text or "Stack trace" in text:
            values["final_report_status"] = "failed_gui"
        else:
            values["final_report_status"] = "clean"

    return values


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orfs-flow-dir", type=Path, default=Path.home() / "openroad-flow-scripts" / "flow")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    flow_dir = args.orfs_flow_dir.expanduser().resolve()
    project_root = args.project_root.expanduser().resolve()
    output_dir = (args.output_dir or (project_root / "results" / "ibex_features")).expanduser().resolve()
    final_v = flow_dir / "results" / "sky130hd" / "ibex" / "base" / "6_final.v"

    if not final_v.exists():
        raise FileNotFoundError(f"Missing final netlist: {final_v}")

    instances = parse_netlist(final_v)
    if not instances:
        raise RuntimeError(f"No instances extracted from {final_v}")

    instance_rows = [asdict(item) for item in instances]
    write_csv(
        output_dir / "instance_features.csv",
        instance_rows,
        ["module", "instance", "cell_type", "category", "arch_class", "net_count", "nets"],
    )

    module_rows = []
    by_module: dict[str, list[InstanceFeature]] = defaultdict(list)
    for item in instances:
        by_module[item.module].append(item)
    for module, items in sorted(by_module.items()):
        category_counts = Counter(item.category for item in items)
        arch_counts = Counter(item.arch_class for item in items)
        module_rows.append(
            {
                "module": module,
                "instance_count": len(items),
                "unique_cell_types": len({item.cell_type for item in items}),
                "sequential_count": category_counts["sequential"],
                "combinational_count": category_counts["combinational"],
                "clock_buffer_count": category_counts["clock_buffer"],
                "buffer_count": category_counts["buffer"],
                "inverter_count": category_counts["inverter"],
                "fill_or_decap_count": category_counts["fill_or_decap"],
                "antenna_count": category_counts["antenna"],
                "top_arch_class": arch_counts.most_common(1)[0][0] if arch_counts else "unknown",
            }
        )
    write_csv(
        output_dir / "module_summary.csv",
        module_rows,
        [
            "module",
            "instance_count",
            "unique_cell_types",
            "sequential_count",
            "combinational_count",
            "clock_buffer_count",
            "buffer_count",
            "inverter_count",
            "fill_or_decap_count",
            "antenna_count",
            "top_arch_class",
        ],
    )

    cell_rows = []
    by_cell = Counter(item.cell_type for item in instances)
    cell_category = {item.cell_type: item.category for item in instances}
    for cell_type, count in sorted(by_cell.items()):
        cell_rows.append({"cell_type": cell_type, "category": cell_category[cell_type], "count": count})
    write_csv(output_dir / "cell_type_summary.csv", cell_rows, ["cell_type", "category", "count"])

    net_counter: Counter[str] = Counter()
    for item in instances:
        for net in filter(None, item.nets.split(";")):
            net_counter[net] += 1
    net_rows = [{"net": net, "connection_count": count} for net, count in sorted(net_counter.items())]
    write_csv(output_dir / "net_summary.csv", net_rows, ["net", "connection_count"])

    report_values = parse_key_value_reports(flow_dir)
    manifest = {
        "orfs_flow_dir": str(flow_dir),
        "input_final_v": str(final_v),
        "output_dir": str(output_dir),
        "instance_count": len(instances),
        "module_count": len(by_module),
        "cell_type_count": len(by_cell),
        "net_count": len(net_counter),
        "report_values": report_values,
        "outputs": [
            "instance_features.csv",
            "module_summary.csv",
            "cell_type_summary.csv",
            "net_summary.csv",
            "manifest.json",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
