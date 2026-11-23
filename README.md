# Internet Archive book scraping project (Network Programming lab)

We compare three ways of collecting the same 200 Internet Archive books (API, Requests + BeautifulSoup, Selenium), measure what each one does on the network, and use the data we collected to predict how popular a book is.

**Team:** Mohammad owns the scrapers, the data and the machine learning. Issa owns the networking and security measurements. The final report and presentation are shared. Deadline: **25 November 2026**.

## What is in this repository (the deliverables)

| Deliverable | Where |
|---|---|
| Three scraper scripts | `scrapers/ia_api_scraper.py`, `scrapers/ia_bs4_scraper.py`, `scrapers/ia_selenium_scraper.py` |
| Networking analysis notebook (with screenshots) | `notebooks/network_analysis.ipynb`, screenshots in `screenshots/` |
| ML notebooks | `notebooks/05_...`, `08_...`, `09_...`, `10_...` (see `notebooks/README.md`) |
| Final report | `report/Lab_Network_Final_Report.docx` (export it to PDF for submission) |
| Presentation (10 min) | `report/Lab_Network_Presentation.pptx` |

## Main results

**Network (200 books, one run per method, measured on a Mac):**

| Method | Time | Data on the network | Records |
|---|---:|---:|---:|
| API | 31.0 s | 163.2 KB | 200 / 200 |
| BeautifulSoup | 27.7 min | 11.37 MB | 200 / 200 |
| Selenium | 28.5 min | 18.63 MB (8,933 browser requests) | 200 / 200 |

**Machine learning** (17,727 books, grouped by Open Library work, same folds and a locked holdout; results describe how much an *archived copy* was viewed, not sales):

| Task | Without description | With description |
|---|---:|---:|
| Popularity, 3 classes, baseline (notebook 05) | 57.35% | 59.35% |
| Popularity, 3 classes, improved with author history (notebook 10) | 61.54% | 62.84% |
| Genre: science fiction / fantasy / mystery (notebook 09) | 70.8% | 86.26% |
| Archive "juvenile" marker | 71.9% | 82.54% |
| Intended for children (provisional AI labels, 291-book fresh test) | 75.3% | 85.57% |

The majority-class baseline for popularity is 35.2%. We did **not** reach 80% for popularity. The genre, juvenile and children numbers are different, easier tasks and must not be presented as popularity accuracy. The children labels were made by an AI model under written rules; an 80-book sheet for a human check is in `report/ml/children/review/`. A small neural network was tested for every task and was never better than the simple models.

## Data (`data/`)

Only five CSV files are kept. See [data/README.md](data/README.md) for what every file and folder is, and for how to bring back the removed intermediate files from Git history.

| File | Rows | What it is |
|---|---:|---|
| `benchmark_200_api.csv`, `benchmark_200_bs4.csv`, `benchmark_200_selenium.csv` | 200 each | The same 200 books collected with each method |
| `training_api.csv` | 5,600 | First training set (API): 200 benchmark books + 1,800 per genre |
| `popularity_training_clean.csv` | 17,727 | Final clean dataset for the ML (37 columns, split by `ol_group`) |

Raw run folders are in `data/runs/`, the frozen lists of chosen books in `data/manifest/`, the children-audience labels in `data/labels/`, and the checksums of the five CSVs in `data/checksums.sha256`. The data dictionary is in [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).

## Repository layout

| Folder | Content |
|---|---|
| `scrapers/` | The three collectors with their shared helpers (`ia_common.py`, `config.py`, `genres.py`, `descriptions.py`), `finalize_datasets.py` and `compare_runs.py` (build the CSVs from the run folders), `prepare_popularity_dataset.py` (builds the clean dataset) and `check_selenium_env.py` |
| `notebooks/` | The analysis notebooks and their helper `.py` files; `README.md` there says which notebook uses which file |
| `report/` | The final report, network measurement CSVs, `ml/` (saved results, figures, split manifests) and `figures/` |
| `screenshots/` | Network screenshots (Issa), scraper terminal runs (`scrapers/`) and notebook screenshots (`ml/`) |
| `measurements/`, `captures/` | Small demo run outputs; packet captures go in `captures/` |
| `docs/` | Data dictionary, assignment requirements, Mac capture notes, label rules, how to reopen the notebooks |
| `tests/` | 32 offline tests (HTTP client, retries, parsers, threading limit, description cleaning, cohort) |
| `run_mac_*.sh` | Issa's scripts for the Mac baselines and the PF firewall demo |

## How to run

**Scrapers** (needs `pip install -r requirements.txt`; the default input is the fixed 200-book list):

```bash
python scrapers/check_selenium_env.py
python scrapers/ia_api_scraper.py --out-root measurements/runs --label net_run1
python scrapers/ia_bs4_scraper.py --out-root measurements/runs --label net_run1
python scrapers/ia_selenium_scraper.py --out-root measurements/runs --label net_run1
```

Use `--limit 3` for a small test. All three accept `--workers N` and `--min-interval S`: request starts from all workers share one limiter, so threads can never go faster than the rate limit (3 s by default). A 429/503 slows every worker and a 403 or verification page stops them all.

**Offline tests** (no website requests): `python -B -m unittest discover -s tests -v` (32 tests) and, for the notebook helpers, `cd notebooks && python -B -m unittest discover -s tests -v` (12 tests).

**Notebooks:** install `requirements-analysis.txt`, run them from `notebooks/` and keep `RETRAIN = False` at the top. The fitted models are saved in `report/ml/models/` (not in Git), so reopening a notebook does not retrain; see [docs/REOPENING_NOTEBOOKS.md](docs/REOPENING_NOTEBOOKS.md). Notebook 05 also needs `data/openlibrary_ids_5600.csv`, which was removed (restore it from Git history, see `data/README.md`).

## Rules we followed and limits

- Identifying User-Agent, 3-second pacing, bounded retries; `Retry-After` is respected and a long wait stops the run. Failures and source differences stay visible.
- Models are chosen by cross-validation on the training pool only, copies of the same work stay in the same fold, and the locked test set is scored once. The improved popularity result in notebook 10 was compared on a holdout that notebook 05 had already looked at, so it is a comparison and not a fresh test.
- Views describe engagement with an archived copy, not worldwide sales or future success. API views exceed page views for 195 of the 200 benchmark books; the differences are kept.
- The network measurements are single runs on one Mac (macOS `lsof` and `pf` stand in for Linux `ss` and `ufw`).
- Earlier experiments, handoff notes and intermediate files were removed from the repository; they remain in the Git history.
