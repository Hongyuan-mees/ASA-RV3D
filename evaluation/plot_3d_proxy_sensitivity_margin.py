#!/usr/bin/env python3
"""Plot sensitivity margins for the RISC-V-aware 3D proxy cost model.

The figure focuses on a meaningful visual question:

    When v3 is best, by how much does it beat the second-best method?

This is more informative than simply drawing a large "22/22" label.
"""

from __future__ import annotations

import csv
from pathlib import Path


INPUT = Path("results/benchmark_summary/3d_proxy_cost_weight_sensitivity.csv")
OUTPUT = Path("results/figures/summary/riscv_3d_proxy_sensitivity_margin.svg")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def esc(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> int:
    rows = read_rows(INPUT)
    if not rows:
        raise SystemExit(f"empty input: {INPUT}")

    for row in rows:
        v3 = float(row["v3_cost"])
        second = float(row["second_proxy_cost"])
        generic = float(row["generic_cost"])
        row["v3_margin_vs_second"] = (second - v3) / second if second else 0.0
        row["v3_reduction_vs_generic_float"] = float(row["v3_reduction_vs_generic"])
        row["generic_cost_float"] = generic

    designs = ["ibex", "riscv32i"]
    design_rows = {design: [row for row in rows if row["design"] == design] for design in designs}
    weight_cases = [row["weight_case"] for row in design_rows[designs[0]]]

    max_margin = max(float(row["v3_margin_vs_second"]) for row in rows)
    max_reduction = max(float(row["v3_reduction_vs_generic_float"]) for row in rows)

    width = 1800
    height = 1040
    x0 = 250
    y0 = 210
    row_gap = 46
    bar_h = 16
    bar_w = 500
    gap = 160
    panel2_x = x0 + bar_w + gap
    panel2_w = 500

    svg: list[str] = []
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    svg.append("<defs>")
    svg.append(
        """
    <style>
      .title { font-family: Arial, Helvetica, sans-serif; font-size: 36px; font-weight: 700; fill: #111827; }
      .subtitle { font-family: Arial, Helvetica, sans-serif; font-size: 19px; fill: #374151; }
      .panel-title { font-family: Arial, Helvetica, sans-serif; font-size: 23px; font-weight: 700; fill: #111827; }
      .axis { stroke: #111827; stroke-width: 1.8; }
      .grid { stroke: #d1d5db; stroke-width: 1; }
      .tick { font-family: Arial, Helvetica, sans-serif; font-size: 14px; fill: #111827; }
      .label { font-family: Arial, Helvetica, sans-serif; font-size: 14px; fill: #111827; }
      .small { font-family: Arial, Helvetica, sans-serif; font-size: 13px; fill: #4b5563; }
      .value { font-family: Arial, Helvetica, sans-serif; font-size: 13px; fill: #111827; font-weight: 600; }
      .caption { font-family: Arial, Helvetica, sans-serif; font-size: 15px; fill: #374151; }
      .ibex { fill: #4c78a8; }
      .riscv { fill: #f28e2b; }
      .panel { fill: #ffffff; stroke: #d1d5db; stroke-width: 1.3; rx: 10; }
      .callout { fill: #f8fafc; stroke: #cbd5e1; stroke-width: 1.3; rx: 10; }
    </style>
        """
    )
    svg.append("</defs>")
    svg.append('<rect x="0" y="0" width="1800" height="1040" fill="#ffffff"/>')

    svg.append('<text x="900" y="56" text-anchor="middle" class="title">3D Proxy Cost Sensitivity Margin</text>')
    svg.append('<text x="900" y="88" text-anchor="middle" class="subtitle">Robustness is shown by how much graph-context v3 beats the second-best method under each weight setting</text>')

    svg.append('<rect x="70" y="135" width="1660" height="790" class="panel"/>')
    svg.append('<text x="110" y="180" class="panel-title">A. v3 margin over second-best method</text>')
    svg.append('<text x="1040" y="180" class="panel-title">B. v3 reduction relative to generic balance</text>')

    # Axes.
    scale1 = bar_w / (max_margin * 1.10 if max_margin else 1)
    scale2 = panel2_w / (max_reduction * 1.10 if max_reduction else 1)
    axis_y = y0 + len(weight_cases) * row_gap + 12

    svg.append(f'<line x1="{x0}" y1="{axis_y}" x2="{x0 + bar_w}" y2="{axis_y}" class="axis"/>')
    svg.append(f'<line x1="{panel2_x}" y1="{axis_y}" x2="{panel2_x + panel2_w}" y2="{axis_y}" class="axis"/>')

    for tick in [0.0, 0.1, 0.2, 0.3, 0.4]:
        x = x0 + tick * scale1
        if x <= x0 + bar_w:
            svg.append(f'<line x1="{x:.1f}" y1="{y0 - 18}" x2="{x:.1f}" y2="{axis_y}" class="grid"/>')
            svg.append(f'<text x="{x:.1f}" y="{axis_y + 25}" text-anchor="middle" class="tick">{int(tick * 100)}%</text>')

    for tick in [0.0, 0.2, 0.4, 0.6, 0.8]:
        x = panel2_x + tick * scale2
        if x <= panel2_x + panel2_w:
            svg.append(f'<line x1="{x:.1f}" y1="{y0 - 18}" x2="{x:.1f}" y2="{axis_y}" class="grid"/>')
            svg.append(f'<text x="{x:.1f}" y="{axis_y + 25}" text-anchor="middle" class="tick">{int(tick * 100)}%</text>')

    svg.append(f'<text x="{x0 + bar_w / 2}" y="{axis_y + 55}" text-anchor="middle" class="small">Margin: (second-best cost - v3 cost) / second-best cost</text>')
    svg.append(f'<text x="{panel2_x + panel2_w / 2}" y="{axis_y + 55}" text-anchor="middle" class="small">Reduction: (generic cost - v3 cost) / generic cost</text>')

    # Row labels and bars.
    for i, case in enumerate(weight_cases):
        y = y0 + i * row_gap
        svg.append(f'<text x="{x0 - 18}" y="{y + 6}" text-anchor="end" class="label">{esc(case)}</text>')

        ibex = next(row for row in design_rows["ibex"] if row["weight_case"] == case)
        riscv = next(row for row in design_rows["riscv32i"] if row["weight_case"] == case)

        for row, dy, cls, short in [(ibex, -9, "ibex", "Ibex"), (riscv, 11, "riscv", "riscv32i")]:
            margin = float(row["v3_margin_vs_second"])
            reduction = float(row["v3_reduction_vs_generic_float"])
            w1 = margin * scale1
            w2 = reduction * scale2
            svg.append(f'<rect x="{x0}" y="{y + dy - bar_h / 2:.1f}" width="{w1:.1f}" height="{bar_h}" class="{cls}"/>')
            svg.append(f'<text x="{x0 + w1 + 6:.1f}" y="{y + dy + 5:.1f}" class="value">{fmt_pct(margin)}</text>')
            svg.append(f'<rect x="{panel2_x}" y="{y + dy - bar_h / 2:.1f}" width="{w2:.1f}" height="{bar_h}" class="{cls}"/>')
            svg.append(f'<text x="{panel2_x + w2 + 6:.1f}" y="{y + dy + 5:.1f}" class="value">{fmt_pct(reduction)}</text>')

    # Legend.
    legend_y = 945
    svg.append(f'<rect x="690" y="{legend_y - 15}" width="22" height="14" class="ibex"/>')
    svg.append(f'<text x="722" y="{legend_y - 3}" class="label">Ibex</text>')
    svg.append(f'<rect x="790" y="{legend_y - 15}" width="22" height="14" class="riscv"/>')
    svg.append(f'<text x="822" y="{legend_y - 3}" class="label">riscv32i</text>')

    # Compact interpretation callout.
    svg.append('<rect x="1070" y="828" width="570" height="70" class="callout"/>')
    svg.append('<text x="1355" y="858" text-anchor="middle" class="caption">v3 is rank 1 in all 22 design-weight cases.</text>')
    svg.append('<text x="1355" y="883" text-anchor="middle" class="small">The bar lengths show the strength of that advantage, not just the win count.</text>')

    svg.append('<text x="900" y="1008" text-anchor="middle" class="caption">Figure: Sensitivity analysis of ASA-RV3D v3 under 11 RISC-V-aware 3D proxy cost weight settings across two designs.</text>')
    svg.append("</svg>")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(svg) + "\n", encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
