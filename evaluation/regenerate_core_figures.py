#!/usr/bin/env python3
"""Regenerate the compact core figure set for ASA-RV3D.

The script deletes no files by itself. Use it after cleaning results/figures.

Generated figures:

1. results/figures/core/asa_rv3d_core_results.svg
   Main result figure with:
   - normalized 3D proxy cost,
   - reduction vs generic,
   - sensitivity margin heatmap.

2. results/figures/core/asa_rv3d_cost_breakdown.svg
   Stacked cost component breakdown.

The layout is deliberately conservative: fixed panels, fixed cell grids, no
free-running bars that can leave the plotting area.
"""

from __future__ import annotations

import csv
from pathlib import Path


OUT_DIR = Path("results/figures/core")
SUMMARY_CSV = Path("results/benchmark_summary/riscv_3d_proxy_cost_summary.csv")
SENS_CSV = Path("results/benchmark_summary/3d_proxy_cost_weight_sensitivity.csv")
DETAIL_CSVS = {
    "ibex": Path("results/benchmark_summary/3d_proxy_cost/ibex_3d_proxy_cost_summary.csv"),
    "riscv32i": Path("results/benchmark_summary/3d_proxy_cost/riscv32i_3d_proxy_cost_summary.csv"),
}

METHODS = ["generic", "connectivity_only", "v2", "v3_context"]
METHOD_LABEL = {
    "generic": "Generic",
    "connectivity_only": "Conn-only",
    "v2": "ASA-v2",
    "v3_context": "ASA-v3",
}
METHOD_COLOR = {
    "generic": "#7f7f7f",
    "connectivity_only": "#4c78a8",
    "v2": "#59a14f",
    "v3_context": "#f28e2b",
}

COMPONENTS = [
    ("base_crossing_cost", "Base crossing", "#a6cee3"),
    ("high_fanout_cost", "High fanout", "#1f78b4"),
    ("control_datapath_boundary_cost", "Ctrl/data boundary", "#b2df8a"),
    ("arch_criticality_cost", "Arch criticality", "#33a02c"),
    ("semantic_uncertainty_cost", "Semantic uncertainty", "#fb9a99"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def val(row: dict[str, str], key: str) -> float:
    return float(row[key])


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def esc(x: object) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_base(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<defs>",
        """
        <style>
          .title { font-family: Arial, Helvetica, sans-serif; font-size: 32px; font-weight: 700; fill: #111827; }
          .subtitle { font-family: Arial, Helvetica, sans-serif; font-size: 17px; fill: #374151; }
          .panel-title { font-family: Arial, Helvetica, sans-serif; font-size: 20px; font-weight: 700; fill: #111827; }
          .axis { stroke: #111827; stroke-width: 1.6; }
          .grid { stroke: #d1d5db; stroke-width: 1; }
          .panel { fill: #ffffff; stroke: #d1d5db; stroke-width: 1.2; rx: 10; }
          .label { font-family: Arial, Helvetica, sans-serif; font-size: 13px; fill: #111827; }
          .tick { font-family: Arial, Helvetica, sans-serif; font-size: 12px; fill: #111827; }
          .value { font-family: Arial, Helvetica, sans-serif; font-size: 12px; font-weight: 700; fill: #111827; }
          .cell-value { font-family: Arial, Helvetica, sans-serif; font-size: 11px; font-weight: 700; fill: #111827; }
          .small { font-family: Arial, Helvetica, sans-serif; font-size: 12px; fill: #4b5563; }
          .caption { font-family: Arial, Helvetica, sans-serif; font-size: 14px; fill: #374151; }
        </style>
        """,
        "</defs>",
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
    ]


def draw_legend(svg: list[str], x: int, y: int, items: list[tuple[str, str]], gap: int = 145) -> None:
    for i, (label, color) in enumerate(items):
        lx = x + i * gap
        svg.append(f'<rect x="{lx}" y="{y - 13}" width="18" height="12" fill="{color}"/>')
        svg.append(f'<text x="{lx + 26}" y="{y - 3}" class="label">{esc(label)}</text>')


def draw_y_axis(svg: list[str], x0: int, y0: int, w: int, h: int, ymax: float, ticks: list[float], fmt) -> None:
    svg.append(f'<line x1="{x0}" y1="{y0}" x2="{x0 + w}" y2="{y0}" class="axis"/>')
    svg.append(f'<line x1="{x0}" y1="{y0 - h}" x2="{x0}" y2="{y0}" class="axis"/>')
    for tick in ticks:
        y = y0 - h * tick / ymax
        svg.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x0 + w}" y2="{y:.1f}" class="grid"/>')
        svg.append(f'<text x="{x0 - 9}" y="{y + 4:.1f}" text-anchor="end" class="tick">{esc(fmt(tick))}</text>')


def color_for_margin(margin: float, max_margin: float) -> str:
    """Blue sequential scale with enough contrast for printed papers."""
    if max_margin <= 0:
        t = 0.0
    else:
        t = max(0.0, min(1.0, margin / max_margin))
    # Interpolate from light blue (#dbeafe) to dark blue (#1d4ed8).
    lo = (219, 234, 254)
    hi = (29, 78, 216)
    rgb = tuple(round(lo[i] + (hi[i] - lo[i]) * t) for i in range(3))
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def make_core_results(summary: list[dict[str, str]], sensitivity: list[dict[str, str]]) -> None:
    width, height = 1800, 1060
    svg = svg_base(width, height)
    svg.append('<text x="900" y="50" text-anchor="middle" class="title">ASA-RV3D Core Experimental Results</text>')
    svg.append('<text x="900" y="78" text-anchor="middle" class="subtitle">Condensed visual evidence: cost reduction, method comparison, and sensitivity robustness.</text>')
    draw_legend(svg, 520, 118, [(METHOD_LABEL[m], METHOD_COLOR[m]) for m in METHODS], gap=175)

    # Panel A.
    px, py, pw, ph = 70, 150, 810, 390
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    svg.append(f'<text x="{px + 28}" y="{py + 40}" class="panel-title">A. Normalized 3D proxy cost</text>')
    svg.append(f'<text x="{px + 28}" y="{py + 64}" class="small">Lower is better; normalized by total net connections.</text>')
    x0, y0, cw, ch = px + 88, py + 315, 650, 220
    ymax = 2.5
    draw_y_axis(svg, x0, y0, cw, ch, ymax, [0, 0.5, 1, 1.5, 2, 2.5], lambda x: f"{x:.1f}")
    bar_w = 34
    for gi, design in enumerate(["ibex", "riscv32i"]):
        gx = x0 + 125 + gi * 315
        for mi, method in enumerate(METHODS):
            row = next(r for r in summary if r["design"] == design and r["case"] == method)
            v = val(row, "normalized_riscv_3d_proxy_cost")
            bh = ch * v / ymax
            x = gx + mi * 48
            y = y0 - bh
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" fill="{METHOD_COLOR[method]}"/>')
            svg.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" class="value">{v:.2f}</text>')
        svg.append(f'<text x="{gx + 72}" y="{y0 + 35}" text-anchor="middle" class="label">{design}</text>')

    # Panel B.
    px, py, pw, ph = 920, 150, 810, 390
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    svg.append(f'<text x="{px + 28}" y="{py + 40}" class="panel-title">B. Reduction vs generic balance</text>')
    svg.append(f'<text x="{px + 28}" y="{py + 64}" class="small">Higher is better; generic is the zero-reference baseline.</text>')
    x0, y0, cw, ch = px + 88, py + 315, 650, 220
    draw_y_axis(svg, x0, y0, cw, ch, 0.8, [0, 0.2, 0.4, 0.6, 0.8], lambda x: f"{int(x * 100)}%")
    methods = ["connectivity_only", "v2", "v3_context"]
    bar_w = 42
    for gi, design in enumerate(["ibex", "riscv32i"]):
        gx = x0 + 140 + gi * 320
        for mi, method in enumerate(methods):
            row = next(r for r in summary if r["design"] == design and r["case"] == method)
            v = val(row, "reduction_vs_generic_3d_proxy")
            bh = ch * v / 0.8
            x = gx + mi * 64
            y = y0 - bh
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{bh:.1f}" fill="{METHOD_COLOR[method]}"/>')
            svg.append(f'<text x="{x + bar_w / 2:.1f}" y="{y - 6:.1f}" text-anchor="middle" class="value">{pct(v)}</text>')
        svg.append(f'<text x="{gx + 75}" y="{y0 + 35}" text-anchor="middle" class="label">{design}</text>')

    # Panel C: fixed heatmap, no overflowing bars.
    px, py, pw, ph = 70, 590, 1660, 350
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    svg.append(f'<text x="{px + 28}" y="{py + 38}" class="panel-title">C. Sensitivity robustness: v3 margin over second-best method</text>')
    svg.append(f'<text x="{px + 28}" y="{py + 62}" class="small">Each cell is one weight setting; darker means v3 beats the second-best method by a larger margin.</text>')
    sens = []
    for r in sensitivity:
        second = val(r, "second_proxy_cost")
        v3 = val(r, "v3_cost")
        rr = dict(r)
        rr["margin"] = (second - v3) / second if second else 0.0
        sens.append(rr)
    cases = [r["weight_case"] for r in sens if r["design"] == "ibex"]
    max_margin = max(float(r["margin"]) for r in sens)
    cell_w, cell_h = 112, 48
    grid_x, grid_y = px + 235, py + 105
    for ci, case in enumerate(cases):
        x = grid_x + ci * cell_w
        svg.append(f'<text x="{x + cell_w / 2:.1f}" y="{grid_y - 12}" text-anchor="middle" class="tick">{esc(case.replace("_", " "))}</text>')
    for ri, design in enumerate(["ibex", "riscv32i"]):
        y = grid_y + ri * cell_h
        svg.append(f'<text x="{grid_x - 18}" y="{y + cell_h / 2 + 4}" text-anchor="end" class="label">{design}</text>')
        for ci, case in enumerate(cases):
            r = next(row for row in sens if row["design"] == design and row["weight_case"] == case)
            margin = float(r["margin"])
            x = grid_x + ci * cell_w
            color = color_for_margin(margin, max_margin)
            svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w - 6}" height="{cell_h - 8}" fill="{color}" stroke="#ffffff" stroke-width="2"/>')
            svg.append(f'<text x="{x + (cell_w - 6) / 2:.1f}" y="{y + cell_h / 2 + 4:.1f}" text-anchor="middle" class="cell-value">{pct(margin)}</text>')
    svg.append(f'<text x="{px + pw / 2}" y="{py + ph - 28}" text-anchor="middle" class="caption">v3 is rank 1 in all 22 design-weight cases; the heatmap shows the margin of that win.</text>')

    svg.append('<text x="900" y="1012" text-anchor="middle" class="caption">Figure: Consolidated ASA-RV3D result visualization after removing low-information exploratory figures.</text>')
    svg.append("</svg>")
    (OUT_DIR / "asa_rv3d_core_results.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")


def make_cost_breakdown(details: dict[str, list[dict[str, str]]]) -> None:
    width, height = 1000, 720
    svg = svg_base(width, height)
    svg.append('<text x="500" y="48" text-anchor="middle" class="title">3D Proxy Cost Breakdown</text>')
    svg.append('<text x="500" y="76" text-anchor="middle" class="subtitle">Stacked components explain where the proxy cost comes from.</text>')
    draw_legend(svg, 105, 118, [(label, color) for _, label, color in COMPONENTS], gap=175)

    px, py, pw, ph = 70, 150, 860, 440
    svg.append(f'<rect x="{px}" y="{py}" width="{pw}" height="{ph}" class="panel"/>')
    x0, y0, cw, ch = px + 80, py + 340, 720, 255
    rows = [r for group in details.values() for r in group]
    ymax = max(val(r, "riscv_3d_proxy_cost") for r in rows) * 1.12
    draw_y_axis(svg, x0, y0, cw, ch, ymax, [0, 30000, 60000, 90000, 120000], lambda x: f"{int(x / 1000)}k")
    bar_w = 34
    group_x = {"ibex": x0 + 105, "riscv32i": x0 + 430}
    for design in ["ibex", "riscv32i"]:
        rows_by_method = {r["case"]: r for r in details[design]}
        gx = group_x[design]
        for mi, method in enumerate(METHODS):
            row = rows_by_method[method]
            x = gx + mi * 50
            y_cursor = y0
            for key, _, color in COMPONENTS:
                h = ch * val(row, key) / ymax
                y_cursor -= h
                svg.append(f'<rect x="{x}" y="{y_cursor:.1f}" width="{bar_w}" height="{h:.1f}" fill="{color}"/>')
            total = val(row, "riscv_3d_proxy_cost")
            svg.append(f'<text x="{x + bar_w / 2}" y="{y_cursor - 6:.1f}" text-anchor="middle" class="value">{int(total / 1000)}k</text>')
            svg.append(f'<text x="{x + bar_w / 2}" y="{y0 + 23}" text-anchor="middle" class="tick">{METHOD_LABEL[method]}</text>')
        svg.append(f'<text x="{gx + 75}" y="{y0 + 58}" text-anchor="middle" class="label">{design}</text>')
    svg.append('<text x="500" y="670" text-anchor="middle" class="caption">Figure: Cost decomposition for generic, connectivity-only, ASA-v2, and ASA-v3 assignments.</text>')
    svg.append("</svg>")
    (OUT_DIR / "asa_rv3d_cost_breakdown.svg").write_text("\n".join(svg) + "\n", encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = read_csv(SUMMARY_CSV)
    sensitivity = read_csv(SENS_CSV)
    details = {design: read_csv(path) for design, path in DETAIL_CSVS.items()}
    make_core_results(summary, sensitivity)
    make_cost_breakdown(details)
    print(OUT_DIR / "asa_rv3d_core_results.svg")
    print(OUT_DIR / "asa_rv3d_cost_breakdown.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
