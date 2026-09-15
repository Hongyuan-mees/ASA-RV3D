#!/usr/bin/env python3
"""Plot the Stage-5 scenario-aware results.

This script intentionally keeps only high-information figures:

1. scenario_aware_main_results.svg
   Main scenario-aware objective reduction and balance.

2. scenario_architecture_migration.svg
   Architecture units that change tier under different scenarios.

3. scenario_crossing_heatmap_ibex.svg
   Unit-by-scenario crossing bottleneck heatmap for Ibex.

4. scenario_crossing_heatmap_riscv32i.svg
   Unit-by-scenario crossing bottleneck heatmap for riscv32i.

The old combined scenario_architecture_behavior.svg is removed if present,
because its right-side card layout is less readable than a heatmap.
"""

from __future__ import annotations

import csv
from pathlib import Path


OUT_DIR = Path("results/figures/scenario")
SUMMARY = Path("results/benchmark_summary/scenario_aware_partition_summary.csv")
ANALYSIS = Path("results/benchmark_summary/scenario_partition_analysis")

SCENARIOS = ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"]
SCENARIO_LABEL = {
    "control_datapath_split": "Control/datapath",
    "memory_near_logic": "Memory-near-logic",
    "state_and_clock_protected": "State/clock protected",
}
DESIGNS = ["ibex", "riscv32i"]
DESIGN_LABEL = {"ibex": "Ibex", "riscv32i": "riscv32i"}
DESIGN_COLOR = {"ibex": "#4c78a8", "riscv32i": "#f28e2b"}
UNIT_COLOR = {
    "generated_control": "#4c78a8",
    "generated_datapath": "#f28e2b",
    "clock_reset": "#59a14f",
    "register_file": "#b07aa1",
    "pipeline_state": "#e15759",
    "execute_alu": "#76b7b2",
    "fetch": "#edc948",
    "load_store": "#8cd17d",
    "unclassified": "#9c9c9c",
    "csr": "#ff9da7",
    "decode_control": "#bab0ac",
    "trap_debug": "#af7aa1",
    "multdiv": "#9edae5",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict[str, str], key: str) -> float:
    return float(row[key])


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def svg_base(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        """
        <style>
          .title { font-family: Arial, Helvetica, sans-serif; font-size: 31px; font-weight: 700; fill: #111827; }
          .subtitle { font-family: Arial, Helvetica, sans-serif; font-size: 16px; fill: #374151; }
          .panel-title { font-family: Arial, Helvetica, sans-serif; font-size: 20px; font-weight: 700; fill: #111827; }
          .section-title { font-family: Arial, Helvetica, sans-serif; font-size: 18px; font-weight: 700; fill: #111827; }
          .axis { stroke: #111827; stroke-width: 1.5; }
          .grid { stroke: #d1d5db; stroke-width: 1; }
          .panel { fill: #ffffff; stroke: #d1d5db; stroke-width: 1.2; rx: 10; }
          .label { font-family: Arial, Helvetica, sans-serif; font-size: 13px; fill: #111827; }
          .tick { font-family: Arial, Helvetica, sans-serif; font-size: 12px; fill: #111827; }
          .value { font-family: Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 700; fill: #111827; }
          .small { font-family: Arial, Helvetica, sans-serif; font-size: 12px; fill: #4b5563; }
          .caption { font-family: Arial, Helvetica, sans-serif; font-size: 14px; fill: #374151; }
          .cell-value { font-family: Arial, Helvetica, sans-serif; font-size: 13px; font-weight: 700; }
        </style>
        """,
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]


def write_svg(name: str, lines: list[str]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def draw_legend(svg: list[str], x: int, y: int, items: list[tuple[str, str]], gap: int = 150) -> None:
    for index, (label, color) in enumerate(items):
        lx = x + index * gap
        svg.append(f'<rect x="{lx}" y="{y - 13}" width="18" height="12" fill="{color}"/>')
        svg.append(f'<text x="{lx + 26}" y="{y - 3}" class="label">{esc(label)}</text>')


def draw_y_axis(svg: list[str], x0: int, y0: int, width: int, height: int, ymax: float, ticks: list[float], formatter) -> None:
    svg.append(f'<line x1="{x0}" y1="{y0}" x2="{x0 + width}" y2="{y0}" class="axis"/>')
    svg.append(f'<line x1="{x0}" y1="{y0 - height}" x2="{x0}" y2="{y0}" class="axis"/>')
    for tick in ticks:
        y = y0 - height * tick / ymax
        svg.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + width}" y2="{y:.1f}" class="grid"/>')
        svg.append(f'<text x="{x0 - 9}" y="{y + 4:.1f}" text-anchor="end" class="tick">{esc(formatter(tick))}</text>')


def make_main_results(rows: list[dict[str, str]]) -> None:
    width, height = 1700, 880
    svg = svg_base(width, height)
    svg.append('<text x="850" y="50" text-anchor="middle" class="title">Scenario-Aware RISC-V 3D Partitioning Results</text>')
    svg.append('<text x="850" y="78" text-anchor="middle" class="subtitle">Scenario-aware partitioning lowers each scenario objective while retaining usable tier balance.</text>')
    draw_legend(svg, 690, 118, [("Ibex", DESIGN_COLOR["ibex"]), ("riscv32i", DESIGN_COLOR["riscv32i"])])

    px, py, pw, ph = 70, 155, 760, 540
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    svg.append(f'<text x="{px + 28}" y="{py + 40}" class="panel-title">A. Scenario objective reduction vs generic</text>')
    x0, y0, cw, ch = px + 95, py + 405, 600, 295
    draw_y_axis(svg, x0, y0, cw, ch, 0.85, [0, 0.2, 0.4, 0.6, 0.8], lambda x: f"{int(x * 100)}%")
    bar_w = 34
    for si, scenario in enumerate(SCENARIOS):
        sx = x0 + 78 + si * 185
        for di, design in enumerate(DESIGNS):
            row = next(r for r in rows if r["design"] == design and r["scenario"] == scenario)
            value = number(row, "reduction_vs_generic_objective")
            bh = ch * value / 0.85
            x = sx + di * 44
            y = y0 - bh
            svg.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" fill="{DESIGN_COLOR[design]}"/>')
            svg.append(f'<text x="{x + bar_w / 2}" y="{y - 7:.1f}" text-anchor="middle" class="value">{pct(value)}</text>')
        svg.append(f'<text x="{sx + 22}" y="{y0 + 34}" text-anchor="middle" class="tick">{esc(SCENARIO_LABEL[scenario])}</text>')
    svg.append(f'<text x="{x0 + cw / 2}" y="{py + ph - 25}" text-anchor="middle" class="caption">All scenario-aware partitions reduce the scenario objective by roughly 69-79%.</text>')

    px, py, pw, ph = 870, 155, 760, 540
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    svg.append(f'<text x="{px + 28}" y="{py + 40}" class="panel-title">B. Instance balance retained after optimization</text>')
    x0, y0, cw, ch = px + 95, py + 405, 600, 295
    draw_y_axis(svg, x0, y0, cw, ch, 1.0, [0, 0.25, 0.5, 0.75, 1.0], lambda x: f"{x:.2f}")
    for si, scenario in enumerate(SCENARIOS):
        sx = x0 + 78 + si * 185
        for di, design in enumerate(DESIGNS):
            row = next(r for r in rows if r["design"] == design and r["scenario"] == scenario)
            value = number(row, "instance_balance_ratio")
            bh = ch * value
            x = sx + di * 44
            y = y0 - bh
            svg.append(f'<rect x="{x}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" fill="{DESIGN_COLOR[design]}"/>')
            svg.append(f'<text x="{x + bar_w / 2}" y="{y - 7:.1f}" text-anchor="middle" class="value">{value:.2f}</text>')
        svg.append(f'<text x="{sx + 22}" y="{y0 + 34}" text-anchor="middle" class="tick">{esc(SCENARIO_LABEL[scenario])}</text>')
    svg.append(f'<text x="{x0 + cw / 2}" y="{py + ph - 25}" text-anchor="middle" class="caption">The optimization changes architecture placement without collapsing one tier.</text>')

    svg.append('<text x="850" y="825" text-anchor="middle" class="caption">Figure: Main scenario-aware partitioning result across two RISC-V benchmarks and three 3D integration scenarios.</text>')
    svg.append("</svg>")
    write_svg("scenario_aware_main_results.svg", svg)


def migration_units(design: str, top_n: int = 8) -> list[tuple[str, int]]:
    path = ANALYSIS / f"{design}_scenario_unit_migration_summary.csv"
    rows = read_csv(path)
    items = [
        (row["architecture_unit"], int(row["migrating_instances"]))
        for row in rows
        if row["design"] == design
    ]
    return items[:top_n]


def make_migration_figure() -> None:
    width, height = 1450, 850
    svg = svg_base(width, height)
    svg.append('<text x="725" y="50" text-anchor="middle" class="title">Architecture Units That Move Across 3D Scenarios</text>')
    svg.append('<text x="725" y="78" text-anchor="middle" class="subtitle">Scenario changes mostly move flexible generated logic; sensitive architecture units move much less.</text>')

    panel_w, panel_h = 620, 610
    for di, design in enumerate(DESIGNS):
        px = 80 + di * 675
        py = 135
        svg.append(f'<rect x="{px}" y="{py}" width="{panel_w}" height="{panel_h}" class="panel"/>')
        svg.append(f'<text x="{px + 28}" y="{py + 42}" class="panel-title">{DESIGN_LABEL[design]}</text>')
        units = migration_units(design)
        max_count = max(count for _, count in units) if units else 1
        label_x = px + 34
        bar_x = px + 210
        top_y = py + 95
        bar_max = 340
        for ui, (unit, count) in enumerate(units):
            y = top_y + ui * 48
            bw = bar_max * count / max_count
            color = UNIT_COLOR.get(unit, "#9c9c9c")
            svg.append(f'<text x="{label_x}" y="{y + 14}" class="tick">{esc(unit)}</text>')
            svg.append(f'<rect x="{bar_x}" y="{y}" width="{bw:.1f}" height="22" fill="{color}"/>')
            svg.append(f'<text x="{bar_x + bw + 10:.1f}" y="{y + 16}" class="value">{count}</text>')
        svg.append(f'<text x="{px + panel_w / 2}" y="{py + panel_h - 28}" text-anchor="middle" class="caption">Number of instances whose tier differs across scenarios.</text>')

    svg.append('<text x="725" y="800" text-anchor="middle" class="caption">Figure: Architecture-unit migration summary across memory-near-logic, control/datapath, and state/clock-protected scenarios.</text>')
    svg.append("</svg>")
    write_svg("scenario_architecture_migration.svg", svg)


def crossing_matrix(design: str) -> tuple[list[str], dict[tuple[str, str], int], int]:
    path = ANALYSIS / f"{design}_scenario_crossing_units.csv"
    rows = read_csv(path)
    matrix: dict[tuple[str, str], int] = {}
    totals: dict[str, int] = {}
    max_value = 0
    for row in rows:
        if row["design"] != design:
            continue
        scenario = row["scenario"]
        unit = row["architecture_unit"]
        value = int(row["crossing_net_count"])
        if value <= 0:
            continue
        matrix[(unit, scenario)] = value
        totals[unit] = totals.get(unit, 0) + value
        max_value = max(max_value, value)
    ordered_units = sorted(totals, key=lambda u: (-totals[u], u))
    return ordered_units, matrix, max_value


def heat_color(value: int, max_value: int) -> str:
    if max_value <= 0:
        return "#eff6ff"
    t = value / max_value
    start = (239, 246, 255)
    end = (29, 78, 216)
    r = round(start[0] + (end[0] - start[0]) * t)
    g = round(start[1] + (end[1] - start[1]) * t)
    b = round(start[2] + (end[2] - start[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def draw_heatmap(svg: list[str], design: str, x: int, y: int, width: int) -> int:
    units, matrix, max_value = crossing_matrix(design)
    cell_w = 250
    cell_h = 34
    label_w = 220
    header_h = 56
    body_h = len(units) * cell_h
    height = header_h + body_h + 45

    svg.append(f'<rect x="{x}" y="{y}" width="{width}" height="{height}" class="panel"/>')
    svg.append(f'<text x="{x + 26}" y="{y + 34}" class="section-title">{DESIGN_LABEL[design]}</text>')
    for ci, scenario in enumerate(SCENARIOS):
        cx = x + label_w + ci * cell_w
        svg.append(f'<text x="{cx + cell_w / 2}" y="{y + 34}" text-anchor="middle" class="label">{esc(SCENARIO_LABEL[scenario])}</text>')

    for ri, unit in enumerate(units):
        cy = y + header_h + ri * cell_h
        svg.append(f'<text x="{x + 24}" y="{cy + 22}" class="tick">{esc(unit)}</text>')
        for ci, scenario in enumerate(SCENARIOS):
            value = matrix.get((unit, scenario), 0)
            cx = x + label_w + ci * cell_w
            color = heat_color(value, max_value)
            text_color = "#ffffff" if max_value and value / max_value > 0.58 else "#111827"
            svg.append(f'<rect x="{cx}" y="{cy}" width="{cell_w - 8}" height="{cell_h - 4}" fill="{color}" stroke="#ffffff" stroke-width="1"/>')
            svg.append(f'<text x="{cx + (cell_w - 8) / 2}" y="{cy + 21}" text-anchor="middle" class="cell-value" fill="{text_color}">{value}</text>')

    legend_x = x + label_w + 3 * cell_w - 185
    legend_y = y + height - 27
    svg.append(f'<text x="{legend_x - 68}" y="{legend_y + 10}" class="small">Low</text>')
    for i in range(6):
        color = heat_color(round(max_value * i / 5), max_value)
        svg.append(f'<rect x="{legend_x + i * 24}" y="{legend_y}" width="24" height="12" fill="{color}"/>')
    svg.append(f'<text x="{legend_x + 155}" y="{legend_y + 10}" class="small">High crossing count</text>')
    return height


def make_crossing_heatmap(design: str) -> str:
    units, _, _ = crossing_matrix(design)
    width = 1350
    # Dynamic canvas height prevents truncation when a design has many unit rows.
    height = 245 + 56 + len(units) * 34 + 80
    svg = svg_base(width, height)
    svg.append(f'<text x="675" y="50" text-anchor="middle" class="title">{DESIGN_LABEL[design]} Scenario Crossing Bottlenecks</text>')
    svg.append('<text x="675" y="78" text-anchor="middle" class="subtitle">Each cell reports crossing net count for one architecture unit under one 3D integration scenario.</text>')

    x = 95
    y = 125
    panel_w = 1160
    draw_heatmap(svg, design, x, y, panel_w)

    svg.append(f'<text x="675" y="{height - 35}" text-anchor="middle" class="caption">Figure: Heatmap view of {DESIGN_LABEL[design]} unit-level crossing bottlenecks. Darker cells mark dominant architecture units.</text>')
    svg.append("</svg>")
    filename = f"scenario_crossing_heatmap_{design}.svg"
    write_svg(filename, svg)
    return filename


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    old_combined = OUT_DIR / "scenario_architecture_behavior.svg"
    if old_combined.exists():
        old_combined.unlink()
    old_heatmap = OUT_DIR / "scenario_crossing_heatmap.svg"
    if old_heatmap.exists():
        old_heatmap.unlink()

    make_main_results(read_csv(SUMMARY))
    make_migration_figure()
    heatmap_files = [make_crossing_heatmap(design) for design in DESIGNS]

    print(OUT_DIR / "scenario_aware_main_results.svg")
    print(OUT_DIR / "scenario_architecture_migration.svg")
    for filename in heatmap_files:
        print(OUT_DIR / filename)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
