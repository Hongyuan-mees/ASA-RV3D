#!/usr/bin/env python3
"""Create dependency-free SVG plots for partition v2 results."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Iterable


PALETTE = {
    "generic_balance": "#4C78A8",
    "architecture_aware_v1": "#F58518",
    "architecture_score_v2": "#54A24B",
    "tier0": "#4C78A8",
    "tier1": "#F58518",
    "grid": "#D9DDE7",
    "text": "#1F2937",
}

STRATEGIES = ["generic_balance", "architecture_aware_v1", "architecture_score_v2"]


def escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def svg_text(x: float, y: float, text: str, size: int = 13, anchor: str = "middle", weight: str = "400") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" '
        f'fill="{PALETTE["text"]}">{escape(text)}</text>'
    )


def svg_doc(width: int, height: int, body: Iterable[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n'
        f'<rect width="100%" height="100%" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def ordered_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_strategy = {row["strategy"]: row for row in rows}
    return [by_strategy[strategy] for strategy in STRATEGIES if strategy in by_strategy]


def write_crossing_plot(path: Path, rows: list[dict[str, str]]) -> None:
    rows = ordered_rows(rows)
    width, height = 1080, 560
    left, right, top, bottom = 105, 45, 80, 130
    plot_w = width - left - right
    plot_h = height - top - bottom
    metrics = [("crossing_nets", "Crossing nets"), ("crossing_connections_proxy", "Crossing connection proxy")]
    max_value = max(float(row[key]) for row in rows for key, _label in metrics) * 1.15

    body = [svg_text(width / 2, 36, "Partition V2 Crossing Metrics", size=22, weight="700")]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        value = max_value * i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{PALETTE["grid"]}"/>')
        body.append(svg_text(left - 12, y + 4, f"{value:.0f}", size=11, anchor="end"))

    group_w = plot_w / len(metrics)
    bar_w = 62
    for m_idx, (metric, label) in enumerate(metrics):
        cx = left + group_w * (m_idx + 0.5)
        for r_idx, row in enumerate(rows):
            strategy = row["strategy"]
            value = float(row[metric])
            h = plot_h * value / max_value
            offset = (r_idx - (len(rows) - 1) / 2) * (bar_w + 10)
            x = cx + offset - bar_w / 2
            y = top + plot_h - h
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" fill="{PALETTE[strategy]}"/>')
            body.append(svg_text(x + bar_w / 2, y - 8, f"{value:.0f}", size=11))
        body.append(svg_text(cx, height - 78, label, size=13))

    write_legend(body, width, height - 34)
    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_balance_plot(path: Path, rows: list[dict[str, str]]) -> None:
    rows = ordered_rows(rows)
    width, height = 1080, 470
    left, right, top, bottom = 105, 45, 80, 110
    plot_w = width - left - right
    plot_h = height - top - bottom
    metrics = [("instance_balance_ratio", "Instance balance"), ("weight_balance_ratio", "Proxy-weight balance")]

    body = [svg_text(width / 2, 36, "Partition V2 Tier Balance Ratios", size=22, weight="700")]
    for i in range(6):
        y = top + plot_h - plot_h * i / 5
        value = i / 5
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{PALETTE["grid"]}"/>')
        body.append(svg_text(left - 12, y + 4, f"{value:.1f}", size=11, anchor="end"))

    group_w = plot_w / len(metrics)
    bar_w = 62
    for m_idx, (metric, label) in enumerate(metrics):
        cx = left + group_w * (m_idx + 0.5)
        for r_idx, row in enumerate(rows):
            strategy = row["strategy"]
            value = float(row[metric])
            h = plot_h * value
            offset = (r_idx - (len(rows) - 1) / 2) * (bar_w + 10)
            x = cx + offset - bar_w / 2
            y = top + plot_h - h
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w}" height="{h:.1f}" fill="{PALETTE[strategy]}"/>')
            body.append(svg_text(x + bar_w / 2, y - 8, f"{value:.3f}", size=11))
        body.append(svg_text(cx, height - 64, label, size=13))

    write_legend(body, width, height - 26)
    path.write_text(svg_doc(width, height, body), encoding="utf-8")


def write_class_distribution(path: Path, rows: list[dict[str, str]]) -> None:
    width, height = 1060, 760
    left, right, top, row_h = 240, 70, 78, 34
    bar_w = width - left - right
    selected = [row for row in rows if row["strategy"] == "architecture_score_v2"]
    selected.sort(key=lambda row: int(row["total_count"]), reverse=True)

    body = [svg_text(width / 2, 34, "Partition V2 Architecture Score Tier Distribution", size=22, weight="700")]
    body.append(f'<rect x="{left-18}" y="50" width="12" height="12" fill="{PALETTE["tier0"]}"/>')
    body.append(svg_text(left, 61, "tier0", size=12, anchor="start"))
    body.append(f'<rect x="{left+52}" y="50" width="12" height="12" fill="{PALETTE["tier1"]}"/>')
    body.append(svg_text(left + 70, 61, "tier1", size=12, anchor="start"))

    for idx, row in enumerate(selected):
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


def write_legend(body: list[str], width: int, y: float) -> None:
    x0 = width / 2 - 320
    for idx, strategy in enumerate(STRATEGIES):
        x = x0 + idx * 235
        body.append(f'<rect x="{x:.1f}" y="{y-12}" width="14" height="14" fill="{PALETTE[strategy]}"/>')
        body.append(svg_text(x + 22, y, strategy, size=12, anchor="start"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition-dir", type=Path, default=Path("results") / "partition_v2")
    parser.add_argument("--output-dir", type=Path, default=Path("results") / "figures")
    args = parser.parse_args()

    partition_dir = args.partition_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison = read_csv(partition_dir / "partition_comparison.csv")
    distribution = read_csv(partition_dir / "class_tier_distribution.csv")

    write_crossing_plot(output_dir / "partition_v2_crossing_metrics.svg", comparison)
    write_balance_plot(output_dir / "partition_v2_balance.svg", comparison)
    write_class_distribution(output_dir / "partition_v2_class_distribution.svg", distribution)

    for output in sorted(output_dir.glob("partition_v2_*.svg")):
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
