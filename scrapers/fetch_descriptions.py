#!/usr/bin/env python3
"""Fetch the raw `description` field of the books in data/training_api.csv (one paced search call per 50 books).

Writes data/descriptions_raw_5600.jsonl (one line per book: identifier, found, description) and a run log folder.
Resumable: books already in the output file are skipped. Same identification, pacing, retries and stop rules as
the scrapers (see ia_common). The committed file was produced by this logic on 21-22 Nov 2026.

    python scrapers/fetch_descriptions.py
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import config
import ia_common as c


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ids-csv", default=str(config.DATA_DIR / "training_api.csv"))
    p.add_argument("--out", default=str(config.DATA_DIR / "descriptions_raw_5600.jsonl"))
    p.add_argument("--log-dir", default=str(config.RUNS_DIR / "description_fetch"))
    args = p.parse_args(argv)
    out = Path(args.out)
    ids = [r["identifier"] for r in csv.DictReader(open(args.ids_csv, encoding="utf-8-sig"))]
    done = {json.loads(l)["identifier"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    todo = [i for i in ids if i not in done]
    print(f"{len(ids)} books, {len(done)} already fetched, {len(todo)} to fetch", flush=True)
    run = c.Run("description_fetch", run_dir=args.log_dir)
    client = c.Client(run)
    aborted = None
    try:
        for n in range(0, len(todo), 50):
            batch = todo[n:n + 50]
            q = "identifier:(" + " OR ".join(f'"{i}"' for i in batch) + ")"
            params = [("q", q), ("rows", len(batch)), ("output", "json"), ("fl[]", "identifier"), ("fl[]", "description")]
            docs = {d["identifier"]: d for d in client.get(config.SEARCH_URL, params=params,
                                                           context={"call": "description", "start": n}).json()["response"]["docs"]}
            with open(out, "a", encoding="utf-8") as f:
                for i in batch:
                    d = docs.get(i)
                    f.write(json.dumps({"identifier": i, "found": d is not None,
                                        "description": (d or {}).get("description")}, ensure_ascii=False) + "\n")
            print(f"  {min(n + 50, len(todo))}/{len(todo)}", flush=True)
    except c.Abort as exc:
        aborted = str(exc)
        print("ABORTED:", aborted)
    run.finish([], aborted)
    return 1 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())
