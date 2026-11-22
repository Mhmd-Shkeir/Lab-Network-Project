#!/usr/bin/env python3
"""Build the list of NEW books for the larger Open Library-linked training set (archive.org API only).

Candidates: items of the three-genre pool (same filters/rules as before) that are English, linked to an Open Library book
(`openlibrary_work` present) and have a usable description (25+ words after removing catalogue text, not boilerplate, not the
same text as a different book). Already selected books and the benchmark are never repeated. At most 3 items per Open Library
work (all items of one work stay together in the train/test split via `ol_work`). Drawn in sha256 order (not by views),
PER_GENRE new books per primary genre.

    python scrapers/build_ol_manifest.py --check-only      # snapshot + availability, then stop
    python scrapers/build_ol_manifest.py --per-genre 5000  # also write data/manifest/ol_books_new_ids.json
    (--reuse-snapshot <file> to reuse a saved snapshot)
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
import descriptions as dsc
import genres
from build_manifest import metadata_problem
from build_training_manifest import BASE, classify
from ia_common import Client, Run, clean, dump_json, iso, order_key, sha256_file, unique, work_group

FIELDS = ["identifier", "title", "creator", "year", "imagecount", "addeddate", "language", "subject", "collection",
          "description", "openlibrary_work", "openlibrary_edition"]
QUERY = (BASE + " AND (" + " OR ".join(genres.GENRE_QUERY[g] for g in genres.GENRE_ORDER) + ")"
         + " AND openlibrary_work:[* TO *] AND description:[* TO *]")


def flat(v):
    return v[0] if isinstance(v, list) and v else (v or "")


def fetch(client):
    items, cursor, total = [], None, None
    while True:
        params = {"q": QUERY, "fields": ",".join(FIELDS), "count": 2000}
        if cursor:
            params["cursor"] = cursor
        data = client.get(config.SCRAPE_URL, params=params, context={"call": "ol_scrape", "have": len(items)}).json()
        items += data.get("items", [])
        total = data.get("total") if total is None else total
        cursor = data.get("cursor")
        print(f"  snapshot: {len(items)} / {total}", flush=True)
        if not cursor:
            return items, total


def write_snapshot(path, items):
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=FIELDS)
    w.writeheader()
    for it in sorted(items, key=lambda x: x["identifier"]):
        w.writerow({"identifier": it["identifier"], "title": clean(it.get("title", "")),
                    "creator": config.LIST_SEPARATOR.join(unique(it.get("creator"))), "year": it.get("year", ""),
                    "imagecount": it.get("imagecount", ""), "addeddate": it.get("addeddate", ""),
                    "language": ",".join(unique(it.get("language"))), "subject": config.LIST_SEPARATOR.join(unique(it.get("subject"))),
                    "collection": ",".join(unique(it.get("collection"))), "description": dsc.raw_text(it.get("description")),
                    "openlibrary_work": flat(it.get("openlibrary_work")), "openlibrary_edition": flat(it.get("openlibrary_edition"))})
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as gz:
        gz.write(buf.getvalue().encode("utf-8"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--per-genre", type=int, default=5000)
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--reuse-snapshot")
    p.add_argument("--out-dir", default=str(config.MANIFEST_DIR))
    args = p.parse_args(argv)
    out = Path(args.out_dir)
    run = Run("ol_manifest", run_dir=out / "ol_build_log")
    client = Client(run)
    created = iso()
    if args.reuse_snapshot:
        snap = Path(args.reuse_snapshot); total = None
    else:
        items, total = fetch(client)
        snap = out / f"ol_pool_snapshot_{created[:10].replace('-', '')}.csv.gz"
        write_snapshot(snap, items)
    with gzip.open(snap, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # already selected books (benchmark + the 5,600 training books) and their Open Library works
    bench = {x["identifier"] for x in json.loads((out / "benchmark_200_ids.json").read_text(encoding="utf-8"))["ids"]}
    existing = json.loads((out / "training_ids.json").read_text(encoding="utf-8"))["ids"]
    skip = {i: "already one of the 200 benchmark books" for i in bench}
    skip.update({x["identifier"]: "already in the 5,600 training books" for x in existing})
    ol_old = {}
    olf = config.DATA_DIR / "openlibrary_ids_5600.csv"
    if olf.exists():
        ol_old = {r["identifier"]: r["openlibrary_work"] for r in csv.DictReader(open(olf, encoding="utf-8-sig"))}
    work_count = Counter(w for w in ol_old.values() if w)

    candidates, exclusions = classify(rows, skip)
    by_id = {r["identifier"]: r for r in rows}
    usable, shared_texts = [], Counter()
    for c in candidates:
        r = by_id[c["identifier"]]
        text = dsc.clean_description(r["description"])
        c.update(ol_work=r["openlibrary_work"], ol_edition=r["openlibrary_edition"], description=text, dwords=dsc.description_words(text))
        if c["dwords"] < dsc.MIN_WORDS:
            exclusions.append({"identifier": c["identifier"], "stage": "description", "reason": f"cleaned description under {dsc.MIN_WORDS} words",
                               "primary_genre": c["primary_genre"], "title": c["title"][:80]}); continue
        if dsc.is_boilerplate(text):
            exclusions.append({"identifier": c["identifier"], "stage": "description", "reason": "boilerplate description",
                               "primary_genre": c["primary_genre"], "title": c["title"][:80]}); continue
        c["norm"] = dsc.normalised(text); shared_texts[c["norm"]] += 1
        usable.append(c)
    final = []
    for c in usable:
        if shared_texts[c["norm"]] > 1:
            exclusions.append({"identifier": c["identifier"], "stage": "description", "reason": "same description text as another item",
                               "primary_genre": c["primary_genre"], "title": c["title"][:80]}); continue
        final.append(c)
    avail = {"created_at_utc": created, "pool_query": QUERY, "snapshot_file": snap.name, "snapshot_sha256": sha256_file(snap),
             "scrape_api_reported_total": total, "snapshot_rows": len(rows), "new_candidates_usable": len(final),
             "excluded_by_stage": dict(Counter(e["stage"] for e in exclusions)), "per_genre_wanted": args.per_genre,
             "per_genre_available": {g: sum(1 for c in final if c["primary_genre"] == g) for g in genres.GENRE_ORDER},
             "distinct_open_library_works_available": len({c["ol_work"] for c in final})}
    dump_json(out / "ol_availability.json", avail)
    print(json.dumps(avail, indent=1))
    if args.check_only:
        return 0

    new, shortage = [], {}
    for g in genres.GENRE_ORDER:
        pool = sorted([c for c in final if c["primary_genre"] == g], key=lambda c: c["key"])
        n = 0
        for c in pool:
            if n >= args.per_genre:
                break
            if work_count[c["ol_work"]] >= config.TRAINING_GROUP_CAP:
                continue
            work_count[c["ol_work"]] += 1
            n += 1
            new.append({"identifier": c["identifier"], "position": len(new) + 1, "stratum": g, "in_benchmark": False,
                        "work_group": c["work_group"], "ol_work": c["ol_work"], "ol_edition": c["ol_edition"],
                        "in_americana": c["in_americana"], "genre_flags": c["flags"]})
        if n < args.per_genre:
            shortage[g] = {"selected": n, "wanted": args.per_genre}
    from ia_common import write_flat_csv
    write_flat_csv(out / "ol_exclusions.csv", exclusions)
    meta = {**{k: avail[k] for k in ("created_at_utc", "pool_query", "snapshot_file", "snapshot_sha256")}, "new_books": len(new),
            "per_stratum": dict(Counter(x["stratum"] for x in new)), "shortages": shortage, "group_key": "openlibrary_work (max 3 items per work)",
            "ordering": f'sha256("{config.SEED}:<identifier>") ascending within each genre (not by views)',
            "rules": "English, Open Library-linked, usable description (25+ words, not boilerplate, not shared), genre rules in genres.py"}
    dump_json(out / "ol_books_new_ids.json", {"meta": meta, "ids": new})
    print(json.dumps({k: meta[k] for k in ("new_books", "per_stratum", "shortages")}, indent=1))
    run.finish([], None)
    return 2 if shortage else 0


if __name__ == "__main__":
    sys.exit(main())
