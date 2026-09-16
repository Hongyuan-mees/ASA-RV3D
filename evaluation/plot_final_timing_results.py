#!/usr/bin/env python3
import csv
from pathlib import Path

SRC = Path("results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv")
OUT_DIR = Path("results/figures/final")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DESIGN_LABEL = {
    "riscv32i": "riscv32i",
    "ibex": "Ibex",
}

SCENARIO_LABEL = {
    "control_datapath_split": "Control/datapath",
    "memory_near_logic": "Memory-near-logic",
    "state_and_clock_protected": "State/clock protected",
}

METHODS = [
    ("TritonPart", "tritonpart_timing_weighted_crossing", "#7A7A7A"),
    ("Guarded repair", "guarded_timing_weighted_crossing", "#4C78A8"),
    ("Timing-regret repair", "timing_regret_guarded_timing_weighted_crossing", "#F28E2B"),
]

def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def pct(value):
    return f"{float(value) * 100:.1f}%"

def draw_svg(design, rows):
    width = 1120
    height = 620
    margin_left = 215
    margin_right = 70
    margin_top = 112
    plot_width = width - margin_left - margin_right
    row_gap = 132
    bar_h = 22
    bar_gap = 9
    max_value = max(float(r[m[1]]) for r in rows for m in METHODS)
    axis_max = max_value * 1.16

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">')
    parts.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    parts.append(f'<text x="{width/2:.0f}" y="42" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="27" font-weight="700" fill="#111827">{esc(DESIGN_LABEL[design])}: Timing-Weighted Crossing</text>')
    parts.append(f'<text x="{width/2:.0f}" y="72" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="15" fill="#374151">Lower is better. Timing-regret repair limits moves that increase OpenSTA-derived timing risk.</text>')

    legend_x = margin_left
    legend_y = 96
    for i, (name, _, color) in enumerate(METHODS):
        x = legend_x + i * 210
        parts.append(f'<rect x="{x}" y="{legend_y - 13}" width="15" height="15" fill="{color}"/>')
        parts.append(f'<text x="{x + 23}" y="{legend_y}" font-family="Arial, Helvetica, sans-serif" font-size="14" fill="#111827">{esc(name)}</text>')

    axis_y = margin_top + len(rows) * row_gap + 26
    parts.append(f'<line x1="{margin_left}" y1="{axis_y}" x2="{margin_left + plot_width}" y2="{axis_y}" stroke="#4B5563" stroke-width="1.2"/>')

    tick_count = 5
    for i in range(tick_count + 1):
        value = axis_max * i / tick_count
        x = margin_left + plot_width * value / axis_max
        parts.append(f'<line x1="{x:.1f}" y1="{margin_top - 18}" x2="{x:.1f}" y2="{axis_y}" stroke="#E5E7EB" stroke-width="1"/>')
        parts.append(f'<text x="{x:.1f}" y="{axis_y + 24}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#4B5563">{value:.1f}</text>')

    for idx, row in enumerate(rows):
        group_y = margin_top + idx * row_gap
        scenario = SCENARIO_LABEL[row["scenario"]]
        reduction = pct(row["reduction_vs_guarded"])

        parts.append(f'<text x="32" y="{group_y + 32}" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="700" fill="#111827">{esc(scenario)}</text>')
        parts.append(f'<text x="32" y="{group_y + 55}" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#4B5563">vs guarded: -{reduction}</text>')

        for j, (name, key, color) in enumerate(METHODS):
            value = float(row[key])
            y = group_y + j * (bar_h + bar_gap)
            bar_w = plot_width * value / axis_max
            parts.append(f'<rect x="{margin_left}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="0" fill="{color}"/>')
            label_x = min(margin_left + bar_w + 9, width - margin_right - 12)
            anchor = "start" if label_x < width - margin_right - 20 else "end"
            parts.append(f'<text x="{label_x:.1f}" y="{y + 16}" text-anchor="{anchor}" font-family="Arial, Helvetica, sans-serif" font-size="13" font-weight="700" fill="#111827">{value:.3f}</text>')

    parts.append(f'<text x="{width/2:.0f}" y="{height - 24}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="#4B5563">Source: results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv</text>')
    parts.append("</svg>")
    return "\n".join(parts)

def main():
    rows = list(csv.DictReader(SRC.open(newline="", encoding="utf-8")))
    for design in ["riscv32i", "ibex"]:
        design_rows = [r for r in rows if r["design"] == design]
        design_rows.sort(key=lambda r: ["control_datapath_split", "memory_near_logic", "state_and_clock_protected"].index(r["scenario"]))
        svg = draw_svg(design, design_rows)
        out = OUT_DIR / f"{design}_timing_weighted_crossing.svg"
        out.write_text(svg, encoding="utf-8")
        print(out)

if __name__ == "__main__":
    main()
