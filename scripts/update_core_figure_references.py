#!/usr/bin/env python3
"""Update project documentation to reference the compact core figure set."""

from __future__ import annotations

from pathlib import Path


CORE_SECTION = """## Core Figures

The current figure set is intentionally compact. Low-information exploratory figures were removed and replaced by two high-density SVG summaries:

- `results/figures/core/asa_rv3d_core_results.svg`
  - normalized RISC-V-aware 3D proxy cost,
  - reduction versus generic balance,
  - v3 robustness under proxy-weight sensitivity.
- `results/figures/core/asa_rv3d_cost_breakdown.svg`
  - stacked breakdown of the 3D proxy cost terms for each method and design.

"""


def insert_after_heading(text: str, heading: str, section: str) -> str:
    if section.strip() in text:
        return text
    marker = heading + "\n"
    if marker not in text:
        return text + "\n" + section
    idx = text.index(marker) + len(marker)
    return text[:idx] + "\n" + section + text[idx:]


def replace_old_figure_paths(text: str) -> str:
    replacements = {
        "results/figures/summary/two_riscv_benchmark_partition_summary.svg": "results/figures/core/asa_rv3d_core_results.svg",
        "results/figures/summary/two_riscv_multi_metric_summary.svg": "results/figures/core/asa_rv3d_core_results.svg",
        "results/figures/summary/riscv_3d_proxy_cost_summary.svg": "results/figures/core/asa_rv3d_core_results.svg",
        "results/figures/summary/riscv_3d_proxy_sensitivity.svg": "results/figures/core/asa_rv3d_core_results.svg",
        "results/figures/summary/riscv_3d_proxy_sensitivity_margin.svg": "results/figures/core/asa_rv3d_core_results.svg",
        "results/figures/summary/riscv32i_v2_ablation_summary.svg": "results/figures/core/asa_rv3d_core_results.svg",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def update_readme(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_old_figure_paths(text)
    text = insert_after_heading(text, "## Main Results", CORE_SECTION)
    path.write_text(text, encoding="utf-8")


def update_experiment_summary(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_old_figure_paths(text)
    old = """## Key Figures

| Figure | Path | Purpose |
| --- | --- | --- |
| ASA-RV3D method flow | `results/figures/summary/asa_rv3d_method_flow.svg` | Shows the full pipeline and where the innovation enters. |
| Two RISC-V benchmark summary | `results/figures/summary/two_riscv_benchmark_partition_summary.svg` | Shows generic, v1, and v2 crossing reductions. |
| Multi-metric summary | `results/figures/summary/two_riscv_multi_metric_summary.svg` | Shows crossing, balance, and architecture separation together. |
| riscv32i ablation summary | `results/figures/summary/riscv32i_v2_ablation_summary.svg` | Shows the effect of removing objective terms. |
"""
    new = """## Key Figures

| Figure | Path | Purpose |
| --- | --- | --- |
| Core result summary | `results/figures/core/asa_rv3d_core_results.svg` | Shows normalized 3D proxy cost, reduction versus generic, and v3 sensitivity robustness. |
| Cost breakdown | `results/figures/core/asa_rv3d_cost_breakdown.svg` | Shows which proxy-cost terms dominate each method and design. |
"""
    if old in text:
        text = text.replace(old, new)
    else:
        text = insert_after_heading(text, "## Key Figures", new)
    path.write_text(text, encoding="utf-8")


def update_proxy_doc(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = replace_old_figure_paths(text)
    text = text.replace(
        "results/figures/summary/riscv_3d_proxy_cost_summary.svg",
        "results/figures/core/asa_rv3d_core_results.svg",
    )
    addition = """\nThe cost component breakdown is stored at:\n\n```text\nresults/figures/core/asa_rv3d_cost_breakdown.svg\n```\n"""
    anchor = "The main result figure is:\n\n```text\nresults/figures/core/asa_rv3d_core_results.svg\n```\n"
    if anchor in text and "results/figures/core/asa_rv3d_cost_breakdown.svg" not in text:
        text = text.replace(anchor, anchor + addition)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    update_readme(Path("README.md"))
    update_experiment_summary(Path("docs/experiment-summary.md"))
    update_proxy_doc(Path("docs/3d-proxy-cost-model.md"))
    print("updated README.md")
    print("updated docs/experiment-summary.md")
    print("updated docs/3d-proxy-cost-model.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
