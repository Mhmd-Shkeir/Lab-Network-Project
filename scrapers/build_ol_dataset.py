#!/usr/bin/env python3
"""Build data/training_ol_books.csv: every training book that is linked to an Open Library book record.

Rows = the earlier 5,600 books that have an Open Library work id (data/openlibrary_ids_5600.csv) + the newly collected books
(run folder given with --new-run; all of them were chosen to have an Open Library link and a usable description).
Columns = those of training_api.csv + openlibrary_work, openlibrary_edition, ol_group (Open Library work id, use it to keep copies
together in a train/test split), description (cleaned; empty when the book has no usable one), description_words.
No web access: reads files only.

    python scrapers/build_ol_dataset.py --new-run data/runs/api_<timestamp>_ol15000
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

import config
import descriptions as dsc
import genres
from ia_common import write_records_csv

READY = dsc.MIN_WORDS            # description_ready = cleaned description of 25+ words, not boilerplate


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--new-run", required=True)
    args = p.parse_args(argv)
    data = config.DATA_DIR
    old = pd.read_csv(data / "training_api.csv", encoding="utf-8-sig")
    ids = pd.read_csv(data / "openlibrary_ids_5600.csv", encoding="utf-8-sig").fillna("")
    wd = pd.read_csv(data / "training_with_descriptions.csv", encoding="utf-8-sig")[["identifier", "description"]]
    old = old.merge(ids, on="identifier", how="left").merge(wd, on="identifier", how="left")
    old = old[old["openlibrary_work"].fillna("") != ""].copy()
    old["description"] = old["description"].fillna("")
    old["source_batch"] = "first_5600"

    manifest = {x["identifier"]: x for x in json.loads((config.MANIFEST_DIR / "ol_books_new_ids.json").read_text(encoding="utf-8"))["ids"]}
    recs = {}
    for line in (Path(args.new_run) / "records.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line); recs[r["identifier"]] = r
    new_rows, dropped = [], Counter()
    for ident, m in manifest.items():
        r = recs.get(ident)
        if r is None:
            dropped["not collected"] += 1; continue
        if r["status"] != "ok":
            dropped[f"status {r['status']}"] += 1; continue
        text = dsc.clean_description(r.get("raw_description"))
        flags = genres.genre_flags(r["subjects"])
        row = {k: r.get(k) for k in config.DATA_FIELDS + config.PROVENANCE_FIELDS}
        row.update({"sampling_stratum": m["stratum"], "genre_primary": genres.primary_genre(flags) or "none",
                    **{f"genre_{g}": flags[g] for g in genres.GENRE_ORDER}, "in_americana": m.get("in_americana", False),
                    "juvenile": genres.is_juvenile(r["subjects"]), "work_group": m["work_group"], "in_benchmark": False,
                    "openlibrary_work": r.get("raw_openlibrary_work") or m["ol_work"], "openlibrary_edition": r.get("raw_openlibrary_edition") or m["ol_edition"],
                    "description": text, "source_batch": "ol_collection"})
        new_rows.append(row)
    new = pd.DataFrame(new_rows)
    new["publication_year"] = new["publication_year"].astype(int)
    cols = [c for c in pd.read_csv(data / "training_api.csv", encoding="utf-8-sig", nrows=1).columns] + ["openlibrary_work", "openlibrary_edition", "description", "source_batch"]
    both = pd.concat([old[cols], new[cols]], ignore_index=True)
    # list-valued columns of new rows are lists; flatten like the other CSVs
    for c in ("creators", "subjects"):
        both[c] = both[c].map(lambda v: config.LIST_SEPARATOR.join(v) if isinstance(v, list) else v)
    both["description_words"] = both["description"].map(dsc.description_words)
    both["ol_group"] = both["openlibrary_work"]
    dup_before = int(both.identifier.duplicated().sum())
    both = both.drop_duplicates("identifier").reset_index(drop=True)
    # description_ready: the older books keep their description only if it is usable; boilerplate / shared texts are not ready
    norm = both["description"].map(dsc.normalised)
    groups_per_text = both[both.description_words > 0].assign(n=norm).groupby("n")["ol_group"].nunique()
    shared = set(groups_per_text[groups_per_text > 1].index)
    both["description_ready"] = ((both["description_words"] >= READY) & ~both["description"].map(dsc.is_boilerplate) & ~norm.isin(shared)).astype(int)
    both.loc[both["description_ready"] == 0, "description"] = both.loc[both["description_ready"] == 0, "description"].where(both["description_words"] >= READY, "")
    both["description_words"] = both["description"].map(dsc.description_words)
    out_cols = cols[:-1] + ["ol_group", "description_words", "description_ready", "source_batch"]
    both[out_cols].to_csv(data / "training_ol_books.csv", index=False, encoding="utf-8-sig")
    both[both.description_ready == 1][out_cols].to_csv(data / "training_ol_books_with_description.csv", index=False, encoding="utf-8-sig")

    usable = both["description_ready"] == 1
    no_author = both["first_creator"].fillna("") == ""
    wc = both.groupby("ol_group").size()
    rep = {"rows": len(both), "from_first_5600": int((both.source_batch == "first_5600").sum()), "newly_collected": int((both.source_batch == "ol_collection").sum()),
           "new_not_usable": dict(dropped), "all_have_open_library_work": bool((both.openlibrary_work != "").all()),
           "distinct_open_library_works": int(both.openlibrary_work.nunique()), "max_items_per_work": int(both.openlibrary_work.value_counts().max()),
           "with_usable_description": int(usable.sum()), "per_stratum": both.sampling_stratum.value_counts().to_dict(),
           "per_stratum_with_description": both[usable].sampling_stratum.value_counts().to_dict(),
           "juvenile_share": round(float(both.juvenile.mean()), 4), "language_all_english": bool(both.language.str.contains("eng").all()),
           "duplicate_identifiers_removed": dup_before, "duplicate_identifiers": int(both.identifier.duplicated().sum()),
           "description_ready_rows": int(usable.sum()), "not_ready_rows": int((~usable).sum()),
           "not_ready_by_source": both[~usable].source_batch.value_counts().to_dict(),
           "shared_description_texts_removed_from_ready": int(len(shared)),
           "missing_author_rows": int(no_author.sum()), "missing_author_by_source": both[no_author].source_batch.value_counts().to_dict(),
           "missing_title_rows": int((both.title.fillna("") == "").sum()), "missing_year_rows": int(both.publication_year.isna().sum()),
           "work_groups_with_more_than_3_items": int((wc > 3).sum()), "largest_work_group": int(wc.max()),
           "ready_work_groups": int(both[usable].ol_group.nunique()),
           "description_words_ready_p5_median_p95": [float(both[usable].description_words.quantile(q)) for q in (.05, .5, .95)],
           "views_min_median_max": [int(both.views_all_time.min()), float(both.views_all_time.median()), int(both.views_all_time.max())],
           "retrieved_at_window_utc": [str(both.retrieved_at_utc.min()), str(both.retrieved_at_utc.max())]}
    (data / "training_ol_books_report.json").write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
