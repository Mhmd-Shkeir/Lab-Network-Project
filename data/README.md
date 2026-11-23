# data/ - what is here

Only the main CSV files are kept in this folder. Everything else here is supporting material.

## The five CSV files

| File | Rows | What it is |
|---|---:|---|
| `benchmark_200_api.csv` | 200 | The fixed 200 books collected with the **API** scraper |
| `benchmark_200_bs4.csv` | 200 | The same 200 books collected with the **BS4** (Requests + BeautifulSoup) scraper |
| `benchmark_200_selenium.csv` | 200 | The same 200 books collected with the **Selenium** scraper |
| `training_api.csv` | 5,600 | The first training set collected with the API: 200 benchmark books + 1,800 books for each of three genres (science fiction, fantasy, mystery/thriller) |
| `popularity_training_clean.csv` | 17,727 | The **final clean dataset** used by the machine-learning notebooks (it contains the 5,600-book set's books that have a work link and a usable description, plus the 15,000-book API collection). 37 columns, grouped by `ol_group` (the work ID) |

`checksums.sha256` checks these five files: `cd data && sha256sum -c checksums.sha256`.

## Folders and other files

| Path | What it is |
|---|---|
| `runs/` | The raw run folders of every collection: `records.jsonl`, the per-attempt log and `run.json` (the 15,000-book run is `api_20261122_154837_ol15000`) |
| `manifest/` | The frozen lists of chosen book IDs, pool snapshots and exclusion records (how the books were picked) |
| `labels/` | Labels and sampling files of the children-audience experiment (notebook 08) |
| `benchmark_200_comparison/` | Field-by-field comparison of the three benchmark CSVs |
| `completeness_report.md/.json` | Completeness check of the three benchmark CSVs |
| `popularity_training_quality.json` | Quality checks that produced the clean dataset |
| `archive/` | Notes and raw files that belonged to removed intermediate CSV files (kept for reference only) |

## Removed intermediate CSV files (still in Git history)

To keep the folder simple we removed these derived files from the working folder. They are still in Git; to get one back:

```bash
git checkout 4623777 -- data/<file name>      # for example data/training_ol_books.csv
```

| Removed file | Rows | What it was |
|---|---:|---|
| `training_ol_books.csv` | 20,271 | All books with an Open Library work link (5,271 older + 15,000 new) |
| `training_ol_books_with_description.csv` | 17,763 | The description-ready subset of the file above |
| `training_with_descriptions.csv` | 3,152 | An early subset of `training_api.csv` that had usable descriptions |
| `openlibrary_ids_5600.csv` | 5,600 | The Open Library work/edition IDs of the 5,600 books (IDs taken from the archive.org metadata) |
| `popularity_training_exclusions.csv` | 2,544 | The books removed when the clean dataset was made, with the reason |
| `training_api_not_usable.csv` | 0 | Header only (no unusable training rows) |

## Removed helper scripts (still in Git history)

`scrapers/` keeps only what produces the five CSV files: the three scrapers (`ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py`) with their helpers (`ia_common.py`, `config.py`, `genres.py`, `descriptions.py`), `finalize_datasets.py` and `compare_runs.py` (they build the three benchmark CSVs and `training_api.csv` from `data/runs/`), `prepare_popularity_dataset.py` (builds `popularity_training_clean.csv`) and `check_selenium_env.py`.
These scripts were removed because they only made the intermediate files above: `build_manifest.py`, `build_training_manifest.py`, `build_ol_manifest.py` (choose the books; the chosen lists are kept in `data/manifest/`), `fetch_descriptions.py`, `fetch_openlibrary_ids.py`, `build_description_dataset.py`, `build_ol_dataset.py`. Get one back with `git checkout 4623777 -- scrapers/<file name>`.

Notebooks 08, 09 and 10 do **not** need these files. Notebook 05 reads `openlibrary_ids_5600.csv` and the scripts that rebuilt the intermediate files were removed too; restore what you need from Git first if you want to rerun those steps.
