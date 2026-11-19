#!/usr/bin/env python3
"""Build the training manifest: the 200 benchmark books + ~600 books per genre (science fiction, fantasy, mystery/thriller).

Genre rules and exclusions: scrapers/genres.py. The benchmark manifest is never changed.

Step 1  --check-only   download the genre pool snapshot (Americana, same filters as the benchmark pool), apply the rules,
                       write data/manifest/genre_availability.json/.md and genre_preview.csv, then STOP.
Step 2  (default)      reuse that snapshot; for each genre in precedence order walk the pool in sha256 order (NOT sorted by views
                       or downloads), keep items for which the Views API has data (a genuine 0 counts), at most 3 per
                       work_group overall, until 600 per genre. Writes training_ids.json (benchmark first, then genres).

    python scrapers/build_training_manifest.py --check-only
    python scrapers/build_training_manifest.py --reuse-snapshot data/manifest/genre_pool_snapshot_<date>.csv.gz
"""
import argparse
import csv
import gzip
import io
import json
import sys
from collections import Counter
from pathlib import Path

import config
import genres
from build_manifest import metadata_problem
from ia_common import Client, Run, clean, dump_json, iso, order_key, sha256_file, unique, work_group, write_flat_csv

PER_GENRE = 600
COLUMNS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language", "subject"]
FIELDS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language", "subject"]
BASE = (f"mediatype:texts AND language:eng AND creator:* AND year:[{config.YEAR_MIN} TO {config.YEAR_MAX}] "
        f"AND imagecount:[{config.IMAGECOUNT_MIN} TO {config.IMAGECOUNT_MAX}]")
GENRE_CLAUSE = ('(subject:"science fiction" OR subject:fantasy OR subject:("detective and mystery stories" OR '
                '"mystery fiction" OR "detective fiction" OR thriller OR thrillers OR "suspense fiction" OR '
                '"spy stories" OR "crime fiction"))')
POOL_QUERY = f"collection:{config.POOL_COLLECTION} AND {BASE} AND {GENRE_CLAUSE}"


def fetch(client):
    items, cursor, total = [], None, None
    while True:
        params = {"q": POOL_QUERY, "fields": ",".join(FIELDS), "count": 5000}
        if cursor:
            params["cursor"] = cursor
        data = client.get(config.SCRAPE_URL, params=params, context={"call": "genre_scrape", "have": len(items)}).json()
        items += data.get("items", [])
        total = data.get("total") if total is None else total
        cursor = data.get("cursor")
        print(f"  genre snapshot: {len(items)} / {total}", flush=True)
        if not cursor:
            return items, total


def write_snapshot(path, items):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    for it in sorted(items, key=lambda x: x["identifier"]):
        w.writerow({"identifier": it["identifier"], "title": clean(it.get("title", "")),
                    "creator": config.LIST_SEPARATOR.join(unique(it.get("creator"))),
                    "year": it.get("year", ""), "imagecount": it.get("imagecount", ""),
                    "addeddate": it.get("addeddate", ""), "language": ",".join(unique(it.get("language"))),
                    "subject": config.LIST_SEPARATOR.join(unique(it.get("subject")))})
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def classify(rows, bench):
    """Apply metadata checks, benchmark/duplicate exclusion, genre rules and non-fiction rules."""
    exclusions, candidates, seen = [], [], set()
    for row in rows:
        ident = row["identifier"]
        subjects = [s for s in row["subject"].split(config.LIST_SEPARATOR) if s]
        creators = [c for c in row["creator"].split(config.LIST_SEPARATOR) if c]
        flags = genres.genre_flags(subjects)
        primary = genres.primary_genre(flags)

        def drop(stage, reason):
            exclusions.append({"identifier": ident, "stage": stage, "reason": reason, "primary_genre": primary or "",
                               "title": row["title"][:80]})
        if ident in seen:
            drop("duplicate", "duplicate identifier")
            continue
        seen.add(ident)
        if ident in bench:
            drop("benchmark", "already one of the 200 benchmark books")
            continue
        if primary is None:
            drop("genre_rule", "no genre rule matched the subject tags")
            continue
        problem = metadata_problem(row)
        if problem:
            drop("metadata", problem)
            continue
        reason = genres.nonfiction_reason(row["title"], subjects)
        if reason:
            drop("nonfiction_rule", reason)
            continue
        candidates.append({**row, "subjects_list": subjects, "flags": flags, "primary_genre": primary,
                           "work_group": work_group(row["title"], creators), "key": order_key(ident)})
    return candidates, exclusions


def availability(rows, candidates, exclusions, bench_groups):
    raw_flags = Counter()
    for row in rows:
        f = genres.genre_flags([s for s in row["subject"].split(config.LIST_SEPARATOR) if s])
        for g in genres.GENRE_ORDER:
            raw_flags[g] += f[g]
    out = {"pool_query": POOL_QUERY, "snapshot_rows": len(rows), "per_genre_target": PER_GENRE, "genres": {}}
    for g in genres.GENRE_ORDER:
        cands = [c for c in candidates if c["primary_genre"] == g]
        counts = Counter(c["work_group"] for c in cands)
        capped = sum(min(n, config.TRAINING_GROUP_CAP) for n in counts.values())
        excl = Counter(e["stage"] for e in exclusions if e["primary_genre"] == g)
        out["genres"][g] = {
            "rows_matching_rule_any_priority": raw_flags[g],
            "assigned_primary_rows_after_rules": len(cands) + sum(excl.values()),
            "excluded_by_stage": dict(excl),
            "candidates_after_all_rules": len(cands), "distinct_work_groups": len(counts),
            "candidates_after_group_cap_3_estimate": capped,
            "before_views_check_enough": capped >= PER_GENRE,
        }
    out["overlap_rows"] = {
        "science_fiction+fantasy": sum(1 for c in candidates if c["flags"]["science_fiction"] and c["flags"]["fantasy"]),
        "science_fiction+mystery_thriller": sum(1 for c in candidates if c["flags"]["science_fiction"] and c["flags"]["mystery_thriller"]),
        "fantasy+mystery_thriller": sum(1 for c in candidates if c["flags"]["fantasy"] and c["flags"]["mystery_thriller"]),
        "all_three": sum(1 for c in candidates if all(c["flags"].values())),
    }
    out["exclusion_reasons_top"] = Counter(e["reason"].split("'")[0] + (e["reason"].split("'")[-2] if "'" in e["reason"] else "")
                                            for e in exclusions if e["stage"] == "nonfiction_rule").most_common(12)
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", default=str(config.MANIFEST_DIR))
    p.add_argument("--check-only", action="store_true", help="availability + preview only, then stop")
    p.add_argument("--reuse-snapshot", help="genre_pool_snapshot_*.csv.gz to use instead of downloading")
    p.add_argument("--reported-total", type=int)
    args = p.parse_args(argv)
    out = Path(args.out_dir)
    run = Run("training_manifest", run_dir=out / "training_build_log")
    client = Client(run)
    created = iso()
    bench_manifest = json.loads((out / "benchmark_200_ids.json").read_text(encoding="utf-8"))
    bench = {x["identifier"]: x for x in bench_manifest["ids"]}

    if args.reuse_snapshot:
        snap, total = Path(args.reuse_snapshot), args.reported_total
    else:
        items, total = fetch(client)
        snap = out / f"genre_pool_snapshot_{created[:10].replace('-', '')}.csv.gz"
        write_snapshot(snap, items)
    with gzip.open(snap, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    candidates, exclusions = classify(rows, bench)
    bench_groups = {x["work_group"] for x in bench.values()}
    avail = availability(rows, candidates, exclusions, bench_groups)
    avail.update({"created_at_utc": created, "snapshot_file": snap.name, "snapshot_sha256": sha256_file(snap),
                  "scrape_api_reported_total": total})
    dump_json(out / "genre_availability.json", avail)
    write_flat_csv(out / "genre_exclusions.csv", exclusions)

    preview = []
    for g in genres.GENRE_ORDER:
        for c in sorted([c for c in candidates if c["primary_genre"] == g], key=lambda c: c["key"])[:6]:
            preview.append({"genre": g, "identifier": c["identifier"], "title": c["title"][:90],
                            "creator": c["creator"][:50], "year": c["year"], "imagecount": c["imagecount"],
                            "also_matches": ",".join(x for x in genres.GENRE_ORDER if c["flags"][x] and x != g),
                            "subjects": c["subject"][:110]})
    write_flat_csv(out / "genre_preview.csv", preview)
    print(json.dumps({k: avail[k] for k in ("snapshot_rows", "overlap_rows", "genres")}, indent=1))
    if args.check_only:
        return 0

    # ---- selection (Views API has data; random hash order; shared group cap)
    group_count = Counter(x["work_group"] for x in bench.values())
    training = [{"identifier": i, "position": n, "stratum": "benchmark_random_fiction", "in_benchmark": True,
                 "work_group": x["work_group"], "stream_rank": x["stream_rank"]}
                for n, (i, x) in enumerate(bench.items(), 1)]
    checks, shortage = [], {}
    for g in genres.GENRE_ORDER:
        pool = sorted([c for c in candidates if c["primary_genre"] == g], key=lambda c: c["key"])
        accepted, examined = 0, 0
        for start in range(0, len(pool), config.VIEWS_CHECK_BATCH):
            if accepted >= PER_GENRE:
                break
            batch = pool[start:start + config.VIEWS_CHECK_BATCH]
            views = client.get(config.VIEWS_URL + ",".join(c["identifier"] for c in batch),
                               context={"call": "views_check", "genre": g, "start": start}).json()
            stamp = iso()
            for rank, c in enumerate(batch, start + 1):
                if accepted >= PER_GENRE:
                    break
                examined += 1
                info = views.get(c["identifier"]) or {}
                have = bool(info.get("have_data"))
                if group_count[c["work_group"]] >= config.TRAINING_GROUP_CAP:
                    decision = "excluded: group cap"
                    exclusions.append({"identifier": c["identifier"], "stage": "group_cap", "reason": "work_group already has 3 items",
                                       "primary_genre": g, "title": c["title"][:80]})
                elif not have:
                    decision = "excluded: views have_data=false"
                    exclusions.append({"identifier": c["identifier"], "stage": "views_check", "reason": "views API has no data",
                                       "primary_genre": g, "title": c["title"][:80]})
                else:
                    group_count[c["work_group"]] += 1
                    accepted += 1
                    training.append({"identifier": c["identifier"], "position": len(training) + 1, "stratum": g,
                                     "in_benchmark": False, "work_group": c["work_group"], "stream_rank": rank,
                                     "genre_flags": c["flags"]})
                    decision = "accepted"
                checks.append({"identifier": c["identifier"], "genre": g, "pool_rank": rank, "have_data": have,
                               "views_all_time_at_check": info.get("all_time") if have else "",
                               "checked_at_utc": stamp, "decision": decision})
            print(f"  {g}: examined {examined}, accepted {accepted}", flush=True)
        if accepted < PER_GENRE:
            shortage[g] = {"accepted": accepted, "wanted": PER_GENRE}
    write_flat_csv(out / "genre_exclusions.csv", exclusions)
    write_flat_csv(out / "genre_eligibility_views_check.csv", checks)
    meta = {**{k: avail[k] for k in ("created_at_utc", "pool_query", "snapshot_file", "snapshot_sha256",
                                       "snapshot_rows", "scrape_api_reported_total")},
            "benchmark_books": len(bench), "per_genre_target": PER_GENRE,
            "accepted_per_stratum": dict(Counter(t["stratum"] for t in training)),
            "total_training_ids": len(training), "shortages": shortage,
            "genre_rules": "scrapers/genres.py", "assignment": "primary genre by precedence " + " > ".join(genres.GENRE_ORDER),
            "ordering": f'sha256("{config.SEED}:<identifier>") ascending within each genre (not by views/downloads)',
            "group_cap": config.TRAINING_GROUP_CAP, "views_check_note": "have_data checked once at build time"}
    dump_json(out / "training_ids.json", {"meta": meta, "ids": training})
    dump_json(out / "training_manifest_meta.json", meta)
    run.finish([], None)
    print(json.dumps({k: meta[k] for k in ("accepted_per_stratum", "total_training_ids", "shortages")}, indent=1))
    return 2 if shortage else 0


if __name__ == "__main__":
    sys.exit(main())
