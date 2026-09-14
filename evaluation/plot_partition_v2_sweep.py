#!/usr/bin/env python3
"""Create dependency-free SVG plots for the partition v2 parameter sweep."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


TEXT = "#1F2937"
GRID = "#D9DDE7"
GREEN = "#54A24B"
ORANGE = "#F58518"
BLUE = "#4C78A8"


def escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def svg_text(x: float, y: float, text: object, size: int = 12, anchor: str = "middle", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{TEXT}">{escape(text)}</text>'
    )


def svg_doc(width: int, height: int, body: Iterable[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="100%" height="100%" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def color_scale(value: float, low: float, high: float) -> str:
    """Return a blue-to-green color for a value in [low, high]."""
    if high <= low:
        ratio = 1.0
    else:
        ratio = max(0.0, min(1.0, (value - low) / (high - low)))
    r0, g0, b0 = 198, 219, 239
    r1, g1, b1 = 84, 162, 75
    r = round(r0 + (r1 - r0) * ratio)
    g = round(g0 + (g1 - g0) * ratio)
    b = round(b0 + (b1 - b0) * ratio)
    return f"#{r:02x}{g:02x}{b:02x}"


def write_reduction_heatmap(path: Path, rows: list[dict[str, str]], metric: str, title: str) -> None:
    arch_weights = sorted({float(row["architecture_weight"]) for row in rows})
    balances = sorted({float(row["min_weight_balance"]) for row in rows})
    values = {
        (float(row["architecture_weight"]), float(row["min_weight_balance"])): float(row[metric])
        for row in rows
    }
    min_value = min(values.values())
    max_value = max(values.values())

    width, height = 880, 520
    left, top = 150, 90
    cell_w, cell_h = 145, 78
    body = [svg_text(width / 2, 36, title, size=22, weight="700")]
    body.append(svg_text(width / 2, 64, "Cell value = reduction ratio; darker green is better", size=12))

    for col, balance in enumerate(balances):
        x = left + col * cell_w + cell_w / 2
        body.append(svg_text(x, top - 26, f"min WB {balance:.2f}", size=12, weight="700"))

    for row_idx, arch_weight in enumerate(arch_weights):
        y = top + row_idx * cell_h
        body.append(svg_text(left - 18, y + cell_h / 2 + 4, f"arch {arch_weight:.1f}", size=12, anchor="end", weight="700"))
        for col, balance in enumerate(balances):
            x = left + col * cell_w
            value = values.get((arch_weight, balance))
            color = color_scale(value, min_value, max_value) if value is not None else "#F3F4F6"
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w-8}" height="{cell_h-8}" fill="{color}" stroke="white"/>')
            label = f"{value*100:.1f}%" if value is not None else "N/A"
            body.append(svg_text(x + (cell_w - 8) / 2, y + 34, label, size=15, weight="700"))

    body.append(svg_text(width / 2, height - 42, f"Range: {min_value*100:.1f}% to {max_value*100:.1f}%", size=12))
    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_tradeoff_plot(path: Path, rows: list[dict[str, str]]) -> None:
    width, height = 920, 560
    left, right, top, bottom = 90, 55, 75, 90
    plot_w = width - left - right
    plot_h = height - top - bottom

    x_values = [float(row["v2_weight_balance_ratio"]) for row in rows]
    y_values = [float(row["v2_reduction_vs_generic"]) for row in rows]
    x_min, x_max = min(x_values) - 0.01, max(x_values) + 0.01
    y_min, y_max = min(y_values) - 0.03, max(y_values) + 0.03

    def px(value: float) -> float:
        return left + (value - x_min) / (x_max - x_min) * plot_w

    def py(value: float) -> float:
        return top + plot_h - (value - y_min) / (y_max - y_min) * plot_h

    body = [svg_text(width / 2, 36, "Partition V2 Sweep Tradeoff", size=22, weight="700")]
    body.append(svg_text(width / 2, 58, "Higher is better on both axes", size=12))

    for i in range(6):
        y = top + plot_h * i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}"/>')
        value = y_max - (y_max - y_min) * i / 5
        body.append(svg_text(left - 12, y + 4, f"{value*100:.0f}%", size=11, anchor="end"))
    for i in range(6):
        x = left + plot_w * i / 5
        body.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="{GRID}"/>')
        value = x_min + (x_max - x_min) * i / 5
        body.append(svg_text(x, height - bottom + 24, f"{value:.2f}", size=11))

    for row in rows:
        x = px(float(row["v2_weight_balance_ratio"]))
        y = py(float(row["v2_reduction_vs_generic"]))
        arch = float(row["architecture_weight"])
        radius = 5 + arch * 5
        balance = float(row["min_weight_balance"])
        color = GREEN if balance <= 0.90 else ORANGE if balance <= 0.95 else BLUE
        body.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" opacity="0.82"/>')
        body.append(svg_text(x + 8, y - 8, row["run_name"], size=9, anchor="start"))

    body.append(svg_text(width / 2, height - 28, "v2 proxy-weight balance ratio", size=13))
    body.append(
        f'<text x="24" y="{height/2:.1f}" transform="rotate(-90 24 {height/2:.1f})" '
        f'text-anchor="middle" font-family="Arial, sans-serif" font-size="13" fill="{TEXT}">'
        "Reduction vs generic crossing proxy</text>"
    )
    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_best_table(path: Path, rows: list[dict[str, str]]) -> None:
    sorted_rows = sorted(rows, key=lambda row: float(row["v2_reduction_vs_generic"]), reverse=True)
    top = sorted_rows[:5]
    lines = [
        "# Partition V2 Sweep Summary",
        "",
        "| Rank | Run | Reduction vs Generic | Reduction vs V1 | Weight Balance | Instance Balance | Crossing Proxy |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(top, start=1):
        lines.append(
            "| "
            f"{idx} | `{row['run_name']}` | "
            f"{float(row['v2_reduction_vs_generic'])*100:.1f}% | "
            f"{float(row['v2_reduction_vs_v1'])*100:.1f}% | "
            f"{float(row['v2_weight_balance_ratio']):.3f} | "
            f"{float(row['v2_instance_balance_ratio']):.3f} | "
            f"{row['v2_crossing_connections_proxy']} |"
        )
    lines.extend(
        [
            "",
            "Default run `arch0p4_wb0p95` is a conservative main setting: it keeps proxy-weight balance above 0.95 while still strongly reducing crossing proxy.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-dir", type=Path, default=Path("results") / "partition_v2_sweep")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "figures")
    args = parser.parse_args()

    sweep_dir = args.sweep_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = read_csv(sweep_dir / "sweep_summary.csv")

    write_reduction_heatmap(
        output_dir / "partition_v2_sweep_reduction_vs_generic.svg",
        rows,
        "v2_reduction_vs_generic",
        "V2 Sweep: Reduction vs Generic",
    )
    write_reduction_heatmap(
        output_dir / "partition_v2_sweep_reduction_vs_v1.svg",
        rows,
        "v2_reduction_vs_v1",
        "V2 Sweep: Reduction vs Architecture-Aware V1",
    )
    write_tradeoff_plot(output_dir / "partition_v2_sweep_tradeoff.svg", rows)
    write_best_table(sweep_dir / "sweep_report_table.md", rows)

    for output in sorted(output_dir.glob("partition_v2_sweep_*.svg")):
        print(output)
    print(sweep_dir / "sweep_report_table.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
