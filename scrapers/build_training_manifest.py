#!/usr/bin/env python3
"""Build the training manifest: the 200 benchmark books + N books per genre (rules in scrapers/genres.py).

The benchmark manifest is never changed. Two modes:

 FIRST BUILD (v1, already done): Americana pool, 600 per genre -> training_ids.json (2,000 ids).
     python scrapers/build_training_manifest.py --check-only
     python scrapers/build_training_manifest.py --reuse-snapshot data/manifest/genre_pool_snapshot_<date>.csv.gz

 EXTEND (add more books per genre, keep every existing row):
     python scrapers/build_training_manifest.py --extend --scope all_texts --per-genre 1800 --check-only
     python scrapers/build_training_manifest.py --extend --scope all_texts --per-genre 1800 --reuse-snapshot <snapshot>
   Existing ids are kept (the old file is saved as training_ids_v1_2000.json); each genre is topped up to --per-genre with
   NEW books drawn in sha256 order (NOT by views/downloads), only books the Views API has data for (a genuine 0 counts),
   at most 3 per work_group across the whole set. New ids only are written to training_ids_extension_ids.json for the API scraper.
   To add a new genre: add it to scrapers/genres.py (GENRE_ORDER, GENRE_PHRASES, GENRE_QUERY) and run --extend again.

--scope americana  = same collection as the benchmark;  all_texts = any English text on archive.org (needed to reach 1,800+ per genre).
"""
import argparse
import csv
import gzip
import io
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import config
import genres
from build_manifest import metadata_problem
from ia_common import Client, Run, clean, dump_json, iso, order_key, sha256_file, unique, work_group, write_flat_csv

COLUMNS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language", "subject", "collection"]
FIELDS = list(COLUMNS)
BASE = (f"mediatype:texts AND language:eng AND creator:* AND year:[{config.YEAR_MIN} TO {config.YEAR_MAX}] "
        f"AND imagecount:[{config.IMAGECOUNT_MIN} TO {config.IMAGECOUNT_MAX}]")


def pool_query(scope):
    clause = " OR ".join(genres.GENRE_QUERY[g] for g in genres.GENRE_ORDER)
    pre = f"collection:{config.POOL_COLLECTION} AND " if scope == "americana" else ""
    return f"{pre}{BASE} AND ({clause})"


def fetch(client, query):
    items, cursor, total = [], None, None
    while True:
        params = {"q": query, "fields": ",".join(FIELDS), "count": 5000}
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
                    "subject": config.LIST_SEPARATOR.join(unique(it.get("subject"))),
                    "collection": ",".join(unique(it.get("collection")))})
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def classify(rows, skip):
    """Apply duplicate/already-selected exclusion, genre rules, metadata checks and non-fiction rules.
    `skip` maps identifier -> reason for ids that are already in the benchmark / training set."""
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
        if ident in skip:
            drop("already_selected", skip[ident])
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
                           "work_group": work_group(row["title"], creators), "key": order_key(ident),
                           "in_americana": "americana" in row.get("collection", "").split(",")})
    return candidates, exclusions


def availability(rows, candidates, exclusions, wanted):
    raw_flags = Counter()
    for row in rows:
        f = genres.genre_flags([s for s in row["subject"].split(config.LIST_SEPARATOR) if s])
        for g in genres.GENRE_ORDER:
            raw_flags[g] += f[g]
    out = {"snapshot_rows": len(rows), "new_books_wanted_per_genre": wanted, "genres": {}}
    for g in genres.GENRE_ORDER:
        cands = [c for c in candidates if c["primary_genre"] == g]
        counts = Counter(c["work_group"] for c in cands)
        capped = sum(min(n, config.TRAINING_GROUP_CAP) for n in counts.values())
        excl = Counter(e["stage"] for e in exclusions if e["primary_genre"] == g)
        out["genres"][g] = {
            "rows_matching_rule_any_priority": raw_flags[g], "excluded_by_stage": dict(excl),
            "candidates_after_all_rules": len(cands), "of_which_americana": sum(1 for c in cands if c["in_americana"]),
            "distinct_work_groups": len(counts), "candidates_after_group_cap_3_estimate": capped,
            "new_books_wanted": wanted[g], "enough_before_views_check": capped >= wanted[g]}
    out["overlap_rows"] = {
        "science_fiction+fantasy": sum(1 for c in candidates if c["flags"]["science_fiction"] and c["flags"]["fantasy"]),
        "science_fiction+mystery_thriller": sum(1 for c in candidates if c["flags"]["science_fiction"] and c["flags"]["mystery_thriller"]),
        "fantasy+mystery_thriller": sum(1 for c in candidates if c["flags"]["fantasy"] and c["flags"]["mystery_thriller"]),
        "all_three": sum(1 for c in candidates if all(c["flags"].values()))}
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", default=str(config.MANIFEST_DIR))
    p.add_argument("--scope", choices=["americana", "all_texts"], default="americana")
    p.add_argument("--extend", action="store_true", help="keep the existing training_ids.json and top up each genre")
    p.add_argument("--per-genre", type=int, help="target books per genre in total (default 600; with --extend 1800)")
    p.add_argument("--check-only", action="store_true", help="availability + preview only, then stop")
    p.add_argument("--reuse-snapshot", help="genre_pool_snapshot_*.csv.gz to use instead of downloading")
    p.add_argument("--reported-total", type=int)
    args = p.parse_args(argv)
    out = Path(args.out_dir)
    per_genre = args.per_genre or (1800 if args.extend else 600)
    tag = "" if (args.scope == "americana" and not args.extend) else f"_{args.scope}"
    query = pool_query(args.scope)
    run = Run("training_manifest", run_dir=out / f"training_build_log{tag}")
    client = Client(run)
    created = iso()
    bench = {x["identifier"]: x for x in json.loads((out / "benchmark_200_ids.json").read_text(encoding="utf-8"))["ids"]}

    # --- what is already selected
    existing = []
    if args.extend:
        v1 = out / "training_ids_v1_2000.json"
        current = out / "training_ids.json"
        if not v1.exists():
            shutil.copyfile(current, v1)                 # keep the first 2,000-id list untouched
        existing = json.loads(v1.read_text(encoding="utf-8"))["ids"]
    skip = {i: "already one of the 200 benchmark books" for i in bench}
    skip.update({x["identifier"]: "already in the training set" for x in existing})
    have_per_stratum = Counter(x["stratum"] for x in existing)
    wanted = {g: max(0, per_genre - (have_per_stratum[g] if args.extend else 0)) for g in genres.GENRE_ORDER}

    # --- pool snapshot
    if args.reuse_snapshot:
        snap, total = Path(args.reuse_snapshot), args.reported_total
    else:
        items, total = fetch(client, query)
        snap = out / f"genre_pool_snapshot{tag}_{created[:10].replace('-', '')}.csv.gz"
        write_snapshot(snap, items)
    with gzip.open(snap, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    candidates, exclusions = classify(rows, skip)
    avail = availability(rows, candidates, exclusions, wanted)
    avail.update({"created_at_utc": created, "pool_query": query, "scope": args.scope, "snapshot_file": snap.name,
                  "snapshot_sha256": sha256_file(snap), "scrape_api_reported_total": total,
                  "existing_rows_kept": len(existing)})
    dump_json(out / f"genre_availability{tag}.json", avail)
    write_flat_csv(out / f"genre_exclusions{tag}.csv", exclusions)
    preview = []
    for g in genres.GENRE_ORDER:
        for c in sorted([c for c in candidates if c["primary_genre"] == g], key=lambda c: c["key"])[:6]:
            preview.append({"genre": g, "identifier": c["identifier"], "title": c["title"][:90],
                            "creator": c["creator"][:50], "year": c["year"], "imagecount": c["imagecount"],
                            "americana": c["in_americana"],
                            "also_matches": ",".join(x for x in genres.GENRE_ORDER if c["flags"][x] and x != g),
                            "subjects": c["subject"][:110]})
    write_flat_csv(out / f"genre_preview{tag}.csv", preview)
    print(json.dumps({k: avail[k] for k in ("snapshot_rows", "overlap_rows", "genres")}, indent=1))
    if args.check_only:
        return 0

    # --- selection: Views API has data, random hash order, shared group cap
    group_count = Counter(x["work_group"] for x in bench.values())
    for x in existing:
        group_count[x["work_group"]] += 1
    if args.extend:
        training = [dict(x) for x in existing]
    else:
        training = [{"identifier": i, "position": n, "stratum": "benchmark_random_fiction", "in_benchmark": True,
                     "work_group": x["work_group"], "stream_rank": x["stream_rank"], "in_americana": True}
                    for n, (i, x) in enumerate(bench.items(), 1)]
    new_entries, checks, shortage = [], [], {}
    for g in genres.GENRE_ORDER:
        pool = sorted([c for c in candidates if c["primary_genre"] == g], key=lambda c: c["key"])
        accepted, examined = 0, 0
        for start in range(0, len(pool), config.VIEWS_CHECK_BATCH):
            if accepted >= wanted[g]:
                break
            batch = pool[start:start + config.VIEWS_CHECK_BATCH]
            views = client.get(config.VIEWS_URL + ",".join(c["identifier"] for c in batch),
                               context={"call": "views_check", "genre": g, "start": start}).json()
            stamp = iso()
            for rank, c in enumerate(batch, start + 1):
                if accepted >= wanted[g]:
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
                    entry = {"identifier": c["identifier"], "position": len(training) + 1, "stratum": g,
                             "in_benchmark": False, "work_group": c["work_group"], "stream_rank": rank,
                             "in_americana": c["in_americana"], "genre_flags": c["flags"]}
                    training.append(entry)
                    new_entries.append(entry)
                    decision = "accepted"
                checks.append({"identifier": c["identifier"], "genre": g, "pool_rank": rank, "have_data": have,
                               "views_all_time_at_check": info.get("all_time") if have else "",
                               "checked_at_utc": stamp, "decision": decision})
            print(f"  {g}: examined {examined}, accepted {accepted} of {wanted[g]}", flush=True)
        if accepted < wanted[g]:
            shortage[g] = {"accepted_new": accepted, "wanted_new": wanted[g]}
    write_flat_csv(out / f"genre_exclusions{tag}.csv", exclusions)
    write_flat_csv(out / f"genre_eligibility_views_check{tag}.csv", checks)
    meta = {**{k: avail[k] for k in ("created_at_utc", "pool_query", "scope", "snapshot_file", "snapshot_sha256",
                                       "snapshot_rows", "scrape_api_reported_total")},
            "benchmark_books": len(bench), "per_genre_target_total": per_genre, "extends": "training_ids_v1_2000.json" if args.extend else None,
            "accepted_per_stratum": dict(Counter(t["stratum"] for t in training)),
            "new_ids_in_this_build": len(new_entries), "total_training_ids": len(training), "shortages": shortage,
            "genre_rules": "scrapers/genres.py", "assignment": "primary genre by precedence " + " > ".join(genres.GENRE_ORDER),
            "ordering": f'sha256("{config.SEED}:<identifier>") ascending within each genre (not by views/downloads)',
            "group_cap": config.TRAINING_GROUP_CAP, "views_check_note": "have_data checked once at build time",
            "in_americana_note": "v1 books are all Americana; new books carry their own flag"}
    dump_json(out / "training_ids.json", {"meta": meta, "ids": training})
    dump_json(out / "training_manifest_meta.json", meta)
    if args.extend:
        dump_json(out / "training_ids_extension_ids.json", {"meta": meta, "ids": new_entries})
    run.finish([], None)
    print(json.dumps({k: meta[k] for k in ("accepted_per_stratum", "new_ids_in_this_build", "total_training_ids",
                                            "shortages")}, indent=1))
    return 2 if shortage else 0


if __name__ == "__main__":
    sys.exit(main())
