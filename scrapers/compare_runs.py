#!/usr/bin/env python3
"""Compare the API, BS4 and Selenium CSVs of the same manifest, field by field (read-only, no web access).

Nothing is filled in: if a method has no value, that field is reported as missing, never copied
from another method. View-count differences are listed in full (they are an observed result).

Usage:
    python scrapers/compare_runs.py --api <api.csv> --bs4 <bs4.csv> --selenium <selenium.csv> --out-dir <folder>
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import config

COMPARE = ["title", "creators", "first_creator", "publication_year", "subjects", "language",
           "addeddate", "scanned_page_count", "views_all_time"]
METHODS = ["api", "bs4", "selenium"]


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return {r["identifier"]: r for r in csv.DictReader(f)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for m in METHODS:
        p.add_argument(f"--{m}", required=True)
    p.add_argument("--manifest", help="manifest JSON (to check all expected ids are present)")
    p.add_argument("--limit", type=int, help="only the first N manifest ids (validation runs)")
    p.add_argument("--out-dir", required=True)
    args = p.parse_args(argv)
    data = {m: read(getattr(args, m)) for m in METHODS}
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    expected = None
    if args.manifest:
        raw = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        expected = [x["identifier"] if isinstance(x, dict) else x for x in (raw["ids"] if isinstance(raw, dict) else raw)]
    if expected and args.limit:
        expected = expected[:args.limit]
    ids = expected or sorted(set().union(*[set(d) for d in data.values()]))

    summary = {"ids_expected": len(ids), "per_method": {}, "fields": {}, "views_differences": []}
    for m in METHODS:
        counts = {}
        for i in ids:
            s = data[m].get(i, {}).get("status", "absent")
            counts[s] = counts.get(s, 0) + 1
        summary["per_method"][m] = {"rows": len(data[m]), "status_counts": counts,
                                    "ids_not_in_csv": sum(1 for i in ids if i not in data[m]),
                                    "extra_ids_not_in_manifest": sum(1 for i in data[m] if i not in set(ids))}
    summary["ids_ok_in_all_three"] = sum(1 for i in ids if all(data[m].get(i, {}).get("status") == "ok" for m in METHODS))

    detail, views_rows = [], []
    for field in COMPARE:
        stats = {"compared": 0, "equal": 0, "differ": 0, "differ_same_items_other_order": 0, "missing_in_a_method": 0}
        for i in ids:
            vals = {m: (data[m].get(i, {}).get(field, "") if data[m].get(i, {}).get("status") != "failed" else "")
                    for m in METHODS}
            if any(v == "" for v in vals.values()):
                stats["missing_in_a_method"] += 1
                detail.append({"identifier": i, "field": field, **vals, "result": "missing in at least one method"})
                continue
            stats["compared"] += 1
            if len(set(vals.values())) == 1:
                stats["equal"] += 1
                continue
            same_items = field in ("creators", "subjects") and len({
                tuple(sorted(v.split(config.LIST_SEPARATOR))) for v in vals.values()}) == 1
            stats["differ_same_items_other_order" if same_items else "differ"] += 1
            detail.append({"identifier": i, "field": field, **vals,
                           "result": "same items, different order" if same_items else "values differ"})
            if field == "views_all_time":
                n = {m: int(v) for m, v in vals.items()}
                views_rows.append({"identifier": i, **n, "api_minus_bs4": n["api"] - n["bs4"],
                                   "api_minus_selenium": n["api"] - n["selenium"],
                                   "bs4_minus_selenium": n["bs4"] - n["selenium"]})
        summary["fields"][field] = stats
    summary["views_differences"] = views_rows

    def write(path, rows, fields):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    write(out / "field_differences.csv", detail, ["identifier", "field"] + METHODS + ["result"])
    write(out / "views_differences.csv", views_rows,
          ["identifier"] + METHODS + ["api_minus_bs4", "api_minus_selenium", "bs4_minus_selenium"])
    (out / "comparison_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [f"# Three-method comparison ({len(ids)} ids)", "",
             "| Method | rows | " + " | ".join(sorted({s for m in METHODS for s in summary['per_method'][m]['status_counts']})) + " |",
             ]
    statuses = sorted({s for m in METHODS for s in summary["per_method"][m]["status_counts"]})
    lines = [f"# Three-method comparison ({len(ids)} ids)", "",
             "| Method | rows in CSV | " + " | ".join(statuses) + " |", "|---|---:|" + "---:|" * len(statuses)]
    for m in METHODS:
        pm = summary["per_method"][m]
        lines.append(f"| {m} | {pm['rows']} | " + " | ".join(str(pm["status_counts"].get(s, 0)) for s in statuses) + " |")
    lines += ["", f"IDs with status ok in all three methods: **{summary['ids_ok_in_all_three']}**", "",
              "| Field | compared | equal | differ | same items other order | missing in a method |",
              "|---|---:|---:|---:|---:|---:|"]
    for field, s in summary["fields"].items():
        lines.append(f"| {field} | {s['compared']} | {s['equal']} | {s['differ']} | "
                     f"{s['differ_same_items_other_order']} | {s['missing_in_a_method']} |")
    if views_rows:
        lines += ["", f"View-count differences between methods: **{len(views_rows)}** ids (see views_differences.csv)."]
    (out / "comparison_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
