#!/usr/bin/env python3
"""Extract physical-aware features from ORFS final DEF and RV3D CSV features.

This is the first step of the physical-aware ASA-RV3D mainline.  It connects
the current architecture-aware gate-level flow to physical implementation data
without changing the partition algorithm yet.

Inputs:
  - ORFS final DEF, usually:
      <orfs-flow-dir>/results/<platform>/<design>/base/6_final.def
  - Existing RV3D feature directory:
      results/<design>_features/instance_features.csv
      results/<design>_features/architecture_mapping_instances.csv

Outputs:
  - results/<design>_features/physical_instance_features.csv
  - results/<design>_features/physical_net_features.csv
  - results/<design>_features/physical_unit_summary.csv
  - results/<design>_features/physical_features_manifest.json

The extracted values are physical proxies, not signoff physical metrics.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


CLOCK_RESET_RE = re.compile(r"(^|[_./])(?:clk|clock|rst|reset)(?:$|[_./])|clk_|rst_|reset_", re.IGNORECASE)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def normalize_name(name: str) -> str:
    """Normalize names enough to match DEF and CSV identifiers."""

    out = name.strip()
    if out.startswith("\\"):
        out = out[1:]
    return out


def parse_def(def_path: Path) -> tuple[int, tuple[int, int, int, int] | None, dict[str, dict[str, object]]]:
    """Parse DEF units, die area, and component placement.

    This parser only targets the subset needed here.  It handles common ORFS DEF
    component lines such as:

      - inst_name cell_name + PLACED ( 123 456 ) N ;

    Coordinates are returned in DEF database units.
    """

    units = 1000
    diearea: tuple[int, int, int, int] | None = None
    components: dict[str, dict[str, object]] = {}

    in_components = False
    current = ""

    units_re = re.compile(r"UNITS\s+DISTANCE\s+MICRONS\s+(\d+)", re.IGNORECASE)
    die_re = re.compile(r"DIEAREA\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)\s+\(\s*(-?\d+)\s+(-?\d+)\s*\)", re.IGNORECASE)
    comp_start_re = re.compile(r"^\s*-\s+(\S+)\s+(\S+)")
    placed_re = re.compile(r"\+\s+(PLACED|FIXED|COVER|UNPLACED)\s*(?:\(\s*(-?\d+)\s+(-?\d+)\s*\)\s*(\S+))?", re.IGNORECASE)

    with def_path.open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue

            m = units_re.search(line)
            if m:
                units = int(m.group(1))
                continue

            m = die_re.search(line)
            if m:
                diearea = tuple(int(m.group(i)) for i in range(1, 5))  # type: ignore[assignment]
                continue

            if line.startswith("COMPONENTS "):
                in_components = True
                current = ""
                continue
            if in_components and line.startswith("END COMPONENTS"):
                in_components = False
                current = ""
                continue
            if not in_components:
                continue

            if line.startswith("- "):
                current = line
            else:
                current += " " + line

            if ";" not in line:
                continue

            start = comp_start_re.search(current)
            if not start:
                current = ""
                continue
            inst = normalize_name(start.group(1))
            cell = normalize_name(start.group(2))
            placed = placed_re.search(current)
            status = "UNKNOWN"
            x = y = None
            orient = ""
            if placed:
                status = placed.group(1).upper()
                if placed.group(2) is not None and placed.group(3) is not None:
                    x = int(placed.group(2))
                    y = int(placed.group(3))
                    orient = placed.group(4) or ""
            components[inst] = {
                "cell": cell,
                "status": status,
                "x_dbu": x,
                "y_dbu": y,
                "orient": orient,
            }
            current = ""

    return units, diearea, components


def region_label(norm_x: float | None, norm_y: float | None) -> str:
    if norm_x is None or norm_y is None:
        return "unplaced"
    x_label = "west" if norm_x < 1 / 3 else "center" if norm_x < 2 / 3 else "east"
    y_label = "south" if norm_y < 1 / 3 else "middle" if norm_y < 2 / 3 else "north"
    return f"{y_label}_{x_label}"


def parse_nets(feature_rows: list[dict[str, str]]) -> dict[str, list[str]]:
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in feature_rows:
        inst = normalize_name(row["instance"])
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return dict(net_to_instances)


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", required=True)
    parser.add_argument("--platform", default="sky130hd")
    parser.add_argument("--orfs-flow-dir", type=Path, default=Path("~/openroad-flow-scripts/flow"))
    parser.add_argument("--features-dir", type=Path)
    parser.add_argument("--def-file", type=Path)
    args = parser.parse_args()

    flow_dir = args.orfs_flow_dir.expanduser().resolve()
    features_dir = (args.features_dir or Path("results") / f"{args.design}_features").resolve()
    def_path = (
        args.def_file.expanduser().resolve()
        if args.def_file
        else flow_dir / "results" / args.platform / args.design / "base" / "6_final.def"
    )

    feature_path = features_dir / "instance_features.csv"
    mapping_path = features_dir / "architecture_mapping_instances.csv"
    if not feature_path.exists():
        raise FileNotFoundError(feature_path)
    if not mapping_path.exists():
        raise FileNotFoundError(mapping_path)
    if not def_path.exists():
        raise FileNotFoundError(def_path)

    feature_rows = read_csv(feature_path)
    mapping = {normalize_name(row["instance"]): row for row in read_csv(mapping_path)}
    units_per_micron, diearea, components = parse_def(def_path)

    if diearea:
        die_x0, die_y0, die_x1, die_y1 = diearea
        die_w = max(1, die_x1 - die_x0)
        die_h = max(1, die_y1 - die_y0)
    else:
        placed = [c for c in components.values() if c["x_dbu"] is not None and c["y_dbu"] is not None]
        xs = [int(c["x_dbu"]) for c in placed]
        ys = [int(c["y_dbu"]) for c in placed]
        die_x0, die_y0 = (min(xs), min(ys)) if xs and ys else (0, 0)
        die_x1, die_y1 = (max(xs), max(ys)) if xs and ys else (1, 1)
        die_w = max(1, die_x1 - die_x0)
        die_h = max(1, die_y1 - die_y0)

    net_to_instances = parse_nets(feature_rows)

    component_pos_um: dict[str, tuple[float, float]] = {}
    for inst, comp in components.items():
        x_dbu = comp["x_dbu"]
        y_dbu = comp["y_dbu"]
        if x_dbu is None or y_dbu is None:
            continue
        component_pos_um[inst] = (int(x_dbu) / units_per_micron, int(y_dbu) / units_per_micron)

    net_rows: list[dict[str, object]] = []
    net_metrics: dict[str, dict[str, float | int | str]] = {}
    hpwl_values: list[float] = []

    for net, instances in sorted(net_to_instances.items()):
        unique_instances = sorted(set(instances))
        placed_positions = [component_pos_um[inst] for inst in unique_instances if inst in component_pos_um]
        fanout = len(unique_instances)
        placed_pin_count = len(placed_positions)
        if placed_positions:
            xs = [p[0] for p in placed_positions]
            ys = [p[1] for p in placed_positions]
            hpwl = (max(xs) - min(xs)) + (max(ys) - min(ys))
        else:
            hpwl = 0.0
        hpwl_values.append(hpwl)
        is_clock_reset = 1 if CLOCK_RESET_RE.search(net) else 0
        net_metrics[net] = {
            "fanout": fanout,
            "placed_pin_count": placed_pin_count,
            "hpwl_um": hpwl,
            "is_clock_reset_net": is_clock_reset,
        }
        net_rows.append(
            {
                "net": net,
                "fanout": fanout,
                "placed_pin_count": placed_pin_count,
                "hpwl_um": f"{hpwl:.3f}",
                "is_clock_reset_net": is_clock_reset,
            }
        )

    hpwl_p75 = percentile(hpwl_values, 0.75)
    hpwl_p90 = percentile(hpwl_values, 0.90)
    high_fanout_threshold = 8

    instance_rows: list[dict[str, object]] = []
    unit_acc: dict[str, Counter] = defaultdict(Counter)
    unit_float: dict[str, defaultdict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in feature_rows:
        inst = normalize_name(row["instance"])
        mapped = mapping.get(inst, {})
        unit = mapped.get("architecture_unit", "unclassified")
        group = mapped.get("semantic_group", "infrastructure")
        confidence = float(mapped.get("mapping_confidence", "0.5") or 0.5)

        comp = components.get(inst)
        placed = 1 if inst in component_pos_um else 0
        x_um = y_um = None
        norm_x = norm_y = None
        region = "unplaced"
        if comp and placed:
            x_dbu = int(comp["x_dbu"])  # type: ignore[arg-type]
            y_dbu = int(comp["y_dbu"])  # type: ignore[arg-type]
            x_um = x_dbu / units_per_micron
            y_um = y_dbu / units_per_micron
            norm_x = (x_dbu - die_x0) / die_w
            norm_y = (y_dbu - die_y0) / die_h
            region = region_label(norm_x, norm_y)

        nets = [net.strip() for net in row.get("nets", "").split(";") if net.strip()]
        fanouts = [int(net_metrics[net]["fanout"]) for net in nets if net in net_metrics]
        hpwls = [float(net_metrics[net]["hpwl_um"]) for net in nets if net in net_metrics]
        clock_reset_count = sum(int(net_metrics[net]["is_clock_reset_net"]) for net in nets if net in net_metrics)
        high_fanout_count = sum(1 for value in fanouts if value > high_fanout_threshold)
        long_net_count = sum(1 for value in hpwls if value >= hpwl_p75 and value > 0)
        very_long_net_count = sum(1 for value in hpwls if value >= hpwl_p90 and value > 0)

        mean_fanout = sum(fanouts) / len(fanouts) if fanouts else 0.0
        max_fanout = max(fanouts) if fanouts else 0
        mean_hpwl = sum(hpwls) / len(hpwls) if hpwls else 0.0
        max_hpwl = max(hpwls) if hpwls else 0.0
        total_hpwl = sum(hpwls)

        instance_rows.append(
            {
                "instance": inst,
                "architecture_unit": unit,
                "semantic_group": group,
                "mapping_confidence": f"{confidence:.6f}",
                "placed": placed,
                "x_um": "" if x_um is None else f"{x_um:.3f}",
                "y_um": "" if y_um is None else f"{y_um:.3f}",
                "norm_x": "" if norm_x is None else f"{norm_x:.6f}",
                "norm_y": "" if norm_y is None else f"{norm_y:.6f}",
                "placement_region": region,
                "net_count": len(nets),
                "mean_net_fanout": f"{mean_fanout:.3f}",
                "max_net_fanout": max_fanout,
                "mean_net_hpwl_um": f"{mean_hpwl:.3f}",
                "max_net_hpwl_um": f"{max_hpwl:.3f}",
                "total_net_hpwl_um": f"{total_hpwl:.3f}",
                "clock_reset_net_count": clock_reset_count,
                "high_fanout_net_count": high_fanout_count,
                "long_net_count_p75": long_net_count,
                "very_long_net_count_p90": very_long_net_count,
            }
        )

        acc = unit_acc[unit]
        flt = unit_float[unit]
        acc["instance_count"] += 1
        acc["placed_count"] += placed
        acc[f"region::{region}"] += 1
        acc["clock_reset_net_count"] += clock_reset_count
        acc["high_fanout_net_count"] += high_fanout_count
        acc["long_net_count_p75"] += long_net_count
        acc["very_long_net_count_p90"] += very_long_net_count
        flt["mean_net_fanout_sum"] += mean_fanout
        flt["mean_net_hpwl_sum"] += mean_hpwl
        flt["max_net_hpwl_sum"] += max_hpwl
        flt["total_net_hpwl_sum"] += total_hpwl
        if norm_x is not None and norm_y is not None:
            flt["norm_x_sum"] += norm_x
            flt["norm_y_sum"] += norm_y

    unit_rows: list[dict[str, object]] = []
    for unit, acc in sorted(unit_acc.items(), key=lambda kv: (-kv[1]["instance_count"], kv[0])):
        count = acc["instance_count"]
        placed_count = acc["placed_count"]
        flt = unit_float[unit]
        regions = {k.split("::", 1)[1]: v for k, v in acc.items() if k.startswith("region::")}
        top_region, top_region_count = max(regions.items(), key=lambda kv: kv[1])
        unit_rows.append(
            {
                "architecture_unit": unit,
                "instance_count": count,
                "placed_count": placed_count,
                "placed_fraction": f"{placed_count / count if count else 0.0:.6f}",
                "mean_norm_x": f"{flt['norm_x_sum'] / placed_count if placed_count else 0.0:.6f}",
                "mean_norm_y": f"{flt['norm_y_sum'] / placed_count if placed_count else 0.0:.6f}",
                "top_region": top_region,
                "top_region_fraction": f"{top_region_count / count if count else 0.0:.6f}",
                "mean_net_fanout": f"{flt['mean_net_fanout_sum'] / count if count else 0.0:.3f}",
                "mean_net_hpwl_um": f"{flt['mean_net_hpwl_sum'] / count if count else 0.0:.3f}",
                "mean_max_net_hpwl_um": f"{flt['max_net_hpwl_sum'] / count if count else 0.0:.3f}",
                "total_net_hpwl_um": f"{flt['total_net_hpwl_sum']:.3f}",
                "clock_reset_net_count": acc["clock_reset_net_count"],
                "high_fanout_net_count": acc["high_fanout_net_count"],
                "long_net_count_p75": acc["long_net_count_p75"],
                "very_long_net_count_p90": acc["very_long_net_count_p90"],
            }
        )

    instance_fields = [
        "instance",
        "architecture_unit",
        "semantic_group",
        "mapping_confidence",
        "placed",
        "x_um",
        "y_um",
        "norm_x",
        "norm_y",
        "placement_region",
        "net_count",
        "mean_net_fanout",
        "max_net_fanout",
        "mean_net_hpwl_um",
        "max_net_hpwl_um",
        "total_net_hpwl_um",
        "clock_reset_net_count",
        "high_fanout_net_count",
        "long_net_count_p75",
        "very_long_net_count_p90",
    ]
    net_fields = ["net", "fanout", "placed_pin_count", "hpwl_um", "is_clock_reset_net"]
    unit_fields = [
        "architecture_unit",
        "instance_count",
        "placed_count",
        "placed_fraction",
        "mean_norm_x",
        "mean_norm_y",
        "top_region",
        "top_region_fraction",
        "mean_net_fanout",
        "mean_net_hpwl_um",
        "mean_max_net_hpwl_um",
        "total_net_hpwl_um",
        "clock_reset_net_count",
        "high_fanout_net_count",
        "long_net_count_p75",
        "very_long_net_count_p90",
    ]

    instance_out = features_dir / "physical_instance_features.csv"
    net_out = features_dir / "physical_net_features.csv"
    unit_out = features_dir / "physical_unit_summary.csv"
    manifest_out = features_dir / "physical_features_manifest.json"

    write_csv(instance_out, instance_rows, instance_fields)
    write_csv(net_out, net_rows, net_fields)
    write_csv(unit_out, unit_rows, unit_fields)

    manifest = {
        "design": args.design,
        "platform": args.platform,
        "orfs_flow_dir": str(flow_dir),
        "def_file": str(def_path),
        "features_dir": str(features_dir),
        "def_units_per_micron": units_per_micron,
        "diearea_dbu": list(diearea) if diearea else None,
        "component_count_in_def": len(components),
        "instance_count_in_features": len(feature_rows),
        "placed_feature_instances": sum(1 for row in instance_rows if row["placed"] == 1),
        "net_count": len(net_rows),
        "hpwl_p75_um": round(hpwl_p75, 3),
        "hpwl_p90_um": round(hpwl_p90, 3),
        "outputs": [
            str(instance_out),
            str(net_out),
            str(unit_out),
            str(manifest_out),
        ],
        "note": "Physical features are DEF/feature-derived proxies, not signoff physical metrics.",
    }
    manifest_out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(instance_out)
    print(net_out)
    print(unit_out)
    print(manifest_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
