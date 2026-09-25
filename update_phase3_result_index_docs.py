#!/usr/bin/env python3
"""Minimally document Phase-3 dynamic constrained ASA results.

This helper keeps the repository neutral: it only adds result-index entries and
a short README pointer for the strong timing-aware TritonPart baseline extension.
It does not rewrite the method docs or paper narrative.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


PHASE3_SECTIONS = '''    {
        "category": "dynamic_constrained_asa_phase3",
        "purpose": "Evaluate dynamic TritonPart-compatible ASA local refinement on native timing-aware TritonPart assignments under area, cut, path, and timing-weighted guards.",
        "primary_outputs": [
            "results/benchmark_summary/dynamic_constrained_asa_phase3_rollup.csv",
            "results/benchmark_summary/dynamic_constrained_asa_phase3_summary.csv",
        ],
        "figures": [],
        "entrypoints": [
            "partition_tritonpart_compatible_dynamic_guarded_repair.py",
            "select_dynamic_checkpoint_with_canonical_timing.py",
            "run_dynamic_canonical_checkpoint_selection.sh",
            "summarize_dynamic_constrained_asa_phase3.py",
        ],
        "interpretation": "Phase-3 evidence that constrained ASA refinement can improve native timing-aware TritonPart assignments while preserving OpenROAD-compatible area balance, raw-cut/path guards, and canonical timing-weighted crossing.",
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
            "run_dynamic_architecture_off_phase3.sh",
            "summarize_dynamic_architecture_ablation_phase3.py",
        ],
        "interpretation": "Architecture semantics are not uniformly dominant; they change the constrained-refinement trade-off, improving timing-sensitive selectivity on riscv32i while generic constrained repair is stronger on PicoRV32.",
    },
'''


README_SECTION = """## Dynamic Constrained ASA Extension

The repository also includes a Phase-3 strong-baseline extension that starts from OpenROAD native timing-aware TritonPart assignments and applies dynamic, TritonPart-compatible ASA refinement.  Candidate moves are recomputed from the current assignment and accepted only when they preserve reconstructed OpenROAD area balance, raw-cut/path guards, and canonical timing-weighted crossing.

Current Phase-3 summaries are in `results/benchmark_summary/dynamic_constrained_asa_phase3_summary.csv` and `results/benchmark_summary/dynamic_architecture_ablation_phase3_summary.csv`.  These results are intentionally scoped as a strong-baseline refinement study, not as full 3D signoff timing or PPA evidence.

"""


def find_result_index_generator() -> Path:
    candidates = [
        Path("scripts/generate_result_index.py"),
        Path("generate_result_index.py"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Could not find generate_result_index.py")


def update_generator(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if '"category": "dynamic_constrained_asa_phase3"' in text:
        print(f"{path}: Phase-3 result-index entries already present")
        return
    marker = '    {\n        "category": "repository_readiness",'
    if marker not in text:
        raise RuntimeError(f"{path}: repository_readiness marker not found")
    text = text.replace(marker, PHASE3_SECTIONS + marker, 1)
    path.write_text(text, encoding="utf-8")
    print(f"{path}: added Phase-3 result-index entries")


def update_readme(path: Path = Path("README.md")) -> None:
    text = path.read_text(encoding="utf-8")
    if "## Dynamic Constrained ASA Extension" in text:
        print("README.md: Phase-3 section already present")
        return
    for heading in ["## Limitations", "## Roadmap", "## Path-Aware Downstream Validation"]:
        marker = f"\n{heading}"
        idx = text.find(marker)
        if idx != -1:
            text = text[: idx + 1] + README_SECTION + text[idx + 1 :]
            path.write_text(text, encoding="utf-8")
            print("README.md: inserted Phase-3 section")
            return
    path.write_text(text.rstrip() + "\n\n" + README_SECTION, encoding="utf-8")
    print("README.md: appended Phase-3 section")


def regenerate_index(generator: Path) -> None:
    subprocess.run(["python3", str(generator)], check=True)


def main() -> int:
    generator = find_result_index_generator()
    update_generator(generator)
    update_readme()
    regenerate_index(generator)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
