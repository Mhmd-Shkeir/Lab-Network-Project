# Internet Archive book scraping project

Compare API, Requests/BeautifulSoup and Selenium collection of the same 200 Internet Archive books. Use a separate 5,600-record API dataset for exploratory analysis and estimating existing archived-item engagement.

Mohammad owns the scrapers and collection. Issa owns networking measurements. Both own cleaning, ML, the final report and presentation. The assignment deadline is **25 November 2026**.

## Start here

1. **Issa:** [Ubuntu setup](docs/SETUP_UBUNTU_VM.md), then [networking handoff](docs/HANDOFF_NETWORKING_ISSA.md).
2. **Data and ML:** use `data/training_api.csv`; read the [data dictionary](docs/DATA_DICTIONARY.md).
3. **Remaining work:** [project checklist](LABNET_PROJECT_CHECKLIST.md) and [assignment requirements](docs/ASSIGNMENT_REQUIREMENTS.md).

## Collected data

| File in `data/` | Rows | Purpose |
|---|---:|---|
| `benchmark_200_api.csv` | 200 | API collection of the fixed benchmark books |
| `benchmark_200_bs4.csv` | 200 | Independent HTML collection of the same books |
| `benchmark_200_selenium.csv` | 200 | Browser collection of the same books |
| `training_api.csv` | 5,600 | 200 benchmark books plus 1,800 science fiction, 1,800 fantasy and 1,800 mystery/thriller records (each genre: 600 from Americana + 1,200 from other English texts on archive.org) |

All rows have collection status `ok`. This means the required fields were obtained; source metadata and genre labels still need analysis. There are 5,391 training work groups, with at most three archived items per group. Split training and evaluation by `work_group`.

**Two sources inside the training set:** the first 2,000 rows are Americana books (published earlier, unchanged); the other 3,600 come from the wider English-text pool on archive.org, because Americana alone could supply only about 1,280 fantasy books. They are flagged by `in_americana`. Their views are much lower (median 97 views versus 285 for the Americana genre books), so this flag matters for EDA and modelling; check it in a train/test split and by genre. Genre labels are rule-based on subject tags and a few non-genre items remain (for example a cross-stitch pattern book tagged fantasy).

**Adding more later (a fourth genre, or more per genre):** add the genre to `scrapers/genres.py`, then `python scrapers/build_training_manifest.py --extend --scope all_texts --per-genre N` and collect only the new ids with `ia_api_scraper.py --ids data/manifest/training_ids_extension_ids.json`; existing rows are kept.

The benchmark is a reproducible sample from Americana's broad English-fiction pool; the additional training records use explicit genre rules. Selection metadata, frozen ID lists, compressed pool snapshots and exclusions are in `data/manifest/`. Do not rebuild the benchmark for networking runs.

All benchmark metadata agrees across methods except one subject list. API views exceed page views for 195 of 200 books; BS4 and Selenium agree on the observed page values. These differences are preserved. Views describe engagement with an archived copy, rather than worldwide sales or future publication success.

`data/completeness_report.md` documents quality checks. `data/checksums.sha256` verifies the five published CSVs, including the header-only `training_api_not_usable.csv` (zero unusable training records). Excel can open these UTF-8 CSVs; keep identifiers as text.

## Run the scrapers

Install the scraping dependencies in a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scrapers/check_selenium_env.py
```

For Issa's measurements, run all three methods in the **same Linux environment**, using fresh output folders:

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
| `data/runs/` | Four final collection runs: raw checkpoints, attempts and summaries; identical benchmark CSV copies are omitted |
| `docs/` | Setup, networking handoff, data dictionary and assignment requirements |
| `tests/` | Offline HTTP-client, parser, median, simulated browser-retry and threading/global-limit tests (24 tests) |
| `notebooks/`, `captures/`, `screenshots/`, `report/` | Destinations for the remaining assignment deliverables |

Analysis packages are in `requirements-analysis.txt`. Run offline tests with `python -B -m unittest discover -s tests -v`; they use a local fake server and a simulated browser, without archive.org requests.

## Threaded mode (bounded, one global request limit)

All three scrapers accept `--workers N` (1–8; Selenium 1–4, one Chrome per worker) and `--min-interval S` (at least 0.5). Request **starts** (including retries) from
all workers share one limiter and are at least `S` seconds apart, so the total rate is at most 1/`S` whatever `N` is; a 429/503 slows and pauses every worker, and
a 403 or verification page stops them all. Without `--workers` the scrapers stay sequential (3 s after the end of each request). Offline tests use local fake servers;
the option has **not** been run against archive.org. Commands and what to check in `run.json` are in the networking handoff.

```bash
python scrapers/ia_bs4_scraper.py --workers 4 --min-interval 1 --out-root measurements/runs --label thr_w4_i1_run1
```

## Remaining implementation

The live threading and rate-limit experiments, and a proxy (optional), are Issa's. Ubuntu ARM browser setup remains untested; confirm the local browser check before collecting measurements.

Use the project's identifying User-Agent, three-second pacing and bounded retry/backoff. Respect `Retry-After`; a long wait stops the run. Keep failures and source differences visible. Browser request-event totals and client-call durations have distinct meanings explained in the networking handoff.

Earlier experiments and superseded plans are preserved in the [project history](HISTORY.md) and the verified local backup; they are removed from the active handoff.
