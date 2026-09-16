#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

INSTANCE_COLUMNS = ("instance", "instance_name", "name")
ARCH_COLUMNS = ("architecture_unit", "architecture_class", "class")

def canon(name):
    return re.sub(r"[^A-Za-z0-9]+", "", name or "").lower()

def find_col(fields, candidates):
    if not fields:
        return None
    for c in candidates:
        if c in fields:
            return c
    return fields[0]

def read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_instances(features_dir):
    candidates = [
        features_dir / "architecture_mapping.csv",
        features_dir / "architecture_instance_classes.csv",
        features_dir / "instance_features.csv",
    ]
    rows = []
    for path in candidates:
        if path.exists():
            rows = read_rows(path)
            if rows:
                break
    if not rows:
        raise FileNotFoundError(f"No instance feature CSV found in {features_dir}")

    fields = list(rows[0].keys())
    inst_col = find_col(fields, INSTANCE_COLUMNS)
    arch_col = None
    for c in ARCH_COLUMNS:
        if c in fields:
            arch_col = c
            break

    instances = []
    arch = {}
    for row in rows:
        inst = row.get(inst_col, "").strip()
        if not inst:
            continue
        instances.append(inst)
        arch[inst] = row.get(arch_col, "unclassified").strip() if arch_col else "unclassified"

    return sorted(set(instances)), arch

def build_matcher(instances):
    exact = set(instances)
    by_canon = defaultdict(list)
    for inst in instances:
        by_canon[canon(inst)].append(inst)

    def match(token):
        token = token.strip().strip(",")
        token = token.lstrip("^v")
        if "/" in token:
            token = token.rsplit("/", 1)[0]
        token = token.strip()
        if token in exact:
            return token
        key = canon(token)
        vals = by_canon.get(key, [])
        if len(vals) == 1:
            return vals[0]
        return None

    return match

def parse_endpoint_name(line):
    m = re.match(r"^(Startpoint|Endpoint):\s+(.+?)(?:\s+\(|$)", line.strip())
    if not m:
        return None, None
    return m.group(1).lower(), m.group(2).strip()

def parse_slack(block):
    for line in reversed(block):
        m = re.search(r"([-+]?\d+(?:\.\d+)?)\s+slack\s+\(([^)]+)\)", line)
        if m:
            return float(m.group(1)), m.group(2)
    return None, None

def extract_candidates(block):
    candidates = []
    endpoint_roles = []
    for line in block:
        role, name = parse_endpoint_name(line)
        if name:
            candidates.append(name)
            endpoint_roles.append((role, name))
        for m in re.finditer(r"[\^v]?\s+(\S+/\S+)\s+\(", line):
            candidates.append(m.group(1))
    return candidates, endpoint_roles

def parse_report(path, delay_type, match_instance):
    paths = []
    current = []
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if raw.startswith("Startpoint:") and current:
            paths.append(current)
            current = [raw]
        elif raw.startswith("Startpoint:"):
            current = [raw]
        elif current:
            current.append(raw)
    if current:
        paths.append(current)

    events = []
    for idx, block in enumerate(paths, start=1):
        slack, status = parse_slack(block)
        if slack is None:
            continue

        if delay_type == "max":
            path_score = 1.0 + max(0.0, -slack) if slack < 0 else 1.0 / (1.0 + slack)
        else:
            path_score = 0.5 / (1.0 + max(slack, 0.0))

        candidates, endpoint_roles = extract_candidates(block)
        matched = []
        for token in candidates:
            inst = match_instance(token)
            if inst:
                matched.append(inst)

        role_matches = []
        for role, token in endpoint_roles:
            inst = match_instance(token)
            if inst:
                role_matches.append((role, inst))

        events.append({
            "path_index": idx,
            "delay_type": delay_type,
            "slack": slack,
            "status": status,
            "score": path_score,
            "instances": sorted(set(matched)),
            "roles": role_matches,
        })
    return events

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--features-dir", required=True)
    ap.add_argument("--timing-dir", default="results/timing_reports")
    ap.add_argument("--output-dir")
    args = ap.parse_args()

    features_dir = Path(args.features_dir)
    timing_dir = Path(args.timing_dir)
    output_dir = Path(args.output_dir) if args.output_dir else features_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    instances, arch = load_instances(features_dir)
    match_instance = build_matcher(instances)

    report_paths = {
        "max": timing_dir / f"{args.design}_report_checks_max.rpt",
        "min": timing_dir / f"{args.design}_report_checks_min.rpt",
    }
    for path in report_paths.values():
        if not path.exists():
            raise FileNotFoundError(path)

    stats = {
        inst: {
            "instance": inst,
            "architecture_unit": arch.get(inst, "unclassified"),
            "max_path_count": 0,
            "min_path_count": 0,
            "startpoint_count": 0,
            "endpoint_count": 0,
            "timing_raw_score": 0.0,
            "worst_max_slack": "",
            "worst_min_slack": "",
        }
        for inst in instances
    }

    all_events = []
    for delay_type, path in report_paths.items():
        events = parse_report(path, delay_type, match_instance)
        all_events.extend(events)
        for ev in events:
            for inst in ev["instances"]:
                if delay_type == "max":
                    stats[inst]["max_path_count"] += 1
                    stats[inst]["timing_raw_score"] += ev["score"]
                    old = stats[inst]["worst_max_slack"]
                    stats[inst]["worst_max_slack"] = ev["slack"] if old == "" else min(float(old), ev["slack"])
                else:
                    stats[inst]["min_path_count"] += 1
                    old = stats[inst]["worst_min_slack"]
                    stats[inst]["worst_min_slack"] = ev["slack"] if old == "" else min(float(old), ev["slack"])
            for role, inst in ev["roles"]:
                if role == "startpoint":
                    stats[inst]["startpoint_count"] += 1
                elif role == "endpoint":
                    stats[inst]["endpoint_count"] += 1

    max_raw = max((v["timing_raw_score"] for v in stats.values()), default=0.0)
    score_rows = []
    for inst in instances:
        row = stats[inst]
        norm = row["timing_raw_score"] / max_raw if max_raw > 0 else 0.0
        row["timing_context_score"] = f"{norm:.6f}"
        row["timing_raw_score"] = f"{row['timing_raw_score']:.6f}"
        for k in ("worst_max_slack", "worst_min_slack"):
            if row[k] != "":
                row[k] = f"{float(row[k]):.6f}"
        score_rows.append(row)

    score_path = output_dir / "timing_context_scores.csv"
    fields = [
        "instance", "architecture_unit",
        "max_path_count", "min_path_count",
        "startpoint_count", "endpoint_count",
        "worst_max_slack", "worst_min_slack",
        "timing_raw_score", "timing_context_score",
    ]
    with score_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(score_rows)

    by_unit = defaultdict(list)
    for row in score_rows:
        by_unit[row["architecture_unit"]].append(row)

    summary_rows = []
    for unit, rows in sorted(by_unit.items()):
        observed = [r for r in rows if int(r["max_path_count"]) or int(r["min_path_count"])]
        high = [r for r in rows if float(r["timing_context_score"]) >= 0.5]
        worst_values = [float(r["worst_max_slack"]) for r in rows if r["worst_max_slack"] != ""]
        summary_rows.append({
            "design": args.design,
            "architecture_unit": unit,
            "instance_count": len(rows),
            "timing_observed_instances": len(observed),
            "timing_observed_fraction": f"{len(observed) / len(rows):.6f}" if rows else "0.000000",
            "mean_timing_context_score": f"{sum(float(r['timing_context_score']) for r in rows) / len(rows):.6f}" if rows else "0.000000",
            "high_timing_context_instances": len(high),
            "worst_max_slack": f"{min(worst_values):.6f}" if worst_values else "",
            "total_max_path_mentions": sum(int(r["max_path_count"]) for r in rows),
            "total_min_path_mentions": sum(int(r["min_path_count"]) for r in rows),
        })

    summary_path = output_dir / "timing_context_summary.csv"
    sfields = [
        "design", "architecture_unit", "instance_count",
        "timing_observed_instances", "timing_observed_fraction",
        "mean_timing_context_score", "high_timing_context_instances",
        "worst_max_slack", "total_max_path_mentions", "total_min_path_mentions",
    ]
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=sfields)
        w.writeheader()
        w.writerows(summary_rows)

    manifest = {
        "design": args.design,
        "features_dir": str(features_dir),
        "timing_dir": str(timing_dir),
        "instance_count": len(instances),
        "max_report": str(report_paths["max"]),
        "min_report": str(report_paths["min"]),
        "parsed_path_count": len(all_events),
        "outputs": [score_path.name, summary_path.name],
    }
    manifest_path = output_dir / "timing_context_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(score_path)
    print(summary_path)
    print(manifest_path)

if __name__ == "__main__":
    main()
