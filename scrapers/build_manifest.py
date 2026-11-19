#!/usr/bin/env python3
"""Build the reproducible sampling manifests (run once; the committed files are the reference).

1. Snapshot: page through the Internet Archive pool query (Scrape API, identifier + light metadata)
   and save data/manifest/pool_snapshot_<date>.csv.gz (+ SHA-256 in manifest_meta.json).
2. Order: every eligible item is sorted by sha256("<seed>:<identifier>") - same order on any machine.
3. Walk that order in chunks, asking the official Views API whether each item has view data, and keep:
     - training list: first 2,000 items with data, at most 3 per work_group
     - benchmark list: first 200 of those that start a new work_group (so 200 distinct works)
   The benchmark is therefore a random subset of the training list.
4. Write the ID lists, every exclusion with its reason, and the views eligibility check.

Usage:  python scrapers/build_manifest.py                      (downloads a fresh snapshot, ~6 slow requests)
        python scrapers/build_manifest.py --reuse-snapshot data/manifest/pool_snapshot_<date>.csv.gz
"""
import argparse
import csv
import gzip
import io
import json
import sys
from pathlib import Path

import config
from ia_common import (Client, Run, clean, dump_json, iso, order_key, sha256_file, unique, work_group,
                       write_flat_csv)

SNAPSHOT_COLUMNS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language"]


def fetch_snapshot(client):
    items, cursor, total = [], None, None
    while True:
        params = {"q": config.POOL_QUERY, "fields": ",".join(config.SNAPSHOT_FIELDS), "count": 5000}
        if cursor:
            params["cursor"] = cursor
        data = client.get(config.SCRAPE_URL, params=params, context={"call": "scrape", "have": len(items)}).json()
        items += data.get("items", [])
        total = data.get("total") if total is None else total      # first response = size of the whole result set
        cursor = data.get("cursor")
        print(f"  snapshot: {len(items)} / {total}", flush=True)
        if not cursor:
            return items, total


def write_snapshot(path, items):
    rows = []
    for it in sorted(items, key=lambda x: x["identifier"]):
        rows.append({
            "identifier": it["identifier"], "title": clean(it.get("title", "")),
            "creator": config.LIST_SEPARATOR.join(unique(it.get("creator"))),
            "year": it.get("year", ""), "imagecount": it.get("imagecount", ""),
            "addeddate": it.get("addeddate", ""), "language": ",".join(unique(it.get("language"))),
        })
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=SNAPSHOT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def read_snapshot(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def metadata_problem(row):
    """Reason string when a snapshot row cannot be used, else None."""
    for field, label in (("title", "title"), ("creator", "creator"), ("year", "year"),
                         ("imagecount", "imagecount"), ("addeddate", "addeddate")):
        if not clean(row.get(field, "")):
            return f"missing {label}"
    try:
        year, pages = int(float(row["year"])), int(float(row["imagecount"]))
    except ValueError:
        return "year/imagecount not numeric"
    if not (config.YEAR_MIN <= year <= config.YEAR_MAX):
        return "year outside range"
    if not (config.IMAGECOUNT_MIN <= pages <= config.IMAGECOUNT_MAX):
        return "imagecount outside range"
    if "eng" not in row.get("language", "").split(","):
        return "language does not include eng"
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=str(config.MANIFEST_DIR))
    parser.add_argument("--reuse-snapshot", help="use this pool_snapshot_*.csv.gz instead of downloading")
    parser.add_argument("--reported-total", type=int,
                        help="with --reuse-snapshot: total the Scrape API reported when it was downloaded")
    args = parser.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    run = Run("manifest", run_dir=out / "build_log")
    client = Client(run)
    created = iso()

    if args.reuse_snapshot:
        snap_path = Path(args.reuse_snapshot)
        total_reported = args.reported_total
        rows = read_snapshot(snap_path)
    else:
        items, total_reported = fetch_snapshot(client)
        snap_path = out / f"pool_snapshot_{created[:10].replace('-', '')}.csv.gz"
        write_snapshot(snap_path, items)
        rows = read_snapshot(snap_path)
    print(f"snapshot rows: {len(rows)} (reported total {total_reported})", flush=True)

    exclusions, eligible, seen = [], [], set()
    reason_counts = {}
    for row in rows:
        ident = row["identifier"]
        problem = "duplicate identifier" if ident in seen else metadata_problem(row)
        seen.add(ident)
        if problem:
            reason_counts[problem] = reason_counts.get(problem, 0) + 1
            exclusions.append({"identifier": ident, "stage": "metadata", "reason": problem, "detail": ""})
            continue
        creators = [c for c in row["creator"].split(config.LIST_SEPARATOR) if c]
        eligible.append({**row, "work_group": work_group(row["title"], creators), "key": order_key(ident)})
    eligible.sort(key=lambda r: r["key"])
    print(f"eligible by metadata: {len(eligible)}; excluded: {reason_counts}", flush=True)

    training, benchmark, bench_groups, group_count = [], [], set(), {}
    checks, examined = [], 0
    chunk = config.VIEWS_CHECK_BATCH
    for start in range(0, len(eligible), chunk):
        if len(training) >= config.TRAINING_TARGET:
            break
        batch = eligible[start:start + chunk]
        resp = client.get(config.VIEWS_URL + ",".join(r["identifier"] for r in batch),
                          context={"call": "views_check", "start": start})
        views = resp.json()
        checked_at = iso()
        for rank, r in enumerate(batch, start + 1):
            if len(training) >= config.TRAINING_TARGET:
                break
            examined += 1
            ident, grp = r["identifier"], r["work_group"]
            info = views.get(ident) or {}
            have = bool(info.get("have_data"))
            decision = ""
            if group_count.get(grp, 0) >= config.TRAINING_GROUP_CAP:
                decision = "excluded: group cap"
                exclusions.append({"identifier": ident, "stage": "group_cap", "reason": "more than "
                                   f"{config.TRAINING_GROUP_CAP} items in work_group", "detail": grp})
            elif not have:
                decision = "excluded: views have_data=false"
                exclusions.append({"identifier": ident, "stage": "views_check",
                                   "reason": "views API has no data", "detail": ""})
            else:
                group_count[grp] = group_count.get(grp, 0) + 1
                entry = {"identifier": ident, "work_group": grp, "stream_rank": rank}
                in_bench = len(benchmark) < config.BENCHMARK_SIZE and grp not in bench_groups
                if in_bench:
                    bench_groups.add(grp)
                    benchmark.append({"identifier": ident, "position": len(benchmark) + 1, **{k: entry[k] for k in ("work_group", "stream_rank")}})
                training.append({"identifier": ident, "position": len(training) + 1, "in_benchmark": in_bench,
                                 "work_group": grp, "stream_rank": rank})
                decision = "accepted" + (" +benchmark" if in_bench else "")
            checks.append({"identifier": ident, "stream_rank": rank, "work_group": grp, "have_data": have,
                           "views_all_time_at_check": info.get("all_time") if have else "",
                           "checked_at_utc": checked_at, "decision": decision})
        print(f"  checked {examined}; training {len(training)}, benchmark {len(benchmark)}", flush=True)

    meta = {
        "created_at_utc": created, "source": "Internet Archive (archive.org)", "pool_query": config.POOL_QUERY,
        "scrape_api_reported_total": total_reported, "snapshot_file": snap_path.name,
        "snapshot_sha256": sha256_file(snap_path), "snapshot_rows": len(rows),
        "ordering": f'sha256("{config.SEED}:<identifier>") ascending', "seed": config.SEED,
        "metadata_exclusion_counts": reason_counts, "eligible_after_metadata": len(eligible),
        "stream_items_examined": examined,
        "group_cap_exclusions": sum(1 for e in exclusions if e["stage"] == "group_cap"),
        "no_views_data_exclusions": sum(1 for e in exclusions if e["stage"] == "views_check"),
        "benchmark_size": len(benchmark), "training_size": len(training),
        "benchmark_group_cap": config.BENCHMARK_GROUP_CAP, "training_group_cap": config.TRAINING_GROUP_CAP,
        "distinct_work_groups_training": len({t["work_group"] for t in training}),
        "views_check_note": "have_data was checked once at created_at_utc; scrapers re-fetch everything later.",
        "work_group_rule": "main title (before ' : ' ' ; ' ' / '), volume/part/edition markers removed, normalised, "
                           "+ first creator's surname",
    }
    dump_json(out / "benchmark_200_ids.json", {"meta": meta, "ids": benchmark})
    dump_json(out / "random_fiction_training_ids_SUPERSEDED.json", {"meta": meta, "ids": training})
    dump_json(out / "manifest_meta.json", meta)
    write_flat_csv(out / "exclusions.csv", exclusions)
    write_flat_csv(out / "eligibility_views_check.csv", checks)
    run.finish([], None)
    print(json.dumps({k: meta[k] for k in ("snapshot_rows", "eligible_after_metadata", "stream_items_examined",
                                            "group_cap_exclusions", "no_views_data_exclusions", "benchmark_size",
                                            "training_size")}, indent=1))
    if len(benchmark) < config.BENCHMARK_SIZE or len(training) < config.TRAINING_TARGET:
        print("WARNING: fewer items than the targets were found")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
