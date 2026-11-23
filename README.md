# Internet Archive book scraping project

Compare API, Requests/BeautifulSoup and Selenium collection of the same 200 Internet Archive books. Use the completed 20,271-item Open Library-linked API dataset (17,763 description-ready items) for the next analysis; the earlier 5,600-record dataset and its exploratory results are preserved.

Mohammad owns the scrapers and collection. Issa owns networking measurements. Both own cleaning, ML, the final report and presentation. The assignment deadline is **25 November 2026**.

## Start here

1. **Networking (Issa):** `notebooks/network_analysis.ipynb`, the `run_mac_*.sh` scripts and [the Mac capture notes](docs/MAC_NETWORK_CAPTURE.md).
2. **Data and ML:** for the description/no-description popularity comparison use `data/popularity_training_clean.csv` (17,727 complete-case rows). Use `data/training_ol_books.csv` for the full linked dataset, and split by `ol_group`. Read the [dataset note](data/training_ol_books_README.md) and [data dictionary](docs/DATA_DICTIONARY.md). Existing notebook scores are from the earlier datasets.
3. **Report and requirements:** the final report is `report/Lab_Network_Final_Report.docx`; the [assignment requirements](docs/ASSIGNMENT_REQUIREMENTS.md) list what is asked.

## Collected data

| File in `data/` | Rows | Purpose |
|---|---:|---|
| `benchmark_200_api.csv` | 200 | API collection of the fixed benchmark books |
| `benchmark_200_bs4.csv` | 200 | Independent HTML collection of the same books |
| `benchmark_200_selenium.csv` | 200 | Browser collection of the same books |
| `training_api.csv` | 5,600 | 200 benchmark books plus 1,800 science fiction, 1,800 fantasy and 1,800 mystery/thriller records (each genre: 600 from Americana + 1,200 from other English texts on archive.org) |
| `popularity_training_clean.csv` | 17,727 | The final clean dataset used by the ML notebooks (complete required inputs; same books for both popularity-model variants). Split by `ol_group` |

Only these five CSV files are kept. Intermediate files of the collection (for example the 20,271-row Open Library-linked export) were removed from the working folder and remain in Git history; see [data/README.md](data/README.md) for what each one was and how to restore it. Numbers below that mention them describe those removed files.

The earlier 5,600 rows have collection status `ok`, meaning the collector completed its required-field checks. This is not a guarantee of catalogue quality: eight creator values are the literal text `None`, which must be treated as missing in analysis. Source metadata and genre labels still need analysis. There are 5,391 training work groups, with at most three archived items per group. Split training and evaluation by `work_group`.

**Two sources inside the training set:** the first 2,000 rows are Americana books (published earlier, unchanged); the other 3,600 come from the wider English-text pool on archive.org, because Americana alone could supply only about 1,280 fantasy books. They are flagged by `in_americana`. Their views are much lower (median 97 views versus 285 for the Americana genre books), so this flag matters for EDA and modelling; check it in a train/test split and by genre. Genre labels are rule-based on subject tags and a few non-genre items remain (for example a cross-stitch pattern book tagged fantasy).

**Adding more later (a fourth genre, or more per genre):** add the genre to `scrapers/genres.py`, then `python scrapers/build_training_manifest.py --extend --scope all_texts --per-genre N` and collect only the new ids with `ia_api_scraper.py --ids data/manifest/training_ids_extension_ids.json`; existing rows are kept.

The benchmark is a reproducible sample from Americana's broad English-fiction pool; the additional training records use explicit genre rules. Selection metadata, frozen ID lists, compressed pool snapshots and exclusions are in `data/manifest/`. Do not rebuild the benchmark for networking runs.

All benchmark metadata agrees across methods except one subject list. API views exceed page views for 195 of 200 books; BS4 and Selenium agree on the observed page values. These differences are preserved. Views describe engagement with an archived copy, rather than worldwide sales or future publication success.

`data/completeness_report.md` documents the earlier dataset checks; `data/archive/training_ol_books_report.json` documents the completed larger dataset. `data/checksums.sha256` verifies the five kept CSV files. Excel can open these UTF-8 CSVs; keep identifiers as text.

## Analysis notebooks and current results

Install `requirements-analysis.txt` separately from the scraping environment. The notebooks have saved outputs, but the current review did not retrain their models. In particular, the corrected final summary cell in `02_popularity_methods.ipynb` needs re-execution.

| Notebook | Purpose and status |
|---|---|
| `notebooks/05_popularity_description_comparison.ipynb` | Main completed experiment: 17,727 items, same A/B folds, 3,006 fresh held-out items. CV-selected LogReg accuracy 57.35% without descriptions / 59.35% with; Ridge R² on log views 0.3997 / 0.4186. MLP also tested; it did not beat the selected linear models. Section 9 is a runnable manual-input demo: enter a title/description and optional metadata to compare predictions |
| `notebooks/ml_analysis1.ipynb` | Executed overview: cleaning checks, EDA, baselines, grouped evaluation, learning curves and exploratory K-Means |
| `notebooks/02_popularity_methods.ipynb` | Existing archived-item engagement: CV-selected classifier has 59.5% held-out accuracy versus 30.1% baseline; selected regression ensemble has R² 0.401 on log views, with 61.1% within a factor of two |
| `notebooks/03_children_book_classifier.ipynb` | Exploratory detection of the catalogue's juvenile marker; missing juvenile tags do not establish that a book is for adults. Report F1, balanced accuracy and AUC, not plain accuracy alone |
| `notebooks/04_genre_classifier.ipynb` | Genre classification: the current description-based LinearSVC has 86.26% held-out accuracy and 0.859 macro-F1 (see `report/ml/phase2/genre_classical_test_results.csv`). Input features exclude the subject tags that defined the genre labels |
| `notebooks/ml_analysis.ipynb` | Unexecuted starter retained for reference; not the completed analysis |

Genre accuracy is not popularity accuracy. These are exploratory results on the existing datasets. Use training-pool cross-validation for model choices, keep copies of a work in the same fold, and do not keep tuning against a reused test set. Author overlap and rule-based catalogue labels limit generalisation. Some descriptions still contain catalogue notes or contents lists; the 3,152-item subset covers about 56% of the original training data, so compare description/no-description models on the same books.

### Recorded paired-model results and manual book entry

`report/ml/` contains the fixed split manifest, CV selections, saved predictions, per-genre results, grouped bootstrap intervals, training times and figures for notebook 05. Of the 17,727 complete-case items, 14,721 are the training pool and 3,006 are held out; no held-out Open Library work appears in the earlier 5,600-item set. Model settings were selected using training-pool CV before the holdout was scored. The recorded classifier baseline is 35.20% accuracy. With descriptions, LogReg gains about 2.0 percentage points (group-bootstrap interval approximately +0.7 to +3.4); the neural-network result is about 56.4% in either variant. These are existing-archive engagement results, not new-book forecasts.

Section 9 lets you try a book by hand: run Setup once, edit `BOOK` (title and description, plus optional author/year/pages/genre/subjects/archive age), then run Predict. The setup refits only the recorded CV-selected LogisticRegression/Ridge pairs on the saved training pool; subsequent entries reuse those models. It makes no website requests and does not rerun CV, fit holdout targets, change datasets or overwrite experiment results. Missing optional metadata uses visible training-pool defaults. A blank description returns only the metadata prediction. These are estimates of existing archived-item views at the supplied/assumed archive age, not forecasts of new-book sales.

Section 10 contains two runnable real Archive examples with complete saved metadata: **Fahrenheit 451** (`fahrenheit4510000brad`, training pool; 19,245 observed views) and **The Time Machine and the Invisible Man** (`timemachineinvis0000well_p4k8`, held-out work; 87 observed views). Run the updated Setup first, then either example cell. The helper verifies item/work training membership, predicts from metadata, and only then attaches the saved observed views/class and absolute count error. The recorded views are snapshot values, not a live website lookup. These two examples illustrate behaviour; the training example is not generalisation evidence and neither replaces the full held-out metrics. The section 9 preset now uses the real training example rather than the fictional Lighthouse example.

The separate children-audience experiment scored 85.57% on a 291-item fresh test, but its labels are AI-generated and not human validated. An 80-item blind review sheet is provided; complete it before claiming validated intended-audience performance. Genre and juvenile-marker scores above 80% are not popularity scores.

The original neural experiment's feature transforms were fitted before its internal early-stopping validation carve-out; that limitation remains part of the recorded experiment. The manual demo uses the selected linear models. Temporary result caches are ignored by Git, and result CSV bytes are preserved so manifest hashes work across platforms.

### Completed larger description collection

> **Note (tidy-up): the helper scripts `build_manifest.py`, `build_training_manifest.py`, `build_ol_manifest.py`, `build_ol_dataset.py`, `fetch_descriptions.py`, `fetch_openlibrary_ids.py` and `build_description_dataset.py` were removed from `scrapers/` (see `data/README.md`; they are in Git history).**
>
> **Note (tidy-up) on the files below:** `training_ol_books.csv`, `training_ol_books_with_description.csv` and the other intermediate CSV files named in this section were removed from `data/` (they are still in Git history; see `data/README.md` to restore one). The final dataset for the models is `data/popularity_training_clean.csv`, and the raw collection is in `data/runs/`.

The 15,000-item API run completed on 22 November 2026: **15,000 unique items collected**, 5,000 per genre, in 47 minutes 26 seconds. It made 600 successful requests and recovered from 10 failed attempts through retries. These are collection timings, not the final networking benchmark. The source remains **archive.org's API**; the Open Library IDs are links in the metadata.

`data/training_ol_books.csv` combines these records with 5,271 Open Library-linked items from the older dataset: **20,271 unique items**, with 37 columns. `data/training_ol_books_with_description.csv` contains the **17,763 description-ready items**, including 14,935 of the new records. Sixty-five new records failed the final description checks; the raw records are preserved. Forty-two full-dataset records have a missing author, explicitly flagged by `author_missing` (36 are in the description-ready subset).

Use `ol_group` (the Open Library work ID) for grouped evaluation: there are 19,011 works overall and 16,702 in the description-ready subset. Four older work groups exceed the proposed three-item cap, with a maximum of six; keep them together rather than treating copies as independent books. The 329 older items without an Open Library work link are excluded from this linked export, not deleted from the original dataset. The 200-book networking benchmark is unchanged.

The snapshot contained 41,849 candidates; initial checks retained 19,607 new candidates, from which the frozen manifest selected 15,000. Description-ready status is an automated filter, not a manual guarantee of summary quality. Compare description/no-description models on the same items and splits; larger data does not guarantee higher accuracy. The paired larger-dataset experiment is complete in `notebooks/05_popularity_description_comparison.ipynb`; section 9 provides editable book inputs and a prediction cell; the original experiment results are preserved.

Collection checkpoints and attempt logs are in `data/runs/api_20261122_154837_ol15000/`. `scrapers/build_ol_dataset.py --new-run data/runs/api_20261122_154837_ol15000` rebuilds the enriched exports from saved files without website requests. See the [dataset note](data/training_ol_books_README.md) for columns, source differences and exclusions.

Published CSVs are stored byte-for-byte using `.gitattributes`, so Git does not change their line endings and invalidate checksums between Windows and Linux.

## Clean cohort for the popularity comparison

`python scrapers/prepare_popularity_dataset.py` builds `data/popularity_training_clean.csv` offline, retaining 17,727 rows / 16,666 works and all 37 columns from the full linked export. It excludes 2,508 rows failing description checks plus 36 further rows missing authors (2,544 excluded IDs total). Other required inputs are present and valid. The source exports are unchanged. Optional blank edition IDs and successful rows' empty `error` fields are allowed; zero views is valid. See `data/popularity_training_quality.json` and `data/popularity_training_exclusions.csv` for the checks and reasons.

Use this same cohort for the with-description and without-description variants, and reuse one grouped split. The experiment rules (written when the data was prepared) define targets, permissible features, a fresh holdout drawn from new work groups, train-only model selection, paired evaluation and outputs. It includes a small neural network in both feature variants, with grouped early-stopping validation and comparisons against the linear/tree baselines. The cleaning step does not train models. The subsequent completed paired experiment is in `notebooks/05_popularity_description_comparison.ipynb`.

## Run the scrapers

Install the scraping dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrapers/check_selenium_env.py
```

For a reproducible measurement rerun, the original handoff commands below use fresh output folders. The completed evidence in this project was captured on macOS; see [the network report](report/report_draft.md), [capture procedure](docs/MAC_NETWORK_CAPTURE.md), and screenshots. macOS `lsof`/PF were used, so Linux `ss`/UFW compliance is not claimed:

```bash
python scrapers/ia_api_scraper.py --out-root measurements/runs --label net_run1
python scrapers/ia_bs4_scraper.py --out-root measurements/runs --label net_run1
python scrapers/ia_selenium_scraper.py --out-root measurements/runs --label net_run1
```

The default input is the fixed 200-book manifest. Use `--limit 3` for an initial smoke check. Follow the handoff to capture traffic while the scrapers run. Saved collection timings are **not the final network benchmark**.

## Repository contents

| Folder | Content |
|---|---|
| `scrapers/` | Three collectors, shared client/configuration, manifest builders, comparison/export tools and browser check |
| `data/` | Published CSVs, quality reports and checksums |
| `data/manifest/` | Frozen benchmark/training IDs, snapshots, genre rules evidence and exclusions |
| `data/runs/` | Collection checkpoints, raw records, attempts and summaries; keep active-run outputs local until completion and validation |
| `docs/` | Setup, networking handoff, data dictionary and assignment requirements |
| `tests/` | Offline HTTP-client, parser, median, simulated browser-retry and threading/global-limit and description-cleaning/cohort tests (32 tests) |
| `notebooks/`, `captures/`, `screenshots/`, `report/` | Executed ML experiments and destinations for network evidence, screenshots and the final report |

Manual-entry helper checks use the analysis environment: `python -B -m unittest discover -s notebooks/tests -v` (4 tests). The runnable demo was also checked against six saved reference predictions.

Analysis packages are in `requirements-analysis.txt`. Run offline tests with `python -B -m unittest discover -s tests -v`; they use a local fake server and a simulated browser, without archive.org requests.

## Threaded mode (bounded, one global request limit)

All three scrapers accept `--workers N` (1–8; Selenium 1–4, one Chrome per worker) and `--min-interval S` (at least 0.5). Request **starts** (including retries) from
all workers share one limiter and are at least `S` seconds apart, so the total rate is at most 1/`S` whatever `N` is; a 429/503 slows and pauses every worker, and
a 403 or verification page stops them all. Without `--workers` the scrapers stay sequential (3 s after the end of each request). Offline tests use local fake servers;
the option has **not** been run against archive.org. Commands and what to check in `run.json` are in the networking handoff.

```bash
python scrapers/ia_bs4_scraper.py --workers 4 --min-interval 1 --out-root measurements/runs --label thr_w4_i1_run1
```

## Network evidence and report

The API, BS4, and Selenium 200-item Mac baselines, Wireshark captures/screenshots, rate-limit comparison, and macOS PF block/recovery demonstration are complete. The measurements are single-run observations and the report documents their scope and platform limitations. See [the final report](report/report_draft.md), [PDF](output/pdf/lab_network_programming_report.pdf), and [project checklist](LABNET_PROJECT_CHECKLIST.md). Three repeats per method and the optional proxy remain outstanding.

Use the project's identifying User-Agent, three-second pacing and bounded retry/backoff. Respect `Retry-After`; a long wait stops the run. Keep failures and source differences visible. Browser request-event totals and client-call durations have distinct meanings explained in the networking handoff.

Earlier experiments, handoff notes and superseded plans were removed from the repository; they remain in the Git history.

### Reopening ML demos without training

Notebooks 05?10 save their selected fitted models and preprocessing locally. Keep `RETRAIN = False`, run the demo Setup/Load cell, then the book example. See [reopening instructions](docs/REOPENING_NOTEBOOKS.md).
