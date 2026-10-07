#!/usr/bin/env python3
"""Audit native timing-aware baseline feasibility under reconstructed area data.

This reviewer-response audit is intentionally read-only with respect to paper
snapshots. It checks whether native timing-aware TritonPart assignments are
inside the reconstructed OpenROAD area-balance window used by normalized
dynamic Phase-3, and records import provenance separately from area matching.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.net_graph_utils import normalize_instance_name, normalize_lookup_name, read_csv  # noqa: E402


DESIGNS = ("picorv32", "riscv32i", "scr1_core_tuned")
AREA_LO = 0.48
AREA_HI = 0.52


def design_assignment_path(design: str) -> Path:
    return Path("results") / f"{design}_tritonpart_design_timing_aware" / "tritonpart_design_timing_aware_assignment.csv"


def design_area_path(design: str) -> Path:
    return Path("results") / "benchmark_summary" / f"{design}_openroad_instance_area.csv"


def design_manifest_path(design: str) -> Path:
    return design_assignment_path(design).parent / "manifest.json"


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        out = float(text)
    except ValueError:
        return None
    if not math.isfinite(out):
        return None
    return out


def normalize_tier(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text in {"0", "tier0", "tier_0", "top"}:
        return "tier0"
    if text in {"1", "tier1", "tier_1", "bottom"}:
        return "tier1"
    return text


def instance_aliases(name: str | None) -> set[str]:
    if not name:
        return set()
    raw = str(name).strip()
    if not raw:
        return set()
    candidates = {
        raw,
        raw.replace("\\[", "[").replace("\\]", "]"),
        raw.replace("[", "\\[").replace("]", "\\]"),
    }
    aliases: set[str] = set()
    for candidate in candidates:
        norm = normalize_instance_name(candidate)
        lookup = normalize_lookup_name(candidate)
        if norm:
            aliases.add(norm)
            aliases.add(norm.strip("\\"))
        if lookup:
            aliases.add(lookup)
            aliases.add(lookup.strip("\\"))
    return {a for a in aliases if a}


def read_import_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "import_manifest": str(path),
            "true_import_fallback_rows": "unknown",
            "import_status_counts": "unknown",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {
            "import_manifest": str(path),
            "true_import_fallback_rows": "unknown",
            "import_status_counts": "invalid_json",
        }

    status_counts = data.get("status_counts")
    counts_text = "unknown"
    fallback_rows: object = "unknown"
    if isinstance(status_counts, dict):
        counts_text = ";".join(f"{key}:{value}" for key, value in sorted(status_counts.items()))
        fallback_rows = sum(int(value) for key, value in status_counts.items() if "fallback" in str(key).lower())
    for key in ("fallback_rows", "fallback_row_count", "import_fallback_rows"):
        value = data.get(key)
        if isinstance(value, int):
            fallback_rows = value
            break
    return {
        "import_manifest": str(path),
        "true_import_fallback_rows": fallback_rows,
        "import_status_counts": counts_text,
    }


def load_area_index(path: Path) -> tuple[dict[str, float], dict[str, set[str]], int, int]:
    rows = read_csv(path)
    area_by_id: dict[str, float] = {}
    alias_to_ids: dict[str, set[str]] = defaultdict(set)
    skipped_nonunique = 0

    for index, row in enumerate(rows):
        status = (row.get("status") or "unique").strip().lower()
        if status and status != "unique":
            skipped_nonunique += 1
            continue

        area = parse_float(row.get("area"))
        if area is None:
            continue

        canonical = row.get("canonical_instance") or row.get("instance") or row.get("variant") or f"row_{index}"
        canonical_id = normalize_instance_name(canonical) or normalize_lookup_name(canonical) or str(canonical)
        area_by_id[canonical_id] = area

        for key in ("canonical_instance", "variant", "instance", "name"):
            for alias in instance_aliases(row.get(key)):
                alias_to_ids[alias].add(canonical_id)

    return area_by_id, alias_to_ids, len(rows), skipped_nonunique


def match_area(instance: str, area_by_id: dict[str, float], alias_to_ids: dict[str, set[str]]) -> tuple[str, float | None]:
    matches: set[str] = set()
    for alias in instance_aliases(instance):
        matches.update(alias_to_ids.get(alias, set()))
    if len(matches) == 1:
        matched_id = next(iter(matches))
        return "matched", area_by_id[matched_id]
    if len(matches) > 1:
        return "ambiguous", None
    return "unmatched", None


def area_violation(frac: float | None, lo: float, hi: float) -> float | str:
    if frac is None:
        return ""
    if frac < lo:
        return lo - frac
    if frac > hi:
        return frac - hi
    return 0.0


def fmt(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def audit_design(design: str, root: Path, lo: float, hi: float) -> dict[str, object]:
    assignment_rel = design_assignment_path(design)
    area_rel = design_area_path(design)
    manifest_rel = design_manifest_path(design)
    assignment_path = root / assignment_rel
    area_path = root / area_rel
    manifest = read_import_manifest(root / manifest_rel)

    row: dict[str, object] = {
        "design": design,
        "native_assignment": str(assignment_rel),
        "openroad_area": str(area_rel),
        "native_timing_aware_completed": False,
        "assignment_instances": 0,
        "matched_area_instances": 0,
        "unmatched_area_instances": 0,
        "ambiguous_area_instances": 0,
        "area_coverage_fraction": "",
        "tier0_area": "",
        "tier1_area": "",
        "tier0_area_fraction": "",
        "area_lo": lo,
        "area_hi": hi,
        "area_violation": "",
        "reconstructed_area_pass": False,
        "true_import_fallback_rows": manifest["true_import_fallback_rows"],
        "import_manifest": manifest["import_manifest"],
        "import_status_counts": manifest["import_status_counts"],
        "root_cause_status": "",
        "notes": "",
    }

    missing: list[str] = []
    if not assignment_path.exists():
        missing.append("native_assignment")
    if not area_path.exists():
        missing.append("openroad_area")
    if missing:
        row["root_cause_status"] = "missing_input"
        row["notes"] = ";".join(missing)
        return row

    assignment_rows = read_csv(assignment_path)
    row["native_timing_aware_completed"] = bool(assignment_rows)
    row["assignment_instances"] = len(assignment_rows)

    if not assignment_rows:
        row["root_cause_status"] = "empty_assignment"
        row["notes"] = "assignment file exists but contains no rows"
        return row

    area_by_id, alias_to_ids, area_rows, skipped_nonunique = load_area_index(area_path)
    tier_area = {"tier0": 0.0, "tier1": 0.0}
    matched = 0
    unmatched = 0
    ambiguous = 0
    unknown_tier = 0

    for assignment in assignment_rows:
        instance = assignment.get("instance") or assignment.get("name") or ""
        tier = normalize_tier(assignment.get("tier"))
        status, area = match_area(instance, area_by_id, alias_to_ids)
        if status == "matched" and area is not None:
            matched += 1
            if tier in tier_area:
                tier_area[tier] += area
            else:
                unknown_tier += 1
        elif status == "ambiguous":
            ambiguous += 1
        else:
            unmatched += 1

    total_instances = len(assignment_rows)
    coverage = matched / total_instances if total_instances else 0.0
    total_area = tier_area["tier0"] + tier_area["tier1"]
    tier0_fraction = tier_area["tier0"] / total_area if total_area > 0 else None
    violation = area_violation(tier0_fraction, lo, hi)
    pass_area = isinstance(violation, float) and violation == 0.0 and coverage >= 0.99

    row.update(
        {
            "matched_area_instances": matched,
            "unmatched_area_instances": unmatched,
            "ambiguous_area_instances": ambiguous,
            "area_coverage_fraction": coverage,
            "tier0_area": tier_area["tier0"],
            "tier1_area": tier_area["tier1"],
            "tier0_area_fraction": tier0_fraction if tier0_fraction is not None else "",
            "area_violation": violation,
            "reconstructed_area_pass": pass_area,
        }
    )

    notes = [
        f"area_rows={area_rows}",
        f"skipped_nonunique_area_rows={skipped_nonunique}",
        "import_fallback_source=manifest" if manifest["true_import_fallback_rows"] != "unknown" else "import_fallback_source=unknown",
    ]
    if unknown_tier:
        notes.append(f"unknown_tier_matches={unknown_tier}")
    if coverage < 0.99:
        row["root_cause_status"] = "area_coverage_insufficient"
    elif pass_area:
        row["root_cause_status"] = "reconstructed_area_feasible"
    else:
        row["root_cause_status"] = "reconstructed_area_infeasible"
    row["notes"] = ";".join(notes)
    return row


def write_csv(path: Path, rows: Iterable[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: fmt(row.get(key, "")) for key in fieldnames})


def write_scr1_report(path: Path, scr1_row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    status = str(scr1_row.get("root_cause_status", ""))
    frac = scr1_row.get("tier0_area_fraction", "")
    violation = scr1_row.get("area_violation", "")
    coverage = scr1_row.get("area_coverage_fraction", "")
    fallback = scr1_row.get("true_import_fallback_rows", "")

    lines = [
        "# SCR1 Native Baseline Infeasibility Analysis",
        "",
        "This file is generated by `scripts/audit_native_baseline_feasibility.py`.",
        "It audits the imported native timing-aware TritonPart assignment under the",
        "same reconstructed OpenROAD instance-area accounting used by normalized dynamic Phase-3.",
        "",
        "## Observed Evidence",
        "",
        f"- Native assignment: `{scr1_row.get('native_assignment', '')}`",
        f"- OpenROAD area file: `{scr1_row.get('openroad_area', '')}`",
        f"- Import manifest: `{scr1_row.get('import_manifest', '')}`",
        f"- Assignment instances: {scr1_row.get('assignment_instances', '')}",
        f"- Area coverage fraction: {fmt(coverage) if coverage != '' else ''}",
        f"- Tier-0 area fraction: {fmt(frac) if frac != '' else ''}",
        f"- Strict reconstructed area window: [{scr1_row.get('area_lo', AREA_LO)}, {scr1_row.get('area_hi', AREA_HI)}]",
        f"- Area violation: {fmt(violation) if violation != '' else ''}",
        f"- Import fallback rows from manifest: {fallback}",
        f"- Import status counts: `{scr1_row.get('import_status_counts', '')}`",
        f"- Root-cause status: `{status}`",
        "",
        "## Supported Interpretation",
        "",
    ]

    if status == "reconstructed_area_infeasible":
        lines.extend(
            [
                "- The SCR1 native timing-aware baseline is present and has complete reconstructed OpenROAD-area coverage.",
                "- The imported native assignment is mildly outside the strict ASA reconstructed area-balance window.",
                "- This audit by itself supports the conservative claim that SCR1 is boundary evidence under the current paper-facing Phase-3 comparison.",
            ]
        )
    elif status == "reconstructed_area_feasible":
        lines.extend(
            [
                "- The SCR1 native timing-aware baseline is inside the strict reconstructed area-balance window under this audit.",
                "- If this is unexpected, inspect whether the area source or assignment import differs from earlier Phase-3 runs.",
            ]
        )
    elif status == "area_coverage_insufficient":
        lines.extend(
            [
                "- The audit cannot make a strong feasibility claim because assignment-to-area coverage is below 99%.",
                "- Resolve area matching before using SCR1 for the reviewer-response restoration experiment.",
            ]
        )
    else:
        lines.extend(
            [
                "- The available artifacts are insufficient for a strong root-cause claim.",
                "- Resolve missing or empty inputs before running restoration.",
            ]
        )

    lines.extend(
        [
            "",
            "## Not Proven From This Audit Alone",
            "",
            "- This audit does not prove the original TritonPart internal balance quantity.",
            "- It does not relax path guards or rewrite frozen paper snapshots.",
            "- It separates assignment-to-area coverage from assignment-import fallback provenance.",
            "- It only establishes whether the imported native assignment satisfies the reconstructed Phase-3 area window.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--design", action="append", choices=DESIGNS)
    parser.add_argument("--area-lo", type=float, default=AREA_LO)
    parser.add_argument("--area-hi", type=float, default=AREA_HI)
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path("results/benchmark_summary/native_baseline_feasibility_audit.csv"),
    )
    parser.add_argument(
        "--scr1-report",
        type=Path,
        default=Path("results/benchmark_summary/scr1_baseline_infeasibility_analysis.md"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    designs = args.design or list(DESIGNS)
    rows = [audit_design(design, root, args.area_lo, args.area_hi) for design in designs]

    fields = [
        "design",
        "native_assignment",
        "openroad_area",
        "native_timing_aware_completed",
        "assignment_instances",
        "matched_area_instances",
        "unmatched_area_instances",
        "ambiguous_area_instances",
        "area_coverage_fraction",
        "tier0_area",
        "tier1_area",
        "tier0_area_fraction",
        "area_lo",
        "area_hi",
        "area_violation",
        "reconstructed_area_pass",
        "true_import_fallback_rows",
        "import_manifest",
        "import_status_counts",
        "root_cause_status",
        "notes",
    ]
    summary_path = root / args.summary
    write_csv(summary_path, rows, fields)

    scr1 = next((row for row in rows if row["design"] == "scr1_core_tuned"), None)
    if scr1 is not None:
        write_scr1_report(root / args.scr1_report, scr1)

    print(summary_path)
    if scr1 is not None:
        print(root / args.scr1_report)
    for row in rows:
        print(
            "{design}: status={status} pass={passed} tier0_fraction={frac} coverage={coverage} fallback_rows={fallback}".format(
                design=row["design"],
                status=row["root_cause_status"],
                passed=fmt(row["reconstructed_area_pass"]),
                frac=fmt(row["tier0_area_fraction"]) if row["tier0_area_fraction"] != "" else "",
                coverage=fmt(row["area_coverage_fraction"]) if row["area_coverage_fraction"] != "" else "",
                fallback=fmt(row.get("true_import_fallback_rows", "")),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
