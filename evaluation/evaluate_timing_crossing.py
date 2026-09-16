#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path

def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def load_assignment(path):
    rows = read_csv(path)
    return {r["instance"]: r["tier"] for r in rows}

def load_timing(path):
    rows = read_csv(path)
    return {
        r["instance"]: {
            "score": float(r.get("timing_context_score", 0) or 0),
            "max_count": int(r.get("max_path_count", 0) or 0),
            "min_count": int(r.get("min_path_count", 0) or 0),
            "unit": r.get("architecture_unit", "unclassified"),
        }
        for r in rows
    }

def load_nets(features_dir):
    rows = read_csv(Path(features_dir) / "instance_features.csv")
    net_to_instances = defaultdict(list)
    for r in rows:
        inst = r.get("instance", "").strip()
        raw_nets = r.get("nets", "")
        if not inst or not raw_nets:
            continue
        for net in raw_nets.replace(";", " ").split():
            net = net.strip()
            if net:
                net_to_instances[net].append(inst)
    return [(net, sorted(set(insts))) for net, insts in net_to_instances.items()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", required=True)
    ap.add_argument("--features-dir", required=True)
    ap.add_argument("--timing", required=True)
    ap.add_argument("--assignment", action="append", required=True, help="case=path")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    timing = load_timing(args.timing)
    nets = load_nets(args.features_dir)

    out_rows = []
    for spec in args.assignment:
        case, path = spec.split("=", 1)
        assignment = load_assignment(path)

        crossing_nets = 0
        timing_crossing_nets = 0
        timing_weighted_crossing = 0.0
        high_timing_crossing_nets = 0
        unit_hits = defaultdict(int)

        for net, insts in nets:
            placed = [i for i in insts if i in assignment]
            tiers = {assignment[i] for i in placed}
            if len(tiers) < 2:
                continue

            crossing_nets += 1
            net_score = sum(timing.get(i, {}).get("score", 0.0) for i in placed)
            max_score = max([timing.get(i, {}).get("score", 0.0) for i in placed] or [0.0])
            if net_score > 0:
                timing_crossing_nets += 1
                timing_weighted_crossing += net_score
                for i in placed:
                    if timing.get(i, {}).get("score", 0.0) > 0:
                        unit_hits[timing[i]["unit"]] += 1
            if max_score >= 0.5:
                high_timing_crossing_nets += 1

        out_rows.append({
            "design": args.design,
            "case": case,
            "crossing_nets": crossing_nets,
            "timing_crossing_nets": timing_crossing_nets,
            "timing_crossing_net_fraction": f"{timing_crossing_nets / crossing_nets:.6f}" if crossing_nets else "0.000000",
            "high_timing_crossing_nets": high_timing_crossing_nets,
            "timing_weighted_crossing": f"{timing_weighted_crossing:.6f}",
            "top_timing_crossing_unit": max(unit_hits, key=unit_hits.get) if unit_hits else "",
            "top_timing_crossing_unit_hits": max(unit_hits.values()) if unit_hits else 0,
        })

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "design", "case", "crossing_nets", "timing_crossing_nets",
            "timing_crossing_net_fraction", "high_timing_crossing_nets",
            "timing_weighted_crossing", "top_timing_crossing_unit",
            "top_timing_crossing_unit_hits",
        ]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)
    print(out)

if __name__ == "__main__":
    main()
