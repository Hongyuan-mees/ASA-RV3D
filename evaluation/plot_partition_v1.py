#!/usr/bin/env python3
"""Create dependency-free SVG plots for partition v1 results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


PALETTE = {
    "generic_balance": "#4C78A8",
    "architecture_aware": "#F58518",
    "tier0": "#4C78A8",
    "tier1": "#F58518",
    "grid": "#D9DDE7",
    "text": "#1F2937",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def svg_text(x: float, y: float, text: str, size: int = 13, anchor: str = "middle", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{PALETTE["text"]}">{escape(text)}</text>'
    )


def escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_doc(width: int, height: int, body: Iterable[str]) -> str:
    joined = "\n".join(body)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="100%" height="100%" fill="white"/>\n'
        f"{joined}\n"
        f"</svg>\n"
    )


def write_grouped_bar(path: Path, title: str, rows: list[dict[str, str]], metrics: list[tuple[str, str]]) -> None:
    width, height = 920, 520
    left, right, top, bottom = 95, 40, 80, 110
    plot_w = width - left - right
    plot_h = height - top - bottom
    max_value = max(float(row[key]) for row in rows for key, _label in metrics)
    y_max = max_value * 1.15

    body = [svg_text(width / 2, 36, title, size=22, weight="700")]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        value = y_max * i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{PALETTE["grid"]}"/>')
        body.append(svg_text(left - 12, y + 4, f"{value:.0f}", size=11, anchor="end"))

    group_w = plot_w / len(metrics)
    bar_w = min(80, group_w / 4)
    for m_idx, (metric, label) in enumerate(metrics):
        cx = left + group_w * (m_idx + 0.5)
        for r_idx, row in enumerate(rows):
            strategy = row["strategy"]
            value = float(row[metric])
            h = plot_h * value / y_max
            x = cx + (r_idx - 0.5) * (bar_w + 10) - bar_w / 2
            y = top + plot_h - h
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" fill="{PALETTE[strategy]}"/>')
            body.append(svg_text(x + bar_w / 2, y - 8, f"{value:.0f}", size=11))
        body.append(svg_text(cx, height - 62, label, size=13))

    legend_y = height - 28
    legend_x = width / 2 - 190
    for idx, strategy in enumerate(["generic_balance", "architecture_aware"]):
        x = legend_x + idx * 230
        body.append(f'<rect x="{x:.1f}" y="{legend_y-12}" width="14" height="14" fill="{PALETTE[strategy]}"/>')
        body.append(svg_text(x + 22, legend_y, strategy, size=12, anchor="start"))

    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_balance_plot(path: Path, rows: list[dict[str, str]]) -> None:
    width, height = 920, 430
    left, right, top, bottom = 110, 40, 80, 90
    plot_w = width - left - right
    plot_h = height - top - bottom
    metrics = [
        ("instance_balance_ratio", "Instance balance"),
        ("weight_balance_ratio", "Proxy-weight balance"),
    ]

    body = [svg_text(width / 2, 36, "Tier Balance Ratios", size=22, weight="700")]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        value = i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{PALETTE["grid"]}"/>')
        body.append(svg_text(left - 12, y + 4, f"{value:.1f}", size=11, anchor="end"))

    group_w = plot_w / len(metrics)
    bar_w = 82
    for m_idx, (metric, label) in enumerate(metrics):
        cx = left + group_w * (m_idx + 0.5)
        for r_idx, row in enumerate(rows):
            strategy = row["strategy"]
            value = float(row[metric])
            h = plot_h * value
            x = cx + (r_idx - 0.5) * (bar_w + 16) - bar_w / 2
            y = top + plot_h - h
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" fill="{PALETTE[strategy]}"/>')
            body.append(svg_text(x + bar_w / 2, y - 8, f"{value:.3f}", size=11))
        body.append(svg_text(cx, height - 48, label, size=13))

    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_class_distribution(path: Path, rows: list[dict[str, str]]) -> None:
    width, height = 980, 760
    left, right, top, row_h = 230, 70, 72, 34
    bar_w = width - left - right
    arch_rows = [row for row in rows if row["strategy"] == "architecture_aware"]
    arch_rows.sort(key=lambda row: int(row["total_count"]), reverse=True)

    body = [svg_text(width / 2, 34, "Architecture-Aware Tier Distribution By Class", size=22, weight="700")]
    body.append(svg_text(left, 58, "tier0", size=12, anchor="start"))
    body.append(svg_text(left + 70, 58, "tier1", size=12, anchor="start"))
    body.append(f'<rect x="{left-18}" y="47" width="12" height="12" fill="{PALETTE["tier0"]}"/>')
    body.append(f'<rect x="{left+52}" y="47" width="12" height="12" fill="{PALETTE["tier1"]}"/>')

    for idx, row in enumerate(arch_rows):
        y = top + idx * row_h
        tier0 = int(row["tier0_count"])
        tier1 = int(row["tier1_count"])
        total = max(1, int(row["total_count"]))
        w0 = bar_w * tier0 / total
        w1 = bar_w * tier1 / total
        body.append(svg_text(left - 12, y + 18, row["architecture_class"], size=12, anchor="end"))
        body.append(f'<rect x="{left}" y="{y}" width="{w0:.1f}" height="22" fill="{PALETTE["tier0"]}"/>')
        body.append(f'<rect x="{left + w0:.1f}" y="{y}" width="{w1:.1f}" height="22" fill="{PALETTE["tier1"]}"/>')
        body.append(svg_text(left + bar_w + 12, y + 16, f'{total}', size=11, anchor="start"))

    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition-dir", type=Path, default=Path("results") / "partition_v1")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "figures")
    args = parser.parse_args()

    partition_dir = args.partition_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison = read_csv(partition_dir / "partition_comparison.csv")
    distribution = read_csv(partition_dir / "class_tier_distribution.csv")

    write_grouped_bar(
        output_dir / "partition_v1_crossing_metrics.svg",
        "Partition V1 Crossing Metrics",
        comparison,
        [("crossing_nets", "Crossing nets"), ("crossing_connections_proxy", "Crossing connection proxy")],
    )
    write_balance_plot(output_dir / "partition_v1_balance.svg", comparison)
    write_class_distribution(output_dir / "partition_v1_class_distribution.svg", distribution)

    for output in sorted(output_dir.glob("partition_v1_*.svg")):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
