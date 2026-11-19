#!/usr/bin/env python3
"""Assemble the final CSVs from the finished collection runs and write the completeness report.

Reads the run folders (never the web), writes:
  data/benchmark_200_{api,bs4,selenium}.csv   one row per manifest id, as collected (failures kept)
  data/training_api.csv                        usable API rows (status ok) + work_group / in_benchmark
  data/training_api_not_usable.csv             API rows that were partial/failed, with the reason
  data/benchmark_200_comparison/               field/views differences between the three methods
  data/completeness_report.md / .json          counts, completeness, ranges, consistency checks
  data/checksums.sha256

Usage:
  python scrapers/finalize_datasets.py --api RUN --bs4 RUN --selenium RUN --training RUN
"""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path

import config
import genres
from ia_common import read_csv, write_records_csv

TRAIN_FIELDS = config.DATA_FIELDS + [
    "sampling_stratum", "genre_primary", "genre_science_fiction", "genre_fantasy", "genre_mystery_thriller",
    "work_group", "in_benchmark"] + config.PROVENANCE_FIELDS


def load_run(path):
    path = Path(path)
    records = {}
    for line in (path / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            records[row["identifier"]] = row
    return records, json.loads((path / "run.json").read_text(encoding="utf-8"))


def field_completeness(rows, fields):
    out = {}
    for f in fields:
        out[f] = sum(1 for r in rows if r.get(f) not in (None, "", []))
    return out


def describe(values):
    values = sorted(values)
    if not values:
        return None
    return {"min": values[0], "median": statistics.median(values), "max": values[-1],
            "mean": round(statistics.mean(values), 2)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--api", required=True)
    p.add_argument("--bs4", required=True)
    p.add_argument("--selenium", required=True)
    p.add_argument("--training", required=True)
    args = p.parse_args(argv)
    data = config.DATA_DIR
    manifest = json.loads((config.MANIFEST_DIR / "benchmark_200_ids.json").read_text(encoding="utf-8"))
    training_manifest = json.loads((config.MANIFEST_DIR / "training_ids.json").read_text(encoding="utf-8"))
    bench_ids = [x["identifier"] for x in manifest["ids"]]
    report = {"manifest": {k: manifest["meta"][k] for k in (
        "created_at_utc", "pool_query", "snapshot_file", "snapshot_sha256", "snapshot_rows", "seed")},
        "benchmark": {}, "training": {}}

    # ---- benchmark CSVs
    for method in ("api", "bs4", "selenium"):
        records, run_json = load_run(getattr(args, method))
        rows = [records[i] for i in bench_ids if i in records]
        write_records_csv(data / f"benchmark_200_{method}.csv", rows)
        status = {}
        for r in rows:
            status[r["status"]] = status.get(r["status"], 0) + 1
        report["benchmark"][method] = {
            "run_folder": Path(getattr(args, method)).name, "rows": len(rows),
            "unique_ids": len({r["identifier"] for r in rows}),
            "ids_missing_from_run": [i for i in bench_ids if i not in records],
            "status_counts": status,
            "field_non_empty": field_completeness(rows, config.DATA_FIELDS),
            "zero_view_rows": sum(1 for r in rows if r.get("views_all_time") == 0),
            "attempts_logged": run_json["attempts_logged_total"], "retry_attempts": run_json["retry_attempts_total"],
            "collection_timing_pilot_only": run_json["segments"],
        }
    # ---- comparison of the three
    cmp_dir = data / "benchmark_200_comparison"
    subprocess.run([sys.executable, str(Path(__file__).with_name("compare_runs.py")),
                    "--api", str(data / "benchmark_200_api.csv"), "--bs4", str(data / "benchmark_200_bs4.csv"),
                    "--selenium", str(data / "benchmark_200_selenium.csv"),
                    "--manifest", str(config.MANIFEST_DIR / "benchmark_200_ids.json"),
                    "--out-dir", str(cmp_dir)], check=True, stdout=subprocess.DEVNULL)
    report["benchmark_comparison"] = json.loads((cmp_dir / "comparison_summary.json").read_text(encoding="utf-8"))
    report["benchmark_comparison"]["views_differences"] = f"{len(report['benchmark_comparison']['views_differences'])} ids, see views_differences.csv"

    # ---- training CSV
    records, run_json = load_run(args.training)
    meta_by_id = {x["identifier"]: x for x in training_manifest["ids"]}
    usable, unusable = [], []
    for ident in (x["identifier"] for x in training_manifest["ids"]):
        row = records.get(ident)
        if row is None:
            unusable.append({"identifier": ident, "status": "not collected", "error": "no record in run"})
            continue
        flags = genres.genre_flags(row.get("subjects") or [])
        row = {**row, "work_group": meta_by_id[ident]["work_group"], "in_benchmark": meta_by_id[ident]["in_benchmark"],
               "sampling_stratum": meta_by_id[ident]["stratum"],
               "genre_primary": genres.primary_genre(flags) or "none",
               "genre_science_fiction": flags["science_fiction"], "genre_fantasy": flags["fantasy"],
               "genre_mystery_thriller": flags["mystery_thriller"]}
        (usable if row["status"] == "ok" else unusable).append(row)
    write_records_csv(data / "training_api.csv", usable, TRAIN_FIELDS)
    write_records_csv(data / "training_api_not_usable.csv", unusable, TRAIN_FIELDS)
    views = [r["views_all_time"] for r in usable]
    report["training"] = {
        "run_folder": Path(args.training).name, "ids_in_manifest": len(training_manifest["ids"]),
        "usable_rows": len(usable), "not_usable_rows": len(unusable),
        "duplicate_identifiers": len(usable) - len({r["identifier"] for r in usable}),
        "distinct_work_groups": len({r["work_group"] for r in usable}),
        "max_items_per_work_group": max((sum(1 for r in usable if r["work_group"] == g)
                                         for g in {r["work_group"] for r in usable}), default=0),
        "benchmark_ids_in_training_csv": sum(1 for r in usable if r["in_benchmark"]),
        "field_non_empty": field_completeness(usable, config.DATA_FIELDS),
        "zero_view_rows_kept": sum(1 for v in views if v == 0),
        "views_all_time": describe(views), "publication_year": describe([r["publication_year"] for r in usable]),
        "scanned_page_count": describe([r["scanned_page_count"] for r in usable]),
        "views_snapshot_window_utc": [min(r["retrieved_at_utc"] for r in usable),
                                      max(r["retrieved_at_utc"] for r in usable)] if usable else None,
        "collection_timing_pilot_only": run_json["segments"],
        "exclusions_before_collection": {k: manifest["meta"][k] for k in (
            "metadata_exclusion_counts", "group_cap_exclusions", "no_views_data_exclusions",
            "stream_items_examined")},
    }
    # benchmark ids that are ok in training CSV vs API benchmark: consistency of the same ids/different runs
    api_bench = {r["identifier"]: r for r in read_csv(data / "benchmark_200_api.csv")}
    drift = []
    for r in usable:
        b = api_bench.get(r["identifier"])
        if b and str(b["views_all_time"]) != str(r["views_all_time"]):
            drift.append({"identifier": r["identifier"], "benchmark_api_views": b["views_all_time"],
                          "training_api_views": r["views_all_time"]})
    report["training"]["benchmark_api_vs_training_api_views_changed"] = drift
    # ---- strata, genre consistency and engagement coverage (low / medium / high)
    t = report["training"]
    strata = ["benchmark_random_fiction"] + genres.GENRE_ORDER
    t["rows_per_stratum"] = {s: sum(1 for r in usable if r["sampling_stratum"] == s) for s in strata}
    t["manifest_ids_per_stratum"] = dict(training_manifest["meta"]["accepted_per_stratum"])
    usable_by_id = {r["identifier"]: r for r in usable}
    t["genre_rule_mismatch_vs_manifest"] = sum(
        1 for x in training_manifest["ids"]
        if x.get("genre_flags") and x["identifier"] in usable_by_id
        and x["genre_flags"] != {g: usable_by_id[x["identifier"]][f"genre_{g}"] for g in genres.GENRE_ORDER})
    t["rows_matching_several_genres"] = sum(1 for r in usable if sum(
        [r["genre_science_fiction"], r["genre_fantasy"], r["genre_mystery_thriller"]]) > 1)
    srt = sorted(views)
    pct = lambda q: srt[min(len(srt) - 1, int(q * len(srt)))] if srt else None
    t["views_percentiles"] = {f"p{int(q * 100)}": pct(q) for q in (0.1, 0.25, 1 / 3, 0.5, 2 / 3, 0.75, 0.9, 0.99)}
    lo, hi = pct(1 / 3), pct(2 / 3)
    t["tercile_cutoffs_all_rows"] = {"low_max": lo, "high_min": hi}
    bins = [("0", lambda v: v == 0), ("1-9", lambda v: 1 <= v <= 9), ("10-99", lambda v: 10 <= v <= 99),
            ("100-999", lambda v: 100 <= v <= 999), ("1000-9999", lambda v: 1000 <= v <= 9999),
            ("10000+", lambda v: v >= 10000)]
    t["views_bins_by_stratum"] = {
        s: {name: sum(1 for r in usable if r["sampling_stratum"] == s and f(r["views_all_time"])) for name, f in bins}
        for s in t["rows_per_stratum"]}
    t["tercile_share_by_stratum"] = {
        s: {"low": sum(1 for r in usable if r["sampling_stratum"] == s and r["views_all_time"] <= lo),
            "medium": sum(1 for r in usable if r["sampling_stratum"] == s and lo < r["views_all_time"] < hi),
            "high": sum(1 for r in usable if r["sampling_stratum"] == s and r["views_all_time"] >= hi)}
        for s in t["rows_per_stratum"]}
    (data / "completeness_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- markdown report
    L = ["# Completeness report", "", f"Pool query: `{report['manifest']['pool_query']}`  ",
         f"Snapshot: `{report['manifest']['snapshot_file']}` ({report['manifest']['snapshot_rows']} rows, sha256 "
         f"`{report['manifest']['snapshot_sha256'][:16]}…`), seed {report['manifest']['seed']}.", "",
         "## Benchmark (200 manifest ids)", "",
         "| Method | rows | ok | partial | failed | zero-view rows | retries |", "|---|---:|---:|---:|---:|---:|---:|"]
    for m, b in report["benchmark"].items():
        s = b["status_counts"]
        L.append(f"| {m} | {b['rows']} | {s.get('ok', 0)} | {s.get('partial', 0)} | {s.get('failed', 0)} | "
                 f"{b['zero_view_rows']} | {b['retry_attempts']} |")
    L += ["", "Per-field filled cells (of 200):", "", "| Field | api | bs4 | selenium |", "|---|---:|---:|---:|"]
    for f in config.DATA_FIELDS:
        L.append(f"| {f} | " + " | ".join(str(report["benchmark"][m]["field_non_empty"][f]) for m in ("api", "bs4", "selenium")) + " |")
    cmpf = report["benchmark_comparison"]["fields"]
    L += ["", "Field agreement between the three methods (rows complete in all three):", "",
          "| Field | compared | equal | differ | missing in a method |", "|---|---:|---:|---:|---:|"]
    for f, s in cmpf.items():
        L.append(f"| {f} | {s['compared']} | {s['equal']} | {s['differ']} | {s['missing_in_a_method']} |")
    t = report["training"]
    L += ["", "## Training set (API)", "",
          f"- usable rows (status ok): **{t['usable_rows']}** of {t['ids_in_manifest']} manifest ids; not usable: {t['not_usable_rows']}",
          f"- distinct work groups: {t['distinct_work_groups']} (max {t['max_items_per_work_group']} items per group)",
          f"- benchmark ids inside the training CSV: {t['benchmark_ids_in_training_csv']}",
          f"- genuine zero-view rows kept: {t['zero_view_rows_kept']}",
          f"- views_all_time: {t['views_all_time']}", f"- publication_year: {t['publication_year']}",
          f"- scanned_page_count: {t['scanned_page_count']}",
          f"- views snapshot window (UTC): {t['views_snapshot_window_utc']}",
          f"- benchmark ids whose API views changed between the benchmark run and the training run: "
          f"{len(drift)}",
          f"- usable rows per sampling stratum: {t['rows_per_stratum']} (manifest: {t['manifest_ids_per_stratum']})",
          f"- rows matching more than one genre rule: {t['rows_matching_several_genres']}; "
          f"genre flags differing from the manifest: {t['genre_rule_mismatch_vs_manifest']}",
          f"- views percentiles (all usable rows): {t['views_percentiles']}",
          f"- tercile cut-offs of all rows: low <= {t['tercile_cutoffs_all_rows']['low_max']}, "
          f"high >= {t['tercile_cutoffs_all_rows']['high_min']} (illustration only; thresholds must be fitted on the training split)",
          "", "Rows per views range and stratum:", "",
          "| Stratum | " + " | ".join(next(iter(t["views_bins_by_stratum"].values())).keys()) + " |",
          "|---|" + "---:|" * len(next(iter(t["views_bins_by_stratum"].values())))]
    for s, b in t["views_bins_by_stratum"].items():
        L.append(f"| {s} | " + " | ".join(str(v) for v in b.values()) + " |")
    L += ["", "Share of each stratum in the low / medium / high terciles of all rows:", "",
          "| Stratum | low | medium | high |", "|---|---:|---:|---:|"]
    for s, b in t["tercile_share_by_stratum"].items():
        L.append(f"| {s} | {b['low']} | {b['medium']} | {b['high']} |")
    L += ["",
          "Timings in the run folders are pilot/collection timings (including deliberate waits); the final network "
          "comparison is produced separately by re-running the scrapers under packet capture.", ""]
    (data / "completeness_report.md").write_text("\n".join(L), encoding="utf-8")

    # ---- checksums
    names = [f"benchmark_200_{m}.csv" for m in ("api", "bs4", "selenium")] + ["training_api.csv", "training_api_not_usable.csv"]
    with open(data / "checksums.sha256", "w", encoding="utf-8", newline="\n") as f:
        for n in names:
            f.write(f"{hashlib.sha256((data / n).read_bytes()).hexdigest()}  {n}\n")
    print("\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())
