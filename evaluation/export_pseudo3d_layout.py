#!/usr/bin/env python3
"""Export pseudo-3D tier layout artifacts from ASA-RV3D assignments.

This is not true 3D placement and routing. It preserves the existing OpenROAD
2D placement coordinates, splits instances by tier assignment, and emits:

  - tier0_instances.csv
  - tier1_instances.csv
  - vertical_interconnect_candidates.csv
  - pseudo3d_layout_summary.csv
  - tier0_layout_proxy.svg
  - tier1_layout_proxy.svg

The vertical interconnect candidates are crossing nets interpreted as TSV /
micro-bump candidates for an early 3DIC partition validation flow.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


DESIGNS = ["riscv32i", "ibex", "picorv32", "scr1_core_tuned"]
SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]

UNIT_COLORS = {
    "clock_reset": "#dc2626",
    "csr": "#7c3aed",
    "decode_control": "#2563eb",
    "fetch": "#0891b2",
    "generated_control": "#60a5fa",
    "pipeline_state": "#f97316",
    "trap_debug": "#be123c",
    "execute_alu": "#16a34a",
    "generated_datapath": "#86efac",
    "load_store": "#0f766e",
    "multdiv": "#65a30d",
    "register_file": "#a16207",
    "unclassified": "#6b7280",
}


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


def f(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def norm_name(name: str) -> str:
    name = name.strip()
    return name[1:] if name.startswith("\\") else name


def esc(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_assignment(path: Path) -> dict[str, str]:
    return {norm_name(row["instance"]): row["tier"] for row in read_csv(path)}


def load_scores(features_dir: Path, filename: str, columns: list[str]) -> dict[str, str]:
    path = features_dir / filename
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for row in read_csv(path):
        inst = norm_name(row.get("instance", ""))
        for col in columns:
            if row.get(col, "") != "":
                out[inst] = row[col]
                break
    return out


def load_features(features_dir: Path) -> tuple[dict[str, dict[str, str]], dict[str, list[str]]]:
    instance_rows = read_csv(features_dir / "instance_features.csv")
    physical_path = features_dir / "physical_instance_features.csv"
    mapping_path = features_dir / "architecture_mapping_instances.csv"

    physical = {norm_name(row["instance"]): row for row in read_csv(physical_path)} if physical_path.exists() else {}
    mapping = {norm_name(row["instance"]): row for row in read_csv(mapping_path)} if mapping_path.exists() else {}
    timing_scores = load_scores(features_dir, "timing_context_scores.csv", ["timing_context_score", "score"])
    physical_scores = load_scores(features_dir, "physical_context_scores.csv", ["physical_context_score", "raw_physical_score"])

    instances: dict[str, dict[str, str]] = {}
    net_to_instances: dict[str, list[str]] = defaultdict(list)
    for row in instance_rows:
        inst = norm_name(row["instance"])
        phys = physical.get(inst, {})
        mp = mapping.get(inst, {})
        architecture_unit = (
            phys.get("architecture_unit")
            or mp.get("architecture_unit")
            or mp.get("architecture_class")
            or row.get("architecture_unit")
            or row.get("arch_class")
            or "unclassified"
        )
        semantic_group = phys.get("semantic_group") or mp.get("semantic_group") or "unknown"
        merged = {
            "instance": inst,
            "cell_type": row.get("cell_type", ""),
            "architecture_unit": architecture_unit,
            "semantic_group": semantic_group,
            "placed": phys.get("placed", "0"),
            "x_um": phys.get("x_um", ""),
            "y_um": phys.get("y_um", ""),
            "norm_x": phys.get("norm_x", ""),
            "norm_y": phys.get("norm_y", ""),
            "placement_region": phys.get("placement_region", "unplaced"),
            "net_count": row.get("net_count", phys.get("net_count", "0")),
            "timing_context_score": timing_scores.get(inst, "0"),
            "physical_context_score": physical_scores.get(inst, "0"),
        }
        instances[inst] = merged
        for net in row.get("nets", "").split(";"):
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return instances, dict(net_to_instances)


def assignment_path(design: str, scenario: str) -> Path:
    return (
        Path("results")
        / f"{design}_tritonpart_timing_regret_guarded_repair"
        / scenario
        / "tritonpart_timing_regret_guarded_repair_assignment.csv"
    )


def placed_xy(row: dict[str, str]) -> tuple[float, float] | None:
    if row.get("x_um", "") == "" or row.get("y_um", "") == "":
        return None
    return f(row["x_um"]), f(row["y_um"])


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(value: int, total: int) -> str:
    return f"{value / total if total else 0.0:.6f}"


def build_tier_rows(
    design: str,
    scenario: str,
    tier: str,
    assignment: dict[str, str],
    instances: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    rows = []
    for inst, assigned_tier in sorted(assignment.items()):
        if assigned_tier != tier or inst not in instances:
            continue
        row = instances[inst]
        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "tier": tier,
                "instance": inst,
                "cell_type": row["cell_type"],
                "architecture_unit": row["architecture_unit"],
                "semantic_group": row["semantic_group"],
                "placed": row["placed"],
                "x_um": row["x_um"],
                "y_um": row["y_um"],
                "norm_x": row["norm_x"],
                "norm_y": row["norm_y"],
                "placement_region": row["placement_region"],
                "net_count": row["net_count"],
                "timing_context_score": row["timing_context_score"],
                "physical_context_score": row["physical_context_score"],
            }
        )
    return rows


def crossing_candidates(
    design: str,
    scenario: str,
    assignment: dict[str, str],
    instances: dict[str, dict[str, str]],
    net_to_instances: dict[str, list[str]],
) -> list[dict[str, object]]:
    rows = []
    for net, raw_connected in sorted(net_to_instances.items()):
        connected = [inst for inst in raw_connected if inst in assignment and inst in instances]
        if not connected:
            continue
        tiers = Counter(assignment[inst] for inst in connected)
        if len(tiers) <= 1:
            continue
        tier0 = [inst for inst in connected if assignment[inst] == "tier0"]
        tier1 = [inst for inst in connected if assignment[inst] == "tier1"]
        vertical_proxy = min(len(tier0), len(tier1))
        units = sorted({instances[inst]["architecture_unit"] for inst in connected})
        groups = sorted({instances[inst]["semantic_group"] for inst in connected})
        timing = [f(instances[inst]["timing_context_score"]) for inst in connected]
        physical = [f(instances[inst]["physical_context_score"]) for inst in connected]

        placed = [placed_xy(instances[inst]) for inst in connected]
        placed = [xy for xy in placed if xy is not None]
        tier0_xy = [placed_xy(instances[inst]) for inst in tier0]
        tier1_xy = [placed_xy(instances[inst]) for inst in tier1]
        tier0_xy = [xy for xy in tier0_xy if xy is not None]
        tier1_xy = [xy for xy in tier1_xy if xy is not None]
        candidate_x = mean([xy[0] for xy in placed])
        candidate_y = mean([xy[1] for xy in placed])
        tier0_x = mean([xy[0] for xy in tier0_xy])
        tier0_y = mean([xy[1] for xy in tier0_xy])
        tier1_x = mean([xy[0] for xy in tier1_xy])
        tier1_y = mean([xy[1] for xy in tier1_xy])
        centroid_separation = math.hypot(tier0_x - tier1_x, tier0_y - tier1_y) if tier0_xy and tier1_xy else 0.0

        rows.append(
            {
                "design": design,
                "scenario": scenario,
                "net": net,
                "fanout": len(connected),
                "tier0_connections": len(tier0),
                "tier1_connections": len(tier1),
                "vertical_connection_proxy": vertical_proxy,
                "placed_connection_fraction": f"{len(placed) / len(connected) if connected else 0.0:.6f}",
                "candidate_x_um": f"{candidate_x:.3f}" if placed else "",
                "candidate_y_um": f"{candidate_y:.3f}" if placed else "",
                "tier0_centroid_x_um": f"{tier0_x:.3f}" if tier0_xy else "",
                "tier0_centroid_y_um": f"{tier0_y:.3f}" if tier0_xy else "",
                "tier1_centroid_x_um": f"{tier1_x:.3f}" if tier1_xy else "",
                "tier1_centroid_y_um": f"{tier1_y:.3f}" if tier1_xy else "",
                "tier_centroid_separation_um": f"{centroid_separation:.3f}",
                "architecture_units": ";".join(units),
                "semantic_groups": ";".join(groups),
                "mean_timing_context_score": f"{mean(timing):.6f}",
                "max_timing_context_score": f"{max(timing) if timing else 0.0:.6f}",
                "timing_weighted_vertical_proxy": f"{vertical_proxy * mean(timing):.6f}",
                "mean_physical_context_score": f"{mean(physical):.6f}",
                "physical_weighted_vertical_proxy": f"{vertical_proxy * mean(physical):.6f}",
            }
        )
    rows.sort(key=lambda row: (-f(row["timing_weighted_vertical_proxy"]), -int(row["vertical_connection_proxy"]), row["net"]))
    return rows


def svg_text(x: float, y: float, value: object, size: int = 12, anchor: str = "middle", weight: str = "400", color: str = "#111827") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{esc(value)}</text>'
    )


def draw_layout_svg(
    path: Path,
    design: str,
    scenario: str,
    tier: str,
    rows: list[dict[str, object]],
    candidates: list[dict[str, object]],
    max_instances: int,
) -> None:
    width, height = 980, 760
    left, top, plot_w, plot_h = 90, 95, 820, 560
    placed_rows = [row for row in rows if row.get("norm_x", "") != "" and row.get("norm_y", "") != ""]
    if len(placed_rows) > max_instances:
        step = max(1, len(placed_rows) // max_instances)
        placed_rows = placed_rows[::step][:max_instances]

    body: list[str] = []
    body.append('<rect width="100%" height="100%" fill="white"/>')
    body.append(svg_text(width / 2, 38, f"{design}: {scenario}", 23, weight="700"))
    body.append(svg_text(width / 2, 65, f"{tier} pseudo-layout view", 14, color="#475569"))
    body.append(f'<rect x="{left}" y="{top}" width="{plot_w}" height="{plot_h}" fill="#f8fafc" stroke="#334155" stroke-width="1.2"/>')

    for i in range(1, 3):
        x = left + plot_w * i / 3
        y = top + plot_h * i / 3
        body.append(f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{top+plot_h:.1f}" stroke="#e2e8f0" stroke-width="1"/>')
        body.append(f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{left+plot_w:.1f}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1"/>')

    for row in placed_rows:
        x = left + plot_w * f(row["norm_x"])
        y = top + plot_h * (1.0 - f(row["norm_y"]))
        unit = str(row.get("architecture_unit", "unclassified"))
        color = UNIT_COLORS.get(unit, "#6b7280")
        score = max(f(row.get("timing_context_score")), f(row.get("physical_context_score")))
        radius = 1.6 + min(3.4, score * 55.0)
        body.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" fill="{color}" fill-opacity="0.55" stroke="none"/>')

    tier_candidate_points = [
        c for c in candidates
        if c.get("candidate_x_um", "") != "" and c.get("candidate_y_um", "")
    ][:160]
    xs = [f(row["x_um"]) for row in rows if row.get("x_um", "") != ""]
    ys = [f(row["y_um"]) for row in rows if row.get("y_um", "") != ""]
    if xs and ys:
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1.0)
        span_y = max(max_y - min_y, 1.0)
        for c in tier_candidate_points:
            cx = left + plot_w * ((f(c["candidate_x_um"]) - min_x) / span_x)
            cy = top + plot_h * (1.0 - (f(c["candidate_y_um"]) - min_y) / span_y)
            body.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="4.2" fill="none" stroke="#111827" stroke-width="1.2" stroke-opacity="0.65"/>')

    body.append(svg_text(left, top + plot_h + 34, f"instances shown: {len(placed_rows)} / placed {len([r for r in rows if r.get('placed') == '1'])}", 12, "start", color="#475569"))
    body.append(svg_text(left, top + plot_h + 56, "black rings: highest timing-risk vertical candidates", 12, "start", color="#475569"))

    legend_units = ["clock_reset", "generated_control", "generated_datapath", "register_file", "pipeline_state", "unclassified"]
    lx, ly = left + 430, top + plot_h + 34
    for idx, unit in enumerate(legend_units):
        x = lx + (idx % 3) * 145
        y = ly + (idx // 3) * 23
        body.append(f'<circle cx="{x:.1f}" cy="{y-4:.1f}" r="5" fill="{UNIT_COLORS.get(unit, "#6b7280")}" fill-opacity="0.7"/>')
        body.append(svg_text(x + 12, y, unit, 11, "start", color="#475569"))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        + "\n".join(body)
        + "\n</svg>\n",
        encoding="utf-8",
    )


def export_one(design: str, scenario: str, output_root: Path, max_svg_instances: int) -> dict[str, object]:
    features_dir = Path("results") / f"{design}_features"
    assignment = load_assignment(assignment_path(design, scenario))
    instances, net_to_instances = load_features(features_dir)

    tier0_rows = build_tier_rows(design, scenario, "tier0", assignment, instances)
    tier1_rows = build_tier_rows(design, scenario, "tier1", assignment, instances)
    candidates = crossing_candidates(design, scenario, assignment, instances, net_to_instances)

    out_dir = output_root / f"{design}_pseudo3d_layout" / scenario
    tier_fields = [
        "design",
        "scenario",
        "tier",
        "instance",
        "cell_type",
        "architecture_unit",
        "semantic_group",
        "placed",
        "x_um",
        "y_um",
        "norm_x",
        "norm_y",
        "placement_region",
        "net_count",
        "timing_context_score",
        "physical_context_score",
    ]
    candidate_fields = [
        "design",
        "scenario",
        "net",
        "fanout",
        "tier0_connections",
        "tier1_connections",
        "vertical_connection_proxy",
        "placed_connection_fraction",
        "candidate_x_um",
        "candidate_y_um",
        "tier0_centroid_x_um",
        "tier0_centroid_y_um",
        "tier1_centroid_x_um",
        "tier1_centroid_y_um",
        "tier_centroid_separation_um",
        "architecture_units",
        "semantic_groups",
        "mean_timing_context_score",
        "max_timing_context_score",
        "timing_weighted_vertical_proxy",
        "mean_physical_context_score",
        "physical_weighted_vertical_proxy",
    ]
    write_csv(out_dir / "tier0_instances.csv", tier0_rows, tier_fields)
    write_csv(out_dir / "tier1_instances.csv", tier1_rows, tier_fields)
    write_csv(out_dir / "vertical_interconnect_candidates.csv", candidates, candidate_fields)
    draw_layout_svg(out_dir / "tier0_layout_proxy.svg", design, scenario, "tier0", tier0_rows, candidates, max_svg_instances)
    draw_layout_svg(out_dir / "tier1_layout_proxy.svg", design, scenario, "tier1", tier1_rows, candidates, max_svg_instances)

    summary = {
        "design": design,
        "scenario": scenario,
        "tier0_instances": len(tier0_rows),
        "tier1_instances": len(tier1_rows),
        "tier0_placed_fraction": pct(sum(1 for row in tier0_rows if row["placed"] == "1"), len(tier0_rows)),
        "tier1_placed_fraction": pct(sum(1 for row in tier1_rows if row["placed"] == "1"), len(tier1_rows)),
        "vertical_interconnect_candidates": len(candidates),
        "vertical_connection_proxy": sum(int(row["vertical_connection_proxy"]) for row in candidates),
        "timing_weighted_vertical_proxy": f"{sum(f(row['timing_weighted_vertical_proxy']) for row in candidates):.6f}",
        "physical_weighted_vertical_proxy": f"{sum(f(row['physical_weighted_vertical_proxy']) for row in candidates):.6f}",
        "top_candidate_net": candidates[0]["net"] if candidates else "",
        "top_candidate_timing_weighted_vertical_proxy": candidates[0]["timing_weighted_vertical_proxy"] if candidates else "0.000000",
        "output_dir": str(out_dir),
    }
    write_csv(out_dir / "pseudo3d_layout_summary.csv", [summary], list(summary.keys()))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", action="append", help="Design to export. Repeatable. Defaults to the four-core suite.")
    parser.add_argument("--scenario", action="append", help="Scenario to export. Repeatable. Defaults to all three scenarios.")
    parser.add_argument("--output-root", type=Path, default=Path("results"))
    parser.add_argument("--summary-dir", type=Path, default=Path("results/benchmark_summary"))
    parser.add_argument("--max-svg-instances", type=int, default=6000)
    args = parser.parse_args()

    designs = args.design or DESIGNS
    scenarios = args.scenario or SCENARIOS
    summaries = []
    for design in designs:
        for scenario in scenarios:
            summaries.append(export_one(design, scenario, args.output_root, args.max_svg_instances))

    args.summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = args.summary_dir / "pseudo3d_layout_summary.csv"
    write_csv(summary_path, summaries, list(summaries[0].keys()) if summaries else ["design"])
    manifest = {
        "note": "Pseudo-3D layout export. Coordinates are inherited from 2D OpenROAD placement; this is not true 3D P&R.",
        "designs": designs,
        "scenarios": scenarios,
        "outputs": [str(summary_path)],
    }
    manifest_path = args.summary_dir / "pseudo3d_layout_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(summary_path)
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
