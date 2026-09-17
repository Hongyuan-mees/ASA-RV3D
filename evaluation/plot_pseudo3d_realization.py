#!/usr/bin/env python3
"""Plot pseudo-3D timing-risk vertical proxy reduction for ASA-RV3D."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


TEXT = "#111827"
MUTED = "#475569"
GRID = "#e5e7eb"
AXIS = "#475569"
BAR = "#2563eb"
BAR_ALT = "#f97316"
BAR_THIRD = "#10b981"

SCENARIO_LABELS = {
    "control_datapath_split": "Control/datapath",
    "memory_near_logic": "Memory-near-logic",
    "state_and_clock_protected": "State/clock",
}

DESIGN_LABELS = {
    "riscv32i": "riscv32i",
    "ibex": "Ibex",
    "picorv32": "PicoRV32",
    "scr1_core_tuned": "SCR1 tuned",
}

COLORS = {
    "control_datapath_split": BAR,
    "memory_near_logic": BAR_ALT,
    "state_and_clock_protected": BAR_THIRD,
}


def esc(value: object) -> str:
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x: float, y: float, value: object, size: int = 12, anchor: str = "middle", weight: str = "400", color: str = TEXT) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
        f'font-weight="{weight}" fill="{color}">{esc(value)}</text>'
    )


def rect(x: float, y: float, w: float, h: float, fill: str, stroke: str = "none", sw: float = 1.0) -> str:
    return f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{sw:.1f}"/>'


def line(x1: float, y1: float, x2: float, y2: float, color: str = GRID, sw: float = 1.0) -> str:
    return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="{sw:.1f}"/>'


def svg(width: int, height: int, body: list[str]) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        '<rect width="100%" height="100%" fill="white"/>\n'
        + "\n".join(body)
        + "\n</svg>\n"
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_rows(path: Path) -> list[dict[str, object]]:
    rows = []
    for row in read_csv(path):
        if row.get("case") != "asa_rv3d":
            continue
        rows.append(
            {
                "design": row["design"],
                "scenario": row["scenario"],
                "reduction": float(row["timing_weighted_reduction_vs_tritonpart"]),
                "vertical_fraction": float(row["vertical_connection_fraction"]),
                "timing_proxy": float(row["timing_weighted_vertical_proxy"]),
            }
        )
    order = {name: idx for idx, name in enumerate(DESIGN_LABELS)}
    scenario_order = {name: idx for idx, name in enumerate(SCENARIO_LABELS)}
    rows.sort(key=lambda r: (order.get(str(r["design"]), 99), scenario_order.get(str(r["scenario"]), 99)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("results/benchmark_summary/pseudo3d_realization_summary.csv"))
    parser.add_argument("--output", type=Path, default=Path("results/figures/final/pseudo3d_timing_vertical_proxy_reduction.svg"))
    args = parser.parse_args()

    rows = load_rows(args.input)
    if not rows:
        raise RuntimeError(f"No ASA-RV3D rows found in {args.input}")

    reductions = [float(row["reduction"]) for row in rows]
    max_value = max(0.40, max(reductions) * 1.12)
    mean_value = sum(reductions) / len(reductions)

    width, height = 1180, 720
    left, right = 120, 50
    top, bottom = 145, 110
    plot_w = width - left - right
    plot_h = height - top - bottom
    body: list[str] = []

    body.append(text(width / 2, 42, "Pseudo-3D Timing-Risk Vertical Proxy Reduction", 25, weight="700"))
    body.append(text(width / 2, 70, "Higher is better. ASA-RV3D is compared against TritonPart for each 2-tier scenario.", 13, color=MUTED))
    body.append(text(width / 2, 100, f"12 cases | min {min(reductions)*100:.1f}% | mean {mean_value*100:.1f}% | max {max(reductions)*100:.1f}%", 14, weight="700", color=TEXT))

    for i in range(6):
        value = max_value * i / 5
        x = left + plot_w * i / 5
        body.append(line(x, top, x, top + plot_h))
        body.append(text(x, top + plot_h + 28, f"{value*100:.0f}%", 11, color=MUTED))
    body.append(line(left, top, left, top + plot_h, AXIS, 1.2))
    body.append(line(left, top + plot_h, left + plot_w, top + plot_h, AXIS, 1.2))

    design_order = list(DESIGN_LABELS)
    scenario_order = list(SCENARIO_LABELS)
    by_design = {design: [row for row in rows if row["design"] == design] for design in design_order}

    group_h = plot_h / len(design_order)
    bar_h = 22
    for di, design in enumerate(design_order):
        group_y = top + di * group_h
        body.append(text(left - 18, group_y + group_h / 2 + 5, DESIGN_LABELS[design], 15, "end", "700"))
        for si, scenario in enumerate(scenario_order):
            row = next((r for r in by_design.get(design, []) if r["scenario"] == scenario), None)
            if not row:
                continue
            value = float(row["reduction"])
            bar_w = plot_w * value / max_value
            y = group_y + group_h / 2 - 39 + si * 29
            body.append(rect(left, y, bar_w, bar_h, COLORS[scenario]))
            body.append(text(left + bar_w + 8, y + 16, f"{value*100:.1f}%", 11, "start", "700"))

    legend_y = height - 44
    legend_x = width / 2 - 285
    for idx, scenario in enumerate(scenario_order):
        x = legend_x + idx * 205
        body.append(rect(x, legend_y - 14, 14, 14, COLORS[scenario]))
        body.append(text(x + 22, legend_y - 2, SCENARIO_LABELS[scenario], 12, "start", color=MUTED))

    body.append(text(width / 2, height - 14, f"Source: {args.input}", 11, color=MUTED))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg(width, height, body), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
