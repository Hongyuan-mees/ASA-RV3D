#!/usr/bin/env python3
"""Generate two compact SVG figures for final v4b guard090 results.

The script intentionally creates two separate figures:

  1. v4b_guard090_objective_reduction.svg
  2. v4b_guard090_balance_guard.svg

Both use horizontal layouts to avoid rotated labels, clipping, and crowded text.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from xml.sax.saxutils import escape


SCENARIO_LABELS = {
    "control_datapath_split": "control/datapath",
    "memory_near_logic": "memory-near-logic",
    "state_and_clock_protected": "state/clock protected",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def f(row: dict[str, str], key: str) -> float:
    return float(row[key])


def case_label(row: dict[str, str]) -> str:
    return f"{row['design']} | {SCENARIO_LABELS.get(row['scenario'], row['scenario'])}"


def svg_text(x: float, y: float, text: str, size: int = 13, weight: str = "400", anchor: str = "start", fill: str = "#111827") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">{escape(text)}</text>'
    )


def write_svg(path: Path, width: int, height: int, body: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        *body,
        "</svg>",
    ]
    path.write_text("\n".join(svg) + "\n", encoding="utf-8")


def plot_objective_reduction(rows: list[dict[str, str]], out: Path) -> None:
    width = 1120
    height = 620
    margin_left = 245
    margin_right = 145
    top = 112
    row_gap = 66
    bar_h = 22
    axis_w = width - margin_left - margin_right
    max_value = max(f(row, "objective_reduction_vs_baseline") for row in rows)
    domain_max = max(0.03, max_value * 1.18)

    body: list[str] = []
    body.append(svg_text(width / 2, 42, "Guarded Physical-Context Refinement Improves or Preserves Scenario-Aware Results", 24, "700", "middle"))
    body.append(svg_text(width / 2, 70, "Objective reduction is measured against the previous scenario-aware baseline; higher is better.", 14, "400", "middle", "#374151"))

    axis_y = top + row_gap * len(rows) + 8
    body.append(f'<line x1="{margin_left}" y1="{axis_y}" x2="{margin_left + axis_w}" y2="{axis_y}" stroke="#111827" stroke-width="1.2"/>')

    for tick in [0.00, 0.01, 0.02, 0.03]:
        x = margin_left + axis_w * (tick / domain_max)
        body.append(f'<line x1="{x:.1f}" y1="{top - 20}" x2="{x:.1f}" y2="{axis_y}" stroke="#e5e7eb" stroke-width="1"/>')
        body.append(svg_text(x, axis_y + 24, pct(tick), 12, "400", "middle", "#374151"))

    for idx, row in enumerate(rows):
        y = top + idx * row_gap
        label = case_label(row)
        value = f(row, "objective_reduction_vs_baseline")
        bar_w = axis_w * (value / domain_max) if domain_max else 0
        color = "#4f7cac" if row["design"] == "ibex" else "#59a14f"
        body.append(svg_text(34, y + 18, label, 13, "600"))
        body.append(f'<rect x="{margin_left}" y="{y}" width="{bar_w:.1f}" height="{bar_h}" rx="2" fill="{color}"/>')
        label_x = margin_left + max(bar_w + 10, 8)
        body.append(svg_text(label_x, y + 16, pct(value), 13, "700"))

    body.append(svg_text(margin_left + axis_w / 2, height - 34, "Reduction in physical-augmented objective vs scenario-aware baseline", 13, "600", "middle", "#374151"))
    body.append(svg_text(width - 28, height - 18, "Data: results/benchmark_summary/v4b_guard090_summary.csv", 11, "400", "end", "#6b7280"))
    write_svg(out, width, height, body)


def plot_balance_guard(rows: list[dict[str, str]], out: Path) -> None:
    width = 1120
    height = 640
    margin_left = 245
    margin_right = 95
    top = 118
    row_gap = 68
    axis_w = width - margin_left - margin_right
    domain_min = 0.88
    domain_max = 1.01

    def x_of(value: float) -> float:
        return margin_left + axis_w * ((value - domain_min) / (domain_max - domain_min))

    body: list[str] = []
    body.append(svg_text(width / 2, 42, "Balance Guard Check for V4B Physical-Context Refinement", 24, "700", "middle"))
    body.append(svg_text(width / 2, 70, "All final assignments stay at or above the 0.90 instance-balance guard while preserving usable weight balance.", 14, "400", "middle", "#374151"))

    axis_y = top + row_gap * len(rows) + 10
    for tick in [0.88, 0.90, 0.94, 0.98, 1.00]:
        x = x_of(tick)
        stroke = "#ef4444" if abs(tick - 0.90) < 1e-9 else "#e5e7eb"
        dash = ' stroke-dasharray="5 5"' if abs(tick - 0.90) < 1e-9 else ""
        body.append(f'<line x1="{x:.1f}" y1="{top - 24}" x2="{x:.1f}" y2="{axis_y}" stroke="{stroke}" stroke-width="1.2"{dash}/>')
        body.append(svg_text(x, axis_y + 24, f"{tick:.2f}", 12, "400", "middle", "#374151"))
    body.append(svg_text(x_of(0.90) + 8, top - 34, "0.90 guard", 12, "700", "start", "#b91c1c"))
    body.append(f'<line x1="{margin_left}" y1="{axis_y}" x2="{margin_left + axis_w}" y2="{axis_y}" stroke="#111827" stroke-width="1.2"/>')

    for idx, row in enumerate(rows):
        y = top + idx * row_gap
        label = case_label(row)
        inst = f(row, "guarded_instance_balance")
        weight = f(row, "guarded_weight_balance")
        body.append(svg_text(34, y + 18, label, 13, "600"))
        body.append(f'<line x1="{x_of(inst):.1f}" y1="{y + 10:.1f}" x2="{x_of(weight):.1f}" y2="{y + 10:.1f}" stroke="#cbd5e1" stroke-width="2"/>')
        body.append(f'<circle cx="{x_of(inst):.1f}" cy="{y + 10:.1f}" r="7" fill="#4f7cac"/>')
        body.append(f'<rect x="{x_of(weight) - 7:.1f}" y="{y + 3:.1f}" width="14" height="14" fill="#f28e2b"/>')
        body.append(svg_text(x_of(inst), y + 34, f"{inst:.3f}", 11, "600", "middle", "#4f7cac"))
        body.append(svg_text(x_of(weight), y + 50, f"{weight:.3f}", 11, "600", "middle", "#b45309"))

    legend_y = 96
    legend_x = width - 350
    body.append(f'<circle cx="{legend_x}" cy="{legend_y}" r="7" fill="#4f7cac"/>')
    body.append(svg_text(legend_x + 16, legend_y + 4, "Instance balance", 12, "600", "start", "#374151"))
    body.append(f'<rect x="{legend_x + 150}" y="{legend_y - 7}" width="14" height="14" fill="#f28e2b"/>')
    body.append(svg_text(legend_x + 170, legend_y + 4, "Weight balance", 12, "600", "start", "#374151"))

    body.append(svg_text(margin_left + axis_w / 2, height - 34, "Balance ratio after guarded physical-context refinement", 13, "600", "middle", "#374151"))
    body.append(svg_text(width - 28, height - 18, "Data: results/benchmark_summary/v4b_guard090_summary.csv", 11, "400", "end", "#6b7280"))
    write_svg(out, width, height, body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/benchmark_summary/v4b_guard090_summary.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/figures/core"))
    args = parser.parse_args()

    rows = read_csv(args.input)
    rows.sort(key=lambda row: (row["design"] != "ibex", row["scenario"]))

    objective_path = args.output_dir / "v4b_guard090_objective_reduction.svg"
    balance_path = args.output_dir / "v4b_guard090_balance_guard.svg"
    plot_objective_reduction(rows, objective_path)
    plot_balance_guard(rows, balance_path)
    print(objective_path)
    print(balance_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
