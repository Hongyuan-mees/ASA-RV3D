#!/usr/bin/env python3
"""Plot multi-metric partition summaries for the RISC-V benchmarks."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


TEXT = "#1f2937"
MUTED = "#64748b"
GRID = "#d8dee9"
AXIS = "#334155"
COLORS = {
    "generic": "#4e79a7",
    "v1": "#f28e2b",
    "full_v2": "#59a14f",
    "connectivity_only": "#b07aa1",
}
LABELS = {
    "generic": "Generic",
    "v1": "Arch v1",
    "full_v2": "ASA-RV3D",
    "connectivity_only": "Conn-only",
}


def esc(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def normalized_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    generic_crossing = next(float(row["crossing_connections_proxy"]) for row in rows if row["case"] == "generic")
    output = []
    for row in rows:
        crossing = float(row["crossing_connections_proxy"])
        crossing_reduction = (generic_crossing - crossing) / generic_crossing if generic_crossing else 0.0
        output.append(
            {
                "case": row["case"],
                "crossing_reduction": crossing_reduction,
                "instance_balance": float(row["instance_balance_ratio"]),
                "architecture_separation": float(row["architecture_separation_score"]),
            }
        )
    return output


def draw_panel(body, title, rows, x0, y0, width, height):
    cases = ["generic", "v1", "full_v2", "connectivity_only"]
    metrics = [
        ("crossing_reduction", "Crossing reduction"),
        ("instance_balance", "Instance balance"),
        ("architecture_separation", "Arch separation"),
    ]

    body.append(text(x0 + width / 2, y0 - 24, title, 17, weight="700"))

    plot_left = x0 + 62
    plot_top = y0 + 20
    plot_w = width - 95
    plot_h = height - 90

    for i in range(6):
        y = plot_top + plot_h - plot_h * i / 5
        body.append(line(plot_left, y, plot_left + plot_w, y))
        body.append(text(plot_left - 10, y + 4, f"{i/5:.1f}", 10, "end", color=MUTED))
    body.append(line(plot_left, plot_top, plot_left, plot_top + plot_h, AXIS, 1.2))
    body.append(line(plot_left, plot_top + plot_h, plot_left + plot_w, plot_top + plot_h, AXIS, 1.2))

    by_case = {row["case"]: row for row in rows}
    group_w = plot_w / len(metrics)
    bar_w = 24

    for mi, (metric, label) in enumerate(metrics):
        cx = plot_left + group_w * (mi + 0.5)
        for ci, case in enumerate(cases):
            row = by_case.get(case)
            if not row:
                continue
            value = float(row[metric])
            h = plot_h * max(0.0, min(1.0, value))
            x = cx + (ci - 1.5) * (bar_w + 7) - bar_w / 2
            y = plot_top + plot_h - h
            body.append(rect(x, y, bar_w, h, COLORS[case]))
            body.append(text(x + bar_w / 2, y - 6, f"{value:.2f}", 8, weight="700"))
        body.append(text(cx, plot_top + plot_h + 30, label, 11))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ibex", type=Path, default=Path("results/benchmark_summary/ibex_multi_metric_summary.csv"))
    parser.add_argument("--riscv32i", type=Path, default=Path("results/benchmark_summary/riscv32i_multi_metric_summary.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/figures/summary/two_riscv_multi_metric_summary.svg"))
    args = parser.parse_args()

    ibex = normalized_rows(read_csv(args.ibex))
    riscv32i = normalized_rows(read_csv(args.riscv32i))

    width, height = 1380, 670
    body = []
    body.append(text(width / 2, 40, "Multi-Metric Partition Evaluation", 25, weight="700"))
    body.append(text(width / 2, 66, "Higher is better for all normalized metrics", 13, color=MUTED))

    draw_panel(body, "Ibex", ibex, 55, 125, 610, 440)
    draw_panel(body, "riscv32i", riscv32i, 715, 125, 610, 440)

    legend_y = height - 45
    legend_x = width / 2 - 330
    for idx, case in enumerate(["generic", "v1", "full_v2", "connectivity_only"]):
        x = legend_x + idx * 180
        body.append(rect(x, legend_y - 13, 14, 14, COLORS[case]))
        body.append(text(x + 22, legend_y, LABELS[case], 12, "start"))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg(width, height, body), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
