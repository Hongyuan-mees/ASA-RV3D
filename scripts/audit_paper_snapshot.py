#!/usr/bin/env python3
"""Audit the ASA-RV3D paper-facing snapshot.

This check is intentionally small. It validates the files and values that make
up the manuscript-facing public artifact under paper/, rather than re-running
historical development experiments.
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "CITATION.cff",
    "paper/README.md",
    "paper/artifact_manifest.md",
    "paper/table2_partition_results.csv",
    "paper/table3_path_validation.csv",
    "paper/scr1_feasibility_restoration.csv",
    "partition/partition_tritonpart_compatible_normalized_dynamic_guarded_repair.py",
]

EXPECTED_TABLE2 = {
    ("PicoRV32", "control/datapath"): (346, 205, 207, 116, 217, 129, -11.2),
    ("PicoRV32", "memory-near-logic"): (346, 157, 207, 95, 202, 88, 7.4),
    ("PicoRV32", "state/clock"): (346, 211, 207, 98, 214, 90, 8.2),
    ("riscv32i", "control/datapath"): (230, 119, 229, 126, 241, 116, 7.9),
    ("riscv32i", "memory-near-logic"): (230, 104, 229, 105, 226, 96, 8.6),
    ("riscv32i", "state/clock"): (230, 97, 229, 72, 241, 58, 19.4),
}

EXPECTED_TABLE3 = {
    ("PicoRV32", "Native"): (0.30, 0.30, 1, 0.0, 0.0, 0.0),
    ("PicoRV32", "Context-OFF"): (0.30, 0.30, 1, 0.0, 0.0, 0.0),
    ("PicoRV32", "Context-ON"): (0.30, 0.30, 1, 0.0, 0.0, 0.0),
    ("riscv32i", "Native"): (0.35, 0.41, 2, 0.475, 1.195, 2.474),
    ("riscv32i", "Context-OFF"): (0.35, 0.35, 1, 0.415, 1.045, 2.095),
    ("riscv32i", "Context-ON"): (0.35, 0.35, 1, 0.415, 1.045, 2.095),
}



EXPECTED_SCR1_RESTORATION = {
    "design": "scr1_core_tuned",
    "native_tier0_area_fraction": "0.520588",
    "restored_tier0_area_fraction": "0.519990",
    "restoration_moves": "5",
    "native_crossing_nets": "272",
    "restored_crossing_nets": "276",
    "raw_cut_regret": "0.014706",
    "path_avg_cut_regret": "0.000000",
    "path_worst_cut_delta": "0.000000",
    "guard_status": "pass",
    "final_judgement": "A_restoration_successful_under_default_guards",
    "root_cause_statement": "imported_native_mildly_infeasible_under_reconstructed_openroad_area_criterion",
}

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def approx(actual: float, expected: float, tol: float = 1e-6) -> bool:
    return abs(actual - expected) <= tol


def audit_required_files() -> None:
    missing = [p for p in REQUIRED_FILES if not (ROOT / p).is_file()]
    if missing:
        fail("missing required file(s): " + ", ".join(missing))


def audit_readme_terms() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for term in ["Context-OFF", "Context-ON", "recovered RISC-V design context", "paper/table2_partition_results.csv"]:
        if term not in text:
            fail(f"README.md missing paper-facing term: {term}")
    if "A repository license has not yet been specified" in text:
        fail("README.md still says the repository has no license")


def audit_table2() -> None:
    path = ROOT / "paper" / "table2_partition_results.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if len(rows) != 6:
        fail(f"table2 row count is {len(rows)}, expected 6")

    positive = 0
    negative = 0
    seen = set()
    for row in rows:
        key = (row["design"], row["scenario"])
        seen.add(key)
        if key not in EXPECTED_TABLE2:
            fail(f"unexpected table2 row: {key}")
        expected = EXPECTED_TABLE2[key]
        actual = (
            int(row["native_raw"]),
            int(row["native_sensitive"]),
            int(row["context_off_raw"]),
            int(row["context_off_sensitive"]),
            int(row["context_on_raw"]),
            int(row["context_on_sensitive"]),
            float(row["context_gain_percent"]),
        )
        for got, want in zip(actual[:-1], expected[:-1]):
            if got != want:
                fail(f"table2 {key} value mismatch: got {actual}, expected {expected}")
        if not approx(actual[-1], expected[-1]):
            fail(f"table2 {key} context gain mismatch: got {actual[-1]}, expected {expected[-1]}")
        if row.get("provenance") != "paper_reported_snapshot":
            fail(f"table2 {key} provenance is not paper_reported_snapshot")
        if actual[-1] > 0:
            positive += 1
        elif actual[-1] < 0:
            negative += 1

    if seen != set(EXPECTED_TABLE2):
        fail("table2 expected row set mismatch")
    if positive != 5 or negative != 1:
        fail(f"table2 gain counts mismatch: positive={positive}, negative={negative}")


def audit_table3() -> None:
    path = ROOT / "paper" / "table3_path_validation.csv"
    rows = list(csv.DictReader(path.open(newline="", encoding="utf-8")))
    if len(rows) != 6:
        fail(f"table3 row count is {len(rows)}, expected 6")

    seen = set()
    for row in rows:
        key = (row["design"], row["assignment"])
        seen.add(key)
        if key not in EXPECTED_TABLE3:
            fail(f"unexpected table3 row: {key}")
        expected = EXPECTED_TABLE3[key]
        actual = (
            float(row["crossing_path_fraction"]),
            float(row["mean_tier_transitions"]),
            int(row["max_tier_transitions"]),
            float(row["tns_proxy_20ps_ns"]),
            float(row["tns_proxy_50ps_ns"]),
            float(row["tns_proxy_100ps_ns"]),
        )
        for got, want in zip(actual, expected):
            if isinstance(want, int):
                if got != want:
                    fail(f"table3 {key} value mismatch: got {actual}, expected {expected}")
            elif not approx(float(got), float(want)):
                fail(f"table3 {key} value mismatch: got {actual}, expected {expected}")
        if row.get("provenance") != "paper_reported_snapshot":
            fail(f"table3 {key} provenance is not paper_reported_snapshot")

    if seen != set(EXPECTED_TABLE3):
        fail("table3 expected row set mismatch")



def audit_scr1_restoration() -> None:
    path = ROOT / "paper" / "scr1_feasibility_restoration.csv"
    rows = read_csv(path)
    observed = {row.get("metric", ""): row.get("value", "") for row in rows}
    if set(observed) != set(EXPECTED_SCR1_RESTORATION):
        fail("scr1 restoration metric set mismatch")
    for key, expected in EXPECTED_SCR1_RESTORATION.items():
        actual = observed.get(key)
        if actual != expected:
            fail(f"scr1 restoration {key} mismatch: got {actual}, expected {expected}")



def audit_paper_facing_docs() -> None:
    checks = {
        "paper/README.md": [
            "scr1_feasibility_restoration.csv",
            "SCR1 Boundary-Case Restoration",
            "is **not** added to the primary six-case Context-OFF / Context-ON comparison",
        ],
        "docs/method.md": [
            "feasibility-restoration pre-stage",
            "original native TritonPart assignment",
            "does not use recovered design context",
        ],
        "docs/reproduction-guide.md": [
            "scr1_feasibility_restoration.csv",
            "run_baseline_feasibility_restoration.sh restore",
            "does not establish a new guard budget",
        ],
        "CITATION.cff": [
            "version: 1.5.0",
            "date-released: 2026-10-07",
        ],
    }
    for relpath, needles in checks.items():
        content = (ROOT / relpath).read_text(encoding="utf-8")
        for needle in needles:
            if needle not in content:
                fail(f"{relpath} missing expected text: {needle}")


def main() -> int:
    audit_required_files()
    audit_readme_terms()
    audit_table2()
    audit_table3()
    audit_scr1_restoration()
    audit_paper_facing_docs()
    print("paper snapshot audit: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
