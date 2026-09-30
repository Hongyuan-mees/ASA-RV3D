#!/usr/bin/env python3
"""Generate the retained historical result index for ASA-RV3D.

The paper-facing manuscript snapshot lives under paper/. This script keeps the
older development/result-family index auditable without presenting it as the
source of truth for the final manuscript tables.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


SECTIONS = [
    {
        "category": "main_timing_aware_repair",
        "purpose": "Compare TritonPart against ASA-RV3D timing-regret guarded repair across RISC-V cores and 3D partitioning scenarios.",
        "primary_outputs": [
            "results/benchmark_summary/timing_regret_guarded_all_scenarios_summary.csv",
            "results/benchmark_summary/timing_regret_guarded_three_riscv_summary.csv",
        ],
        "figures": [
            "results/figures/paper/fig5_1_timing_weighted_crossing.svg",
        ],
        "entrypoints": [
            "partition/partition_tritonpart_timing_regret_guarded_repair.py",
            "scripts/reproduce_core_results.sh",
        ],
        "interpretation": "Retained historical evidence for timing-weighted inter-tier crossing reduction over TritonPart-derived assignments.",
    },
    {
        "category": "downstream_vertical_delay_proxy",
        "purpose": "Estimate downstream timing impact by adding fixed vertical-link delay on OpenSTA paths for TritonPart, ASA-RV3D, and path-aware ASA-RV3D assignments.",
        "primary_outputs": [
            "results/benchmark_summary/path_aware_downstream_vertical_delay_summary.csv",
            "results/benchmark_summary/path_aware_downstream_vertical_delay_rollup.csv",
        ],
        "figures": [
            "results/figures/paper/fig5_2_downstream_tns_degradation.svg",
        ],
        "entrypoints": [
            "evaluation/evaluate_path_aware_downstream_vertical_delay.py",
            "partition/partition_tritonpart_path_aware_guarded_repair.py",
        ],
        "interpretation": "Retained path-level proxy validation for vertical-link-delay sensitivity.",
    },
    {
        "category": "component_ablation",
        "purpose": "Separate the contribution of TritonPart, ASA-RV3D without timing guard, timing-regret guard, path-aware repair, and architecture semantics.",
        "primary_outputs": [
            "results/benchmark_summary/component_ablation_rollup.csv",
            "results/benchmark_summary/component_ablation_timing_crossing_summary.csv",
            "results/benchmark_summary/component_ablation_downstream_summary.csv",
            "results/benchmark_summary/architecture_ablation_rollup.csv",
            "results/benchmark_summary/architecture_ablation_summary.csv",
        ],
        "figures": [
            "results/figures/paper/fig5_3_component_ablation_timing_crossing.svg",
        ],
        "entrypoints": [
            "scripts/run_component_ablation.py",
            "scripts/run_architecture_ablation.py",
        ],
        "interpretation": "Retained ablation evidence for complementary objective and guard components.",
    },
    {
        "category": "baseline_feasibility",
        "purpose": "Track OpenROAD native triton_part_design timing-aware baseline feasibility and partial comparison against ASA-RV3D.",
        "primary_outputs": [
            "results/benchmark_summary/tritonpart_design_timing_aware_baseline_rollup.csv",
            "results/benchmark_summary/tritonpart_design_timing_aware_baseline_summary.csv",
            "results/benchmark_summary/riscv32i_tritonpart_design_timing_aware_crossing.csv",
            "results/benchmark_summary/picorv32_tritonpart_design_timing_aware_crossing.csv",
            "results/benchmark_summary/scr1_core_tuned_tritonpart_design_timing_aware_crossing.csv",
        ],
        "figures": [],
        "entrypoints": [
            "scripts/probe_tritonpart_design_timing_aware.sh",
            "scripts/import_tritonpart_design_solution.py",
            "scripts/summarize_tritonpart_design_timing_aware_baseline.py",
        ],
        "interpretation": "Historical baseline-feasibility tracking for OpenROAD native timing-aware TritonPart runs.",
    },
    {
        "category": "robustness_checks",
        "purpose": "Check whether downstream conclusions are stable under vertical-delay, path-count, and path-budget variations.",
        "primary_outputs": [
            "results/benchmark_summary/path_aware_downstream_delay_sweep_rollup.csv",
            "results/benchmark_summary/path_aware_downstream_pathcount_sweep_rollup.csv",
            "results/benchmark_summary/ibex_path_aware_budget_sensitivity.csv",
        ],
        "figures": [
            "results/figures/paper/fig5_4_vertical_delay_sensitivity.svg",
            "results/figures/paper/fig5_4_ibex_path_budget_sensitivity.svg",
        ],
        "entrypoints": [
            "scripts/run_path_aware_downstream_delay_sweep.py",
            "scripts/run_path_aware_downstream_pathcount_sweep.py",
            "partition/partition_tritonpart_path_aware_guarded_repair.py",
        ],
        "interpretation": "Retained sensitivity checks for vertical-delay and path-count assumptions.",
    },
    {
        "category": "scenario_behavior_analysis",
        "purpose": "Measure how control/datapath, memory-near-logic, and state/clock scenarios change tier assignment behavior under guarded repair.",
        "primary_outputs": [
            "results/benchmark_summary/scenario_behavior_rollup.csv",
            "results/benchmark_summary/scenario_behavior_paper_summary.csv",
            "results/benchmark_summary/scenario_behavior_top_unit_changes.csv",
        ],
        "figures": [],
        "entrypoints": [
            "evaluation/analyze_scenario_behavior.py",
            "evaluation/summarize_scenario_behavior.py",
        ],
        "interpretation": "Retained development analysis of scenario-dependent behavior.",
    },
    {
        "category": "pseudo3d_realization",
        "purpose": "Export pseudo-3D tier-layout artifacts and vertical-link candidates for early 3D-aware validation and presentation.",
        "primary_outputs": [
            "results/benchmark_summary/pseudo3d_realization_rollup.csv",
            "results/benchmark_summary/pseudo3d_realization_summary.csv",
            "results/benchmark_summary/pseudo3d_layout_summary.csv",
        ],
        "figures": [],
        "entrypoints": [
            "evaluation/evaluate_pseudo3d_realization.py",
            "evaluation/export_pseudo3d_layout.py",
        ],
        "interpretation": "Visualization and proxy-validation artifacts, not signoff 3-D place-and-route.",
    },
    {
        "category": "boundary_cases",
        "purpose": "Track designs where the improvement space is limited or neutral, strengthening the credibility of the evaluation.",
        "primary_outputs": [
            "results/benchmark_summary/serv_timing_regret_guarded_summary.csv",
            "results/benchmark_summary/scr1_core_tuned_timing_regret_guarded_summary.csv",
        ],
        "figures": [
            "results/figures/final/scr1_core_tuned_timing_weighted_crossing.svg",
        ],
        "entrypoints": [
            "partition/partition_tritonpart_timing_regret_guarded_repair.py",
        ],
        "interpretation": "Boundary/sanity cases retained to show limited or neutral repair opportunity.",
    },
    {
        "category": "dynamic_constrained_asa_phase3",
        "purpose": "Evaluate dynamic TritonPart-compatible ASA local refinement on native timing-aware TritonPart assignments under area, cut, path, and timing-weighted guards.",
        "primary_outputs": [
            "results/benchmark_summary/dynamic_constrained_asa_phase3_rollup.csv",
            "results/benchmark_summary/dynamic_constrained_asa_phase3_summary.csv",
        ],
        "figures": [],
        "entrypoints": [
            "partition/partition_tritonpart_compatible_dynamic_guarded_repair.py",
            "scripts/select_dynamic_checkpoint_with_canonical_timing.py",
            "scripts/run_dynamic_canonical_checkpoint_selection.sh",
            "scripts/summarize_dynamic_constrained_asa_phase3.py",
        ],
        "interpretation": "Retained Phase-3 development evidence for constrained local refinement.",
    },
    {
        "category": "dynamic_architecture_ablation_phase3",
        "purpose": "Compare dynamic constrained refinement with architecture semantics enabled versus disabled under the same area, cut, path, and timing-weighted guards.",
        "primary_outputs": [
            "results/benchmark_summary/dynamic_architecture_ablation_phase3_rollup.csv",
            "results/benchmark_summary/dynamic_architecture_ablation_phase3_summary.csv",
        ],
        "figures": [],
        "entrypoints": [
            "scripts/run_dynamic_architecture_off_phase3.sh",
            "scripts/summarize_dynamic_architecture_ablation_phase3.py",
        ],
        "interpretation": "Retained architecture-ablation development evidence; not the final manuscript source of truth.",
    },
    {
        "category": "repository_readiness",
        "purpose": "Check that core scripts, summaries, figures, and wording are aligned and avoid overclaiming.",
        "primary_outputs": [
            "results/benchmark_summary/paper_readiness_audit.csv",
            "results/benchmark_summary/paper_readiness_audit.md",
        ],
        "figures": [],
        "entrypoints": [
            "scripts/audit_paper_readiness.py",
        ],
        "interpretation": "Historical repository hygiene audit retained for development traceability.",
    },
]


def status(path: Path) -> str:
    return "present" if path.exists() else "missing"


def join_items(items: list[str]) -> str:
    return "; ".join(items)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "category",
        "purpose",
        "primary_outputs",
        "primary_output_status",
        "figures",
        "figure_status",
        "entrypoints",
        "entrypoint_status",
        "interpretation",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(path)


def write_markdown(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Historical Development Result Index",
        "",
        "This generated index documents retained development and historical experiment families.",
        "It is not the source of truth for the final manuscript tables. For paper-facing results and provenance, see `README.md` and `paper/`.",
        "",
        "The listed metrics are proxy-level evaluation artifacts unless explicitly stated otherwise.",
        "",
    ]

    for row in rows:
        title = row["category"].replace("_", " ").title()
        lines.extend(
            [
                f"## {title}",
                "",
                f"**Purpose.** {row['purpose']}",
                "",
                f"**Interpretation.** {row['interpretation']}",
                "",
                "**Primary outputs.**",
                "",
            ]
        )
        for item, state in zip(row["primary_outputs"].split("; "), row["primary_output_status"].split("; ")):
            lines.append(f"- `{item}` ({state})")
        lines.extend(["", "**Figures.**", ""])
        if row["figures"]:
            for item, state in zip(row["figures"].split("; "), row["figure_status"].split("; ")):
                lines.append(f"- `{item}` ({state})")
        else:
            lines.append("- None")
        lines.extend(["", "**Entrypoints.**", ""])
        for item, state in zip(row["entrypoints"].split("; "), row["entrypoint_status"].split("; ")):
            lines.append(f"- `{item}` ({state})")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--csv", type=Path, default=Path("results/benchmark_summary/result_index.csv"))
    parser.add_argument("--markdown", type=Path, default=Path("docs/result-index.md"))
    args = parser.parse_args()

    root = args.repo_root.resolve()
    rows: list[dict[str, str]] = []

    for section in SECTIONS:
        primary_outputs = section["primary_outputs"]
        figures = section["figures"]
        entrypoints = section["entrypoints"]
        rows.append(
            {
                "category": section["category"],
                "purpose": section["purpose"],
                "primary_outputs": join_items(primary_outputs),
                "primary_output_status": join_items([status(root / item) for item in primary_outputs]),
                "figures": join_items(figures),
                "figure_status": join_items([status(root / item) for item in figures]),
                "entrypoints": join_items(entrypoints),
                "entrypoint_status": join_items([status(root / item) for item in entrypoints]),
                "interpretation": section["interpretation"],
            }
        )

    csv_path = args.csv if args.csv.is_absolute() else root / args.csv
    markdown_path = args.markdown if args.markdown.is_absolute() else root / args.markdown
    write_csv(csv_path, rows)
    write_markdown(markdown_path, rows)

    missing = [
        row
        for row in rows
        if "missing" in row["primary_output_status"]
        or "missing" in row["figure_status"]
        or "missing" in row["entrypoint_status"]
    ]
    print(f"categories={len(rows)} missing_categories={len(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
