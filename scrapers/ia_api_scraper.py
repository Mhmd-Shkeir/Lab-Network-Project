#!/usr/bin/env python3
"""API scraper: Internet Archive advanced-search metadata + the official Views API, in batches.

Per batch: 1 call to archive.org/advancedsearch.php (title, creator, year, subject, language,
addeddate, imagecount) and 1 call to be-api.us.archive.org/views/v1/short/<ids> (all-time views).
Never reads HTML and never uses another method's data.

Example (validation on 10 books, then the benchmark list):
    python scrapers/ia_api_scraper.py --limit 10 --label validation
    python scrapers/ia_api_scraper.py
Training list (about 2,000 ids):
    python scrapers/ia_api_scraper.py --ids data/manifest/training_ids.json --label training
Threaded (batches in parallel; ONE global limit for all calls, starts >= --min-interval apart):
    python scrapers/ia_api_scraper.py --workers 2 --min-interval 3 --batch-size 10 --label threads2
"""
import argparse
import sys

import config
from ia_common import (RequestFailed, add_common_args, client_factory, execute, failed_row, finalize_row,
                       iso, new_row, run_parallel, start_run, to_int, unique)

SEARCH_FIELDS = ["identifier", "title", "creator", "year", "subject", "language", "addeddate", "imagecount"]


def chunks(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def collect_batch(run, client, batch, batch_no, batch_total, extra_fields=()):
    ids = [identifier for _, identifier, _ in batch]
    rows = {identifier: new_row(identifier, "api", run, position) for position, identifier, _ in batch}
    label = f"advancedsearch.php + be-api views/v1/short (batch {batch_no}/{batch_total})"
    query = "identifier:(" + " OR ".join(f'"{i}"' for i in ids) + ")"
    params = [("q", query), ("rows", len(ids)), ("page", 1), ("output", "json")]
    params += [("fl[]", f) for f in list(SEARCH_FIELDS) + list(extra_fields)]
    ctx = {"call": "search", "batch": batch_no, "n_ids": len(ids), "first_id": ids[0]}
    try:
        search = client.get(config.SEARCH_URL, params=params, context=ctx)
        docs = {d["identifier"]: d for d in search.json()["response"]["docs"]}
        search_attempts, search_status = search.ia_attempts, search.status_code
    except RequestFailed as exc:
        for row in rows.values():
            failed_row(row, f"search call failed: {exc}", exc.status or "")
            row["attempts"] = exc.attempts
            run.save_record(row)
        return
    except (ValueError, KeyError) as exc:
        for row in rows.values():
            failed_row(row, f"search response unreadable: {type(exc).__name__}: {exc}", 200)
            run.save_record(row)
        return

    views, views_error, views_attempts, views_status = {}, "", 0, ""
    try:
        resp = client.get(config.VIEWS_URL + ",".join(ids), context={**ctx, "call": "views"})
        views, views_attempts, views_status = resp.json(), resp.ia_attempts, resp.status_code
    except RequestFailed as exc:
        views_error, views_attempts, views_status = f"views call failed: {exc}", exc.attempts, exc.status or ""
    except ValueError as exc:
        views_error = f"views response unreadable: {exc}"
    retrieved = iso()

    for identifier, row in rows.items():
        row["attempts"] = search_attempts + views_attempts
        row["http_status"] = f"{search_status}/{views_status}"
        row["retrieved_from"], row["retrieved_at_utc"] = label, retrieved
        doc = docs.get(identifier)
        if doc is None:
            failed_row(row, "identifier not returned by advancedsearch", row["http_status"])
            run.save_record(row)
            continue
        row["title"] = " ".join(str(doc.get("title", "")).split())
        row["creators"] = unique(doc.get("creator"))
        row["publication_year"] = to_int(doc.get("year")) if doc.get("year") is not None else None
        row["subjects"] = unique(doc.get("subject"))
        row["language"] = ",".join(unique(doc.get("language")))
        row["addeddate"] = str(doc.get("addeddate") or "")
        row["scanned_page_count"] = to_int(doc.get("imagecount")) if doc.get("imagecount") is not None else None
        for f in extra_fields:      # description / Open Library ids: stored raw in records.jsonl only (CSV columns unchanged)
            v = doc.get(f)
            row["raw_" + f] = " ".join(map(str, v)) if isinstance(v, list) else (v or "")
        errors = []
        info = views.get(identifier) if isinstance(views, dict) else None
        row["raw_views_api"] = info          # kept in records.jsonl only (recent-window counts are not CSV fields)
        if views_error:
            errors.append(views_error)
        elif not info:
            errors.append("identifier missing from views response")
        elif not info.get("have_data"):
            errors.append("views API have_data=false")
        else:
            row["views_all_time"] = int(info["all_time"])    # a genuine 0 is kept
        finalize_row(row, errors)
        run.save_record(row)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common_args(parser)
    parser.add_argument("--with-description", action="store_true", help="also fetch the item's description (raw, in records.jsonl)")
    parser.add_argument("--with-openlibrary", action="store_true", help="also fetch openlibrary_work / openlibrary_edition ids (raw, in records.jsonl)")
    parser.add_argument("--batch-size", type=int, default=config.API_BATCH_SIZE,
                        help=f"ids per search+views call pair (default {config.API_BATCH_SIZE})")
    args = parser.parse_args(argv)
    extra_fields = (["description"] if args.with_description else []) + (["openlibrary_work", "openlibrary_edition"] if args.with_openlibrary else [])
    run, id_rows, todo = start_run("api", args, extra={"batch_size": args.batch_size, "extra_fields": extra_fields})
    get_client = client_factory(run)
    batches = list(enumerate(chunks(todo, args.batch_size), 1))

    def handle(item):
        n, batch = item
        collect_batch(run, get_client(), batch, n, len(batches), extra_fields)
        print(f"  batch {n}/{len(batches)} done ({len(run.records)} records)", flush=True)

    return execute(run, id_rows, args, lambda: run_parallel(batches, handle, run.workers))


if __name__ == "__main__":
    sys.exit(main())
