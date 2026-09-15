#!/usr/bin/env python3
"""Create clean SVG figures for two RISC-V benchmark and ablation summaries."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


TEXT = "#1f2937"
MUTED = "#64748b"
GRID = "#d8dee9"
AXIS = "#334155"
GENERIC = "#4e79a7"
V1 = "#f28e2b"
V2 = "#59a14f"
NO_ARCH = "#8cd17d"
NO_BALANCE = "#b07aa1"

METHOD_LABELS = {
    "generic_balance": "Generic",
    "architecture_aware_v1": "Arch-aware v1",
    "architecture_score_v2": "Score v2",
}

METHOD_COLORS = {
    "generic_balance": GENERIC,
    "architecture_aware_v1": V1,
    "architecture_score_v2": V2,
}


def esc(x):
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, value, size=12, anchor="middle", weight="400", color=TEXT):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{esc(value)}</text>'
    )


def rect(x, y, w, h, fill, stroke="none", sw=1):
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'


def line(x1, y1, x2, y2, color=GRID, sw=1):
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{sw}"/>'


def svg(width, height, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plot_benchmark(path, rows):
    width, height = 1280, 720
    body = []
    body.append(text(width / 2, 40, "Two RISC-V Benchmark Partition Results", 24, weight="700"))
    body.append(text(width / 2, 66, "Lower crossing proxy is better; higher balance is better", 13, color=MUTED))

    designs = ["ibex", "riscv32i"]
    methods = ["generic_balance", "architecture_aware_v1", "architecture_score_v2"]
    by_key = {(r["design"], r["strategy"]): r for r in rows}

    # Left panel: crossing proxy.
    left, top, plot_w, plot_h = 90, 130, 520, 390
    body.append(text(left + plot_w / 2, 108, "(a) Crossing connection proxy", 16, weight="700"))
    max_cross = max(int(r["crossing_connections_proxy"]) for r in rows) * 1.15
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        v = max_cross * i / 5
        body.append(line(left, y, left + plot_w, y))
        body.append(text(left - 12, y + 4, f"{v:.0f}", 11, "end", color=MUTED))
    body.append(line(left, top, left, top + plot_h, AXIS, 1.2))
    body.append(line(left, top + plot_h, left + plot_w, top + plot_h, AXIS, 1.2))

    group_w = plot_w / len(designs)
    bar_w = 44
    for di, design in enumerate(designs):
        cx = left + group_w * (di + 0.5)
        for mi, method in enumerate(methods):
            row = by_key[(design, method)]
            val = int(row["crossing_connections_proxy"])
            h = plot_h * val / max_cross
            x = cx + (mi - 1) * (bar_w + 14) - bar_w / 2
            y = top + plot_h - h
            body.append(rect(x, y, bar_w, h, METHOD_COLORS[method]))
            body.append(text(x + bar_w / 2, y - 8, val, 11, weight="700"))
            if method == "architecture_score_v2":
                body.append(text(x + bar_w / 2, top + plot_h + 48, f"-{float(row['reduction_vs_generic']) * 100:.1f}%", 12, weight="700", color="#2f855a"))
        body.append(text(cx, top + plot_h + 28, design, 13, weight="700"))

    # Right panel: v2 balance.
    rleft, rtop, rplot_w, rplot_h = 750, 130, 410, 390
    body.append(text(rleft + rplot_w / 2, 108, "(b) Score v2 balance", 16, weight="700"))
    for i in range(6):
        y = rtop + rplot_h - rplot_h * i / 5
        v = i / 5
        body.append(line(rleft, y, rleft + rplot_w, y))
        body.append(text(rleft - 12, y + 4, f"{v:.1f}", 11, "end", color=MUTED))
    body.append(line(rleft, rtop, rleft, rtop + rplot_h, AXIS, 1.2))
    body.append(line(rleft, rtop + rplot_h, rleft + rplot_w, rtop + rplot_h, AXIS, 1.2))

    metrics = [("instance_balance_ratio", "Instance"), ("weight_balance_ratio", "Weight")]
    group_w2 = rplot_w / len(designs)
    small_w = 42
    for di, design in enumerate(designs):
        cx = rleft + group_w2 * (di + 0.5)
        row = by_key[(design, "architecture_score_v2")]
        for mi, (metric, label) in enumerate(metrics):
            val = float(row[metric])
            h = rplot_h * val
            x = cx + (mi - 0.5) * (small_w + 18) - small_w / 2
            y = rtop + rplot_h - h
            fill = "#76b7b2" if metric == "instance_balance_ratio" else "#59a14f"
            body.append(rect(x, y, small_w, h, fill))
            body.append(text(x + small_w / 2, y - 8, f"{val:.3f}", 10))
            body.append(text(x + small_w / 2, rtop + rplot_h + 48, label, 11))
        body.append(text(cx, rtop + rplot_h + 28, design, 13, weight="700"))

    legend_y = height - 54
    legend_x = 330
    for i, method in enumerate(methods):
        x = legend_x + i * 190
        body.append(rect(x, legend_y - 13, 14, 14, METHOD_COLORS[method]))
        body.append(text(x + 22, legend_y, METHOD_LABELS[method], 12, "start"))

    path.write_text(svg(width, height, body), encoding="utf-8")


def plot_ablation(path, rows):
    width, height = 1080, 620
    body = []
    body.append(text(width / 2, 40, "riscv32i Partition V2 Ablation", 24, weight="700"))
    body.append(text(width / 2, 66, "Architecture penalty preserves semantic separation; balance repair improves robustness", 13, color=MUTED))

    labels = [
        ("riscv32i_full_v2", "Full v2", V2),
        ("riscv32i_no_arch_penalty", "No arch penalty", NO_ARCH),
        ("riscv32i_no_balance_penalty", "No balance penalty", NO_BALANCE),
    ]
    by_case = {r["case"]: r for r in rows}

    left, top, plot_w, plot_h = 100, 130, 420, 340
    body.append(text(left + plot_w / 2, 108, "(a) Crossing proxy", 16, weight="700"))
    max_cross = max(int(r["crossing_connections_proxy"]) for r in rows) * 1.2
    for i in range(5):
        y = top + plot_h - plot_h * i / 4
        body.append(line(left, y, left + plot_w, y))
        body.append(text(left - 12, y + 4, f"{max_cross * i / 4:.0f}", 11, "end", color=MUTED))
    body.append(line(left, top, left, top + plot_h, AXIS, 1.2))
    body.append(line(left, top + plot_h, left + plot_w, top + plot_h, AXIS, 1.2))

    bar_w = 62
    for i, (case, label, color) in enumerate(labels):
        row = by_case[case]
        val = int(row["crossing_connections_proxy"])
        h = plot_h * val / max_cross
        x = left + 85 + i * 125
        y = top + plot_h - h
        body.append(rect(x, y, bar_w, h, color))
        body.append(text(x + bar_w / 2, y - 8, val, 12, weight="700"))
        body.append(text(x + bar_w / 2, top + plot_h + 28, label, 11))

    rleft, rtop, rplot_w, rplot_h = 650, 130, 330, 340
    body.append(text(rleft + rplot_w / 2, 108, "(b) Balance ratios", 16, weight="700"))
    for i in range(6):
        y = rtop + rplot_h - rplot_h * i / 5
        body.append(line(rleft, y, rleft + rplot_w, y))
        body.append(text(rleft - 12, y + 4, f"{i/5:.1f}", 11, "end", color=MUTED))
    body.append(line(rleft, rtop, rleft, rtop + rplot_h, AXIS, 1.2))
    body.append(line(rleft, rtop + rplot_h, rleft + rplot_w, rtop + rplot_h, AXIS, 1.2))

    for i, (case, label, color) in enumerate(labels):
        row = by_case[case]
        x0 = rleft + 55 + i * 100
        for j, metric in enumerate(["instance_balance_ratio", "weight_balance_ratio"]):
            val = float(row[metric])
            h = rplot_h * val
            x = x0 + j * 34
            y = rtop + rplot_h - h
            body.append(rect(x, y, 28, h, color if j == 0 else "#76b7b2"))
            body.append(text(x + 14, y - 8, f"{val:.3f}", 9))
        body.append(text(x0 + 16, rtop + rplot_h + 28, label, 10))

    body.append(text(width / 2, height - 42, "Full v2 is selected because it keeps low crossing while preserving datapath/control tier semantics.", 13, color=MUTED))
    path.write_text(svg(width, height, body), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark-summary", type=Path, default=Path("results/benchmark_summary/two_riscv_benchmark_partition_summary.csv"))
    ap.add_argument("--ablation-summary", type=Path, default=Path("results/ablation_summary/riscv32i_v2_ablation_summary.csv"))
    ap.add_argument("--output-dir", type=Path, default=Path("results/figures/summary"))
    args = ap.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    plot_benchmark(args.output_dir / "two_riscv_benchmark_partition_summary.svg", read_csv(args.benchmark_summary))
    plot_ablation(args.output_dir / "riscv32i_v2_ablation_summary.svg", read_csv(args.ablation_summary))

    print(args.output_dir / "two_riscv_benchmark_partition_summary.svg")
    print(args.output_dir / "riscv32i_v2_ablation_summary.svg")


if __name__ == "__main__":
    main()
