# training_ol_books.csv (Open Library-linked books)

Built 22 Nov 2026 by `scrapers/build_ol_dataset.py` from saved records only (no web access). Source: archive.org API; every row has an
`openlibrary_work` id (item linked to an Open Library book record), English, one of the three genres (or a benchmark book).

| File | Rows | Meaning |
|---|---:|---|
| `training_ol_books.csv` | 20,271 | All Open Library-linked books: 5,271 from the first 5,600 + 15,000 newly collected (`source_batch` = `first_5600` / `ol_collection`) |
| `training_ol_books_with_description.csv` | 17,763 | The **description-ready** subset (`description_ready = 1`): cleaned description of 25+ words, not boilerplate, not the same text as another work |
| `training_ol_books_report.json` | - | Counts and validation |

Columns = those of `training_api.csv` plus: `openlibrary_work`, `openlibrary_edition`, `ol_group` (= work id; split train/test by it), `author_missing`
(1 when archive.org lists no creator or the text "None"; `creators`/`first_creator` are then empty), `description` (cleaned; use `description_ready` to identify usable summaries),
`description_words`, `description_ready`, `source_batch`.

Older books without a usable description stay in the main CSV with `description_ready = 0` (2,443 older + 65 new rows); the description-ready
file excludes them. Exclusions before collection are in `data/manifest/ol_availability.json` and `ol_exclusions.csv`
(41,849 snapshot rows -> 19,607 usable new candidates -> 15,000 chosen, 5,000 per genre, hash order, not by views).

Known limits: 329 of the first 5,600 books (39 of them benchmark books) have no Open Library link and are not in this file; 42 books have no author;
4 Open Library works have more than 3 items (all older books); new books come from the wider pool and have lower views (median 108 vs 153) and more
juvenile titles (28% vs 17%); views were read on 19-22 Nov 2026 (check `retrieved_at_utc`); descriptions are catalogue/publisher summaries.
