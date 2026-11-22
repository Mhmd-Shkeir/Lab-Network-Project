#!/usr/bin/env python3
"""Fetch the Open Library work/edition ids (archive.org metadata fields openlibrary_work / openlibrary_edition) for the books in
data/training_api.csv. One paced search call per 50 books, archive.org only. Writes data/openlibrary_ids_5600.csv. Resumable.

    python scrapers/fetch_openlibrary_ids.py
"""
import csv, sys
from pathlib import Path
import config, ia_common as c

def main():
    ids = [r["identifier"] for r in csv.DictReader(open(config.DATA_DIR / "training_api.csv", encoding="utf-8-sig"))]
    out = config.DATA_DIR / "openlibrary_ids_5600.csv"
    done = {r["identifier"] for r in csv.DictReader(open(out, encoding="utf-8-sig"))} if out.exists() else set()
    todo = [i for i in ids if i not in done]
    print(len(ids), "books,", len(done), "done,", len(todo), "to fetch", flush=True)
    run = c.Run("openlibrary_id_fetch", run_dir=config.RUNS_DIR / "openlibrary_id_fetch"); client = c.Client(run); aborted = None
    new = not out.exists()
    try:
        with open(out, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=["identifier", "openlibrary_work", "openlibrary_edition"])
            if new: w.writeheader()
            for n in range(0, len(todo), 50):
                batch = todo[n:n + 50]
                q = "identifier:(" + " OR ".join(f'"{i}"' for i in batch) + ")"
                params = [("q", q), ("rows", len(batch)), ("output", "json")] + [("fl[]", x) for x in ("identifier", "openlibrary_work", "openlibrary_edition")]
                docs = {d["identifier"]: d for d in client.get(config.SEARCH_URL, params=params, context={"call": "ol_ids", "start": n}).json()["response"]["docs"]}
                for i in batch:
                    d = docs.get(i, {})
                    flat = lambda v: v[0] if isinstance(v, list) and v else (v or "")
                    w.writerow({"identifier": i, "openlibrary_work": flat(d.get("openlibrary_work")), "openlibrary_edition": flat(d.get("openlibrary_edition"))})
                f.flush(); print(f"  {min(n + 50, len(todo))}/{len(todo)}", flush=True)
    except c.Abort as e:
        aborted = str(e); print("ABORTED:", aborted)
    run.finish([], aborted); print("FINISHED")
    return 1 if aborted else 0

if __name__ == "__main__":
    sys.exit(main())
