#!/usr/bin/env python3
"""Generate paper-facing SVG figures from RV3D experiment CSVs.

The script intentionally uses only the Python standard library and writes SVG
directly, so it does not require matplotlib/seaborn on the experiment server.
Run from the repository root.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable


OUT_DIR = Path("results/figures/paper")
SUMMARY_DIR = Path("results/benchmark_summary")
PALETTE = {
    "tritonpart": "#777777",
    "asa": "#4C78A8",
    "path": "#F28E2B",
    "bad": "#C44E52",
    "grid": "#E5E7EB",
    "text": "#111827",
    "muted": "#4B5563",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def find_first(paths: Iterable[str]) -> Path:
    for name in paths:
        path = SUMMARY_DIR / name
        if path.exists():
            return path
    raise FileNotFoundError("None of the candidate CSV files exist: " + ", ".join(paths))


def f(value: str | float) -> float:
    if value in ("", None):
        return 0.0
    return float(value)


def esc(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_text(x: float, y: float, text: object, size: int = 14, weight: str = "400", anchor: str = "start", color: str | None = None) -> str:
    return f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, sans-serif" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color or PALETTE["text"]}">{esc(text)}</text>'


def write_svg(path: Path, width: int, height: int, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
    svg += '<rect width="100%" height="100%" fill="white"/>\n'
    svg += body
    svg += "\n</svg>\n"
    path.write_text(svg, encoding="utf-8")
    print(path)


def nice_scenario(name: str) -> str:
    return {
        "control_datapath_split": "Control/datapath",
        "memory_near_logic": "Memory-near-logic",
        "state_and_clock_protected": "State/clock",
    }.get(name, name.replace("_", " "))


def nice_design(name: str) -> str:
    return {
        "riscv32i": "riscv32i",
        "ibex": "Ibex",
        "picorv32": "PicoRV32",
        "scr1_core_tuned": "SCR1",
    }.get(name, name)


def grouped_bar_chart(
    path: Path,
    title: str,
    subtitle: str,
    groups: list[str],
    series: list[tuple[str, list[float], str]],
    source: str,
    width: int = 1280,
    height: int = 760,
    y_label: str = "",
    value_fmt: str = "{:.2f}",
) -> None:
    margin_l, margin_r, margin_t, margin_b = 190, 60, 110, 115
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    max_v = max([v for _, values, _ in series for v in values] + [1.0])
    max_v *= 1.12
    body: list[str] = []
    body.append(svg_text(width / 2, 42, title, 28, "700", "middle"))
    body.append(svg_text(width / 2, 70, subtitle, 14, "400", "middle", PALETTE["muted"]))
    if y_label:
        body.append(svg_text(margin_l, 95, y_label, 13, "600", "start", PALETTE["muted"]))

    ticks = 5
    for i in range(ticks + 1):
        value = max_v * i / ticks
        y = margin_t + plot_h - plot_h * value / max_v
        body.append(f'<line x1="{margin_l}" y1="{y:.1f}" x2="{width - margin_r}" y2="{y:.1f}" stroke="{PALETTE["grid"]}" stroke-width="1"/>')
        body.append(svg_text(margin_l - 10, y + 4, value_fmt.format(value), 11, "400", "end", PALETTE["muted"]))

    n = len(groups)
    group_w = plot_w / max(n, 1)
    bar_w = min(22, group_w / (len(series) + 1.7))
    for gi, group in enumerate(groups):
        gx = margin_l + gi * group_w + group_w / 2
        body.append(svg_text(gx, height - margin_b + 25, group, 11, "600", "middle", PALETTE["text"]))
        for si, (label, values, color) in enumerate(series):
            x = gx - (len(series) * bar_w) / 2 + si * bar_w + 2
            v = values[gi]
            h = plot_h * v / max_v
            y = margin_t + plot_h - h
            body.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w - 4:.1f}" height="{h:.1f}" fill="{color}"/>')
            if n <= 12:
                body.append(svg_text(x + (bar_w - 4) / 2, y - 5, value_fmt.format(v), 10, "600", "middle"))

    lx = margin_l
    ly = height - 45
    for label, _, color in series:
        body.append(f'<rect x="{lx:.1f}" y="{ly - 12:.1f}" width="13" height="13" fill="{color}"/>')
        body.append(svg_text(lx + 20, ly, label, 13, "400", "start", PALETTE["muted"]))
        lx += 210
    body.append(svg_text(width / 2, height - 18, f"Source: {source}", 11, "400", "middle", PALETTE["muted"]))
    write_svg(path, width, height, "\n".join(body))


def grouped_horizontal_bar_chart(
    path: Path,
    title: str,
    subtitle: str,
    groups: list[tuple[str, str]],
    series: list[tuple[str, list[float], str]],
    source: str,
    width: int = 1280,
    row_h: int = 58,
    x_label: str = "",
    value_fmt: str = "{:.2f}",
) -> None:
    margin_l, margin_r, margin_t, margin_b = 230, 95, 112, 88
    height = margin_t + margin_b + row_h * len(groups)
    plot_w = width - margin_l - margin_r
    max_v = max([v for _, values, _ in series for v in values] + [1.0])
    max_v *= 1.15
    body: list[str] = []
    body.append(svg_text(width / 2, 40, title, 26, "700", "middle"))
    body.append(svg_text(width / 2, 66, subtitle, 14, "400", "middle", PALETTE["muted"]))
    if x_label:
        body.append(svg_text(margin_l, 94, x_label, 13, "600", "start", PALETTE["muted"]))

    ticks = 5
    for i in range(ticks + 1):
        value = max_v * i / ticks
        x = margin_l + plot_w * value / max_v
        body.append(f'<line x1="{x:.1f}" y1="{margin_t - 8}" x2="{x:.1f}" y2="{height - margin_b + 6}" stroke="{PALETTE["grid"]}" stroke-width="1"/>')
        body.append(svg_text(x, margin_t - 16, value_fmt.format(value), 11, "400", "middle", PALETTE["muted"]))

    bar_h = min(13, row_h / (len(series) + 1.7))
    for gi, (design, scenario) in enumerate(groups):
        gy = margin_t + gi * row_h + row_h / 2
        body.append(svg_text(24, gy - 6, design, 13, "700", "start"))
        body.append(svg_text(24, gy + 13, scenario, 12, "400", "start", PALETTE["muted"]))
        body.append(f'<line x1="{margin_l}" y1="{margin_t + (gi + 1) * row_h:.1f}" x2="{width - margin_r}" y2="{margin_t + (gi + 1) * row_h:.1f}" stroke="#F3F4F6" stroke-width="1"/>')
        for si, (_, values, color) in enumerate(series):
            v = values[gi]
            bar_w = plot_w * v / max_v
            y = gy - (len(series) * bar_h) / 2 + si * bar_h + 1
            body.append(f'<rect x="{margin_l:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h - 2:.1f}" fill="{color}"/>')
            if v > 0:
                label_x = min(margin_l + bar_w + 6, width - margin_r + 52)
                body.append(svg_text(label_x, y + bar_h - 3, value_fmt.format(v), 10, "600", "start"))

    lx = margin_l
    ly = height - 44
    for label, _, color in series:
        body.append(f'<rect x="{lx:.1f}" y="{ly - 12:.1f}" width="13" height="13" fill="{color}"/>')
        body.append(svg_text(lx + 20, ly, label, 13, "400", "start", PALETTE["muted"]))
        lx += 210
    body.append(svg_text(width / 2, height - 17, f"Source: {source}", 11, "400", "middle", PALETTE["muted"]))
    write_svg(path, width, height, "\n".join(body))


def plot_main_timing_crossing() -> None:
    source = find_first(
        [
            "timing_regret_guarded_all_scenarios_summary.csv",
            "timing_regret_guarded_four_riscv_summary.csv",
            "timing_regret_guarded_three_riscv_summary.csv",
        ]
    )
    rows = read_csv(source)
    groups = [(nice_design(r["design"]), nice_scenario(r["scenario"])) for r in rows]
    tri = [f(r["tritonpart_timing_weighted_crossing"]) for r in rows]
    asa_col = "timing_regret_guarded_timing_weighted_crossing"
    asa = [f(r[asa_col]) for r in rows]
    grouped_horizontal_bar_chart(
        OUT_DIR / "fig5_1_timing_weighted_crossing.svg",
        "Timing-Weighted Crossing Across Design-Scenario Cases",
        "Lower is better. ASA-RV3D timing-regret repair is compared against TritonPart.",
        groups,
        [
            ("TritonPart", tri, PALETTE["tritonpart"]),
            ("ASA-RV3D", asa, PALETTE["asa"]),
        ],
        str(source),
        x_label="Timing-weighted crossing",
    )


def plot_downstream_validation() -> None:
    source = SUMMARY_DIR / "path_aware_downstream_vertical_delay_summary.csv"
    rows = read_csv(source)
    groups = [(nice_design(r["design"]), nice_scenario(r["scenario"])) for r in rows]
    tri = [f(r["tritonpart_tns_degradation"]) for r in rows]
    asa = [f(r["asa_rv3d_tns_degradation"]) for r in rows]
    path = [f(r["path_aware_tns_degradation"]) for r in rows]
    grouped_horizontal_bar_chart(
        OUT_DIR / "fig5_2_downstream_tns_degradation.svg",
        "Downstream Vertical-Delay Proxy: TNS Degradation",
        "Fixed vertical delay on OpenSTA paths. Lower degradation is better.",
        groups,
        [
            ("TritonPart", tri, PALETTE["tritonpart"]),
            ("ASA-RV3D", asa, PALETTE["asa"]),
            ("Path-aware ASA", path, PALETTE["path"]),
        ],
        str(source),
        x_label="Estimated TNS degradation (ns)",
    )


def plot_ablation_rollup() -> None:
    source = SUMMARY_DIR / "component_ablation_rollup.csv"
    rows = read_csv(source)
    timing = [r for r in rows if r["metric_group"] == "timing_crossing"]
    order = ["tritonpart", "asa_no_timing_guard", "asa_timing_regret", "asa_path_aware"]
    labels = {
        "tritonpart": "TritonPart",
        "asa_no_timing_guard": "ASA no timing guard",
        "asa_timing_regret": "ASA timing-regret",
        "asa_path_aware": "Path-aware ASA",
    }
    by_case = {r["case"]: r for r in timing}
    groups = [labels[k] for k in order if k in by_case]
    values = [f(by_case[k]["mean_timing_weighted_crossing"]) for k in order if k in by_case]
    grouped_bar_chart(
        OUT_DIR / "fig5_3_component_ablation_timing_crossing.svg",
        "Component Ablation: Net-Level Timing Proxy",
        "Timing-regret guard optimizes net-level timing-weighted crossing; path-aware guard targets downstream paths.",
        groups,
        [("Mean timing-weighted crossing", values, PALETTE["asa"])],
        str(source),
        width=980,
        height=620,
        y_label="Mean timing-weighted crossing",
    )


def plot_sensitivity() -> None:
    source = SUMMARY_DIR / "path_aware_downstream_delay_sweep_rollup.csv"
    rows = read_csv(source)
    groups = [r["vertical_delay_ns"] for r in rows]
    wns = [100 * f(r["mean_wns_reduction_vs_asa"]) for r in rows]
    tns = [100 * f(r["mean_tns_reduction_vs_asa"]) for r in rows]
    grouped_bar_chart(
        OUT_DIR / "fig5_4_vertical_delay_sensitivity.svg",
        "Vertical-Link Delay Sensitivity",
        "Mean downstream degradation reduction versus ASA-RV3D across 12 cases.",
        groups,
        [
            ("WNS reduction", wns, PALETTE["asa"]),
            ("TNS reduction", tns, PALETTE["path"]),
        ],
        str(source),
        width=900,
        height=560,
        y_label="Mean reduction vs ASA-RV3D (%)",
        value_fmt="{:.1f}",
    )


def plot_budget_sensitivity() -> None:
    source = SUMMARY_DIR / "ibex_path_aware_budget_sensitivity.csv"
    rows = read_csv(source)
    groups = [r["path_budget"] for r in rows]
    crossing = [100 * f(r["path_aware_crossing_path_fraction"]) for r in rows]
    net_delta = [f(r["net_crossing_delta"]) for r in rows]
    grouped_bar_chart(
        OUT_DIR / "fig5_4_ibex_path_budget_sensitivity.svg",
        "Ibex Path-Aware Budget Sensitivity",
        "Protecting more critical paths reduces fragmentation at increasing net-crossing cost.",
        groups,
        [
            ("Crossing path fraction (%)", crossing, PALETTE["asa"]),
            ("Net crossing delta", net_delta, PALETTE["path"]),
        ],
        str(source),
        width=900,
        height=560,
        y_label="Percent / count",
        value_fmt="{:.1f}",
    )


def main() -> int:
    plot_main_timing_crossing()
    plot_downstream_validation()
    plot_ablation_rollup()
    plot_sensitivity()
    plot_budget_sensitivity()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
