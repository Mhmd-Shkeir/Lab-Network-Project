#!/usr/bin/env python3
"""Build data/training_with_descriptions.csv: the training books that have a usable description.

Reads data/training_api.csv (unchanged) and data/descriptions_raw_5600.jsonl (see fetch_descriptions.py); no web access.
A book is kept when its cleaned description has 25 or more words, is not boilerplate, and is not the same text as a
different work's description (rules: scrapers/descriptions.py). The new file has every column of training_api.csv plus
`description` (cleaned text) and `description_words`. Rows keep their `work_group`, genre labels and views.

    python scrapers/build_description_dataset.py
"""
import json
import sys
from collections import Counter

import pandas as pd

import config
import descriptions as d


def main():
    data = config.DATA_DIR
    df = pd.read_csv(data / "training_api.csv", encoding="utf-8-sig")
    raw = {}
    for line in (data / "descriptions_raw_5600.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            raw[r["identifier"]] = r["description"]
    df["description_raw_words"] = [len(d.raw_text(raw.get(i)).split()) for i in df["identifier"]]
    df["description"] = [d.clean_description(raw.get(i)) for i in df["identifier"]]
    df["description_words"] = [d.description_words(t) for t in df["description"]]
    df["_norm"] = df["description"].map(d.normalised)
    groups_per_text = df[df["description_words"] > 0].groupby("_norm")["work_group"].nunique()
    shared = set(groups_per_text[groups_per_text > 1].index)
    df["_shared"] = df["_norm"].isin(shared)
    df["_boiler"] = df["description"].map(d.is_boilerplate)
    usable = (df["description_words"] >= d.MIN_WORDS) & ~df["_shared"] & ~df["_boiler"]
    out = df[usable].drop(columns=["description_raw_words", "_norm", "_shared", "_boiler"]).reset_index(drop=True)
    out.to_csv(data / "training_with_descriptions.csv", index=False, encoding="utf-8-sig")

    n = len(df)
    report = {
        "books_checked": n, "no_description_at_all": int((df["description_raw_words"] == 0).sum()),
        "only_catalogue_text_or_under_5_words": int(((df["description_raw_words"] > 0) & (df["description_words"] < 5)).sum()),
        "5_to_24_words": int(((df["description_words"] >= 5) & (df["description_words"] < d.MIN_WORDS)).sum()),
        "25_or_more_words": int((df["description_words"] >= d.MIN_WORDS).sum()),
        "removed_shared_text_or_boilerplate": int(((df["description_words"] >= d.MIN_WORDS) & (df["_shared"] | df["_boiler"])).sum()),
        "kept_usable": len(out), "kept_share": round(len(out) / n, 4),
        "kept_per_stratum": dict(Counter(out["sampling_stratum"])), "kept_per_primary_genre": dict(Counter(out["genre_primary"])),
        "kept_in_americana": int(out["in_americana"].sum()), "kept_juvenile": int(out["juvenile"].sum()),
        "words_median": float(out["description_words"].median()),
        "words_p25_p75": [float(out["description_words"].quantile(.25)), float(out["description_words"].quantile(.75))],
        "views_median_kept": float(out["views_all_time"].median()),
        "views_median_not_kept": float(df.loc[~usable, "views_all_time"].median()),
    }
    (data / "training_with_descriptions_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
