#!/usr/bin/env python3
"""Create summary-style SVG figures for the partition experiments.

The script uses only the Python standard library and writes editable SVG files.
It is intended for report/report figures, not for quick debugging plots.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


TEXT = "#1f2937"
MUTED = "#64748b"
GRID = "#d8dee9"
AXIS = "#334155"
GENERIC = "#4e79a7"
ARCH_V1 = "#f28e2b"
SCORE_V2 = "#59a14f"
LIGHT_BG = "#f8fafc"
REDUCTION = "#2f855a"

STRATEGIES = ["generic_balance", "architecture_aware_v1", "architecture_score_v2"]
STRATEGY_LABELS = {
    "generic_balance": "Generic",
    "architecture_aware_v1": "Arch-aware v1",
    "architecture_score_v2": "Score v2",
}
STRATEGY_COLORS = {
    "generic_balance": GENERIC,
    "architecture_aware_v1": ARCH_V1,
    "architecture_score_v2": SCORE_V2,
}


def escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def svg_text(
    x: float,
    y: float,
    text: object,
    size: int = 12,
    anchor: str = "middle",
    weight: str = "400",
    color: str = TEXT,
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{escape(text)}</text>'
    )


def svg_doc(width: int, height: int, body: Iterable[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="100%" height="100%" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def line(x1: float, y1: float, x2: float, y2: float, color: str = GRID, width: float = 1.0) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{width}"/>'


def rect(x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1.0) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def circle(x: float, y: float, r: float, fill: str, stroke: str = "white", sw: float = 1.2) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def ordered_partition_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_strategy = {row["strategy"]: row for row in rows}
    return [by_strategy[strategy] for strategy in STRATEGIES if strategy in by_strategy]


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_main_results(path: Path, rows: list[dict[str, str]]) -> None:
    rows = ordered_partition_rows(rows)
    width, height = 1280, 620
    body: list[str] = []

    body.append(svg_text(width / 2, 38, "Partition Results on Ibex ORFS Baseline", 24, weight="700"))
    body.append(svg_text(width / 2, 62, "Lower crossing is better; higher balance is better", 13, color=MUTED))

    # Left panel: crossing connection proxy.
    lx, ly, lw, lh = 85, 115, 500, 360
    body.append(svg_text(lx + lw / 2, 96, "(a) Crossing connection proxy", 16, weight="700"))
    max_cross = max(float(row["crossing_connections_proxy"]) for row in rows) * 1.18
    for i in range(5):
        y = ly + lh - lh * i / 4
        value = max_cross * i / 4
        body.append(line(lx, y, lx + lw, y))
        body.append(svg_text(lx - 12, y + 4, f"{value:.0f}", 11, "end", color=MUTED))
    body.append(line(lx, ly, lx, ly + lh, AXIS, 1.2))
    body.append(line(lx, ly + lh, lx + lw, ly + lh, AXIS, 1.2))

    bar_w = 86
    gap = 52
    generic_cross = float(rows[0]["crossing_connections_proxy"])
    for idx, row in enumerate(rows):
        strategy = row["strategy"]
        value = float(row["crossing_connections_proxy"])
        h = lh * value / max_cross
        x = lx + 80 + idx * (bar_w + gap)
        y = ly + lh - h
        body.append(rect(x, y, bar_w, h, STRATEGY_COLORS[strategy]))
        body.append(svg_text(x + bar_w / 2, y - 10, f"{value:.0f}", 12, weight="700"))
        label = STRATEGY_LABELS[strategy]
        body.append(svg_text(x + bar_w / 2, ly + lh + 30, label, 12))
        if idx > 0:
            reduction = (generic_cross - value) / generic_cross
            body.append(svg_text(x + bar_w / 2, ly + lh + 50, f"-{pct(reduction)}", 12, weight="700", color=REDUCTION))

    # Right panel: balance ratios.
    rx, ry, rw, rh = 705, 115, 500, 360
    body.append(svg_text(rx + rw / 2, 96, "(b) Balance ratios", 16, weight="700"))
    for i in range(6):
        y = ry + rh - rh * i / 5
        value = i / 5
        body.append(line(rx, y, rx + rw, y))
        body.append(svg_text(rx - 12, y + 4, f"{value:.1f}", 11, "end", color=MUTED))
    body.append(line(rx, ry, rx, ry + rh, AXIS, 1.2))
    body.append(line(rx, ry + rh, rx + rw, ry + rh, AXIS, 1.2))

    metrics = [("instance_balance_ratio", "Instance"), ("weight_balance_ratio", "Weight")]
    group_w = rw / 2
    small_bar_w = 44
    for m_idx, (metric, label) in enumerate(metrics):
        cx = rx + group_w * (m_idx + 0.5)
        for r_idx, row in enumerate(rows):
            strategy = row["strategy"]
            value = float(row[metric])
            h = rh * value
            x = cx + (r_idx - 1) * (small_bar_w + 12) - small_bar_w / 2
            y = ry + rh - h
            body.append(rect(x, y, small_bar_w, h, STRATEGY_COLORS[strategy]))
            body.append(svg_text(x + small_bar_w / 2, y - 8, f"{value:.3f}", 10))
        body.append(svg_text(cx, ry + rh + 32, label, 12))

    # Legend.
    legend_y = height - 54
    legend_x = width / 2 - 265
    for idx, strategy in enumerate(STRATEGIES):
        x = legend_x + idx * 190
        body.append(rect(x, legend_y - 12, 14, 14, STRATEGY_COLORS[strategy]))
        body.append(svg_text(x + 22, legend_y, STRATEGY_LABELS[strategy], 12, "start"))

    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def heat_color(value: float, low: float, high: float) -> str:
    if high <= low:
        t = 1.0
    else:
        t = max(0.0, min(1.0, (value - low) / (high - low)))
    # Colorblind-friendly blue to green gradient.
    c0 = (222, 235, 247)
    c1 = (49, 130, 93)
    r = round(c0[0] + (c1[0] - c0[0]) * t)
    g = round(c0[1] + (c1[1] - c0[1]) * t)
    b = round(c0[2] + (c1[2] - c0[2]) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def write_sweep_heatmap(path: Path, rows: list[dict[str, str]]) -> None:
    arch_weights = sorted({float(row["architecture_weight"]) for row in rows})
    balances = sorted({float(row["min_weight_balance"]) for row in rows})
    values = {
        (float(row["architecture_weight"]), float(row["min_weight_balance"])): float(row["v2_reduction_vs_generic"])
        for row in rows
    }
    low, high = min(values.values()), max(values.values())

    width, height = 980, 620
    left, top = 230, 120
    cell_w, cell_h = 170, 82
    body: list[str] = []
    body.append(svg_text(width / 2, 38, "Parameter Sweep: Reduction vs Generic", 24, weight="700"))
    body.append(svg_text(width / 2, 64, "Each cell reports crossing connection proxy reduction", 13, color=MUTED))

    for col, balance in enumerate(balances):
        x = left + col * cell_w + (cell_w - 10) / 2
        body.append(svg_text(x, top - 24, f"min weight balance {balance:.2f}", 12, weight="700"))

    for row_idx, arch in enumerate(arch_weights):
        y = top + row_idx * cell_h
        body.append(svg_text(left - 18, y + cell_h / 2, f"architecture weight {arch:.1f}", 12, "end", weight="700"))
        for col, balance in enumerate(balances):
            x = left + col * cell_w
            value = values.get((arch, balance))
            fill = heat_color(value, low, high) if value is not None else LIGHT_BG
            stroke = "#111827" if arch == 0.4 and balance == 0.95 else "white"
            sw = 2.2 if arch == 0.4 and balance == 0.95 else 1.0
            body.append(rect(x, y, cell_w - 10, cell_h - 10, fill, stroke, sw))
            label = f"{value * 100:.1f}%" if value is not None else "N/A"
            body.append(svg_text(x + (cell_w - 10) / 2, y + 36, label, 16, weight="700"))
            if arch == 0.4 and balance == 0.95:
                body.append(svg_text(x + (cell_w - 10) / 2, y + 57, "default", 10, color=MUTED))

    body.append(svg_text(width / 2, height - 50, f"Observed range: {low*100:.1f}% to {high*100:.1f}% reduction", 12, color=MUTED))
    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_pareto(path: Path, rows: list[dict[str, str]]) -> None:
    width, height = 1040, 680
    left, right, top, bottom = 110, 70, 95, 105
    plot_w = width - left - right
    plot_h = height - top - bottom
    x_values = [float(row["v2_weight_balance_ratio"]) for row in rows]
    y_values = [float(row["v2_reduction_vs_generic"]) for row in rows]
    x_min, x_max = 0.89, 1.00
    y_min, y_max = 0.35, 0.70

    def px(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def py(value: float) -> float:
        return top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    body: list[str] = []
    body.append(svg_text(width / 2, 38, "Sweep Tradeoff: Balance vs Crossing Reduction", 24, weight="700"))
    body.append(svg_text(width / 2, 64, "Upper-right is better; labels show selected operating points", 13, color=MUTED))

    for i in range(6):
        x = left + plot_w * i / 5
        value = x_min + (x_max - x_min) * i / 5
        body.append(line(x, top, x, top + plot_h))
        body.append(svg_text(x, top + plot_h + 28, f"{value:.2f}", 11, color=MUTED))
    for i in range(6):
        y = top + plot_h * i / 5
        value = y_max - (y_max - y_min) * i / 5
        body.append(line(left, y, left + plot_w, y))
        body.append(svg_text(left - 12, y + 4, f"{value*100:.0f}%", 11, "end", color=MUTED))
    body.append(line(left, top, left, top + plot_h, AXIS, 1.2))
    body.append(line(left, top + plot_h, left + plot_w, top + plot_h, AXIS, 1.2))

    color_by_balance = {0.90: "#59a14f", 0.95: "#f28e2b", 0.98: "#4e79a7"}
    for row in rows:
        x = px(float(row["v2_weight_balance_ratio"]))
        y = py(float(row["v2_reduction_vs_generic"]))
        arch = float(row["architecture_weight"])
        wb = round(float(row["min_weight_balance"]), 2)
        radius = 5.0 + arch * 5.0
        body.append(circle(x, y, radius, color_by_balance.get(wb, "#777777")))

    # Selected labels only: best reduction, default, strict-best.
    best = max(rows, key=lambda row: float(row["v2_reduction_vs_generic"]))
    default = next((row for row in rows if row["run_name"] == "arch0p4_wb0p95"), rows[0])
    strict = max((row for row in rows if abs(float(row["min_weight_balance"]) - 0.98) < 1e-9), key=lambda row: float(row["v2_reduction_vs_generic"]))
    for row, label, dx, dy in [
        (best, "best reduction", 16, -18),
        (default, "default", 16, 18),
        (strict, "strict balance best", -16, -16),
    ]:
        x = px(float(row["v2_weight_balance_ratio"]))
        y = py(float(row["v2_reduction_vs_generic"]))
        body.append(line(x, y, x + dx, y + dy, "#94a3b8", 1.0))
        anchor = "start" if dx > 0 else "end"
        body.append(svg_text(x + dx, y + dy, f"{label}: {row['run_name']}", 11, anchor, weight="700"))

    # Legends.
    legend_x, legend_y = left + 20, height - 46
    for idx, wb in enumerate([0.90, 0.95, 0.98]):
        x = legend_x + idx * 125
        body.append(circle(x, legend_y - 4, 6, color_by_balance[wb]))
        body.append(svg_text(x + 14, legend_y, f"min WB {wb:.2f}", 11, "start"))
    body.append(svg_text(width / 2, height - 22, "v2 proxy-weight balance ratio", 13))
    body.append(
        f'<text x="28" y="{height/2:.1f}" transform="rotate(-90 28 {height/2:.1f})" '
        f'text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="13" fill="{TEXT}">'
        "Reduction vs generic crossing proxy</text>"
    )

    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_summary_table(path: Path, rows: list[dict[str, str]]) -> None:
    default = next((row for row in rows if row["run_name"] == "arch0p4_wb0p95"), rows[0])
    best = max(rows, key=lambda row: float(row["v2_reduction_vs_generic"]))
    strict = max((row for row in rows if abs(float(row["min_weight_balance"]) - 0.98) < 1e-9), key=lambda row: float(row["v2_reduction_vs_generic"]))
    selected = [("Best reduction", best), ("Default", default), ("Strict balance best", strict)]

    lines = [
        "# Summary Figure Summary",
        "",
        "| Setting | Run | Reduction vs Generic | Reduction vs V1 | Weight Balance | Instance Balance | Crossing Proxy |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, row in selected:
        lines.append(
            "| "
            f"{label} | `{row['run_name']}` | "
            f"{float(row['v2_reduction_vs_generic'])*100:.1f}% | "
            f"{float(row['v2_reduction_vs_v1'])*100:.1f}% | "
            f"{float(row['v2_weight_balance_ratio']):.3f} | "
            f"{float(row['v2_instance_balance_ratio']):.3f} | "
            f"{row['v2_crossing_connections_proxy']} |"
        )
    lines.append("")
    lines.append("The default setting is used as the conservative main result because it maintains proxy-weight balance above 0.95 while substantially reducing crossing proxy.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition-dir", type=Path, default=Path("results") / "partition_v2")
    parser.add_argument("--sweep-dir", type=Path, default=Path("results") / "partition_v2_sweep")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "figures_report")
    args = parser.parse_args()

    partition_rows = read_csv(args.partition_dir / "partition_comparison.csv")
    sweep_rows = read_csv(args.sweep_dir / "sweep_summary.csv")
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    write_main_results(output_dir / "report_main_partition_results.svg", partition_rows)
    write_sweep_heatmap(output_dir / "report_sweep_reduction_heatmap.svg", sweep_rows)
    write_pareto(output_dir / "report_sweep_tradeoff.svg", sweep_rows)
    write_summary_table(output_dir / "report_summary_table.md", sweep_rows)

    for output in sorted(output_dir.glob("report_*")):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
