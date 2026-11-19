# Internet Archive book scraping project

Compare API, Requests/BeautifulSoup and Selenium collection of the same 200 Internet Archive books. Use a separate 2,000-record API dataset for exploratory analysis and estimating existing archived-item engagement.

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
| `training_api.csv` | 2,000 | 200 benchmark books plus 600 science fiction, 600 fantasy and 600 mystery/thriller records |

All rows have collection status `ok`. This means the required fields were obtained; source metadata and genre labels still need analysis. There are 1,947 training work groups, with at most three archived items per group. Split training and evaluation by `work_group`.

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
| `tests/` | Offline HTTP-client, parser, median and simulated browser-retry tests |
| `notebooks/`, `captures/`, `screenshots/`, `report/` | Destinations for the remaining assignment deliverables |

Analysis packages are in `requirements-analysis.txt`. Run offline tests with `python -B -m unittest discover -s tests -v`; they use a local fake server and a simulated browser, without archive.org requests.

## Remaining implementation

Multithreading and its globally paced comparison are still required; the current scrapers are sequential. Implement and test that option before the threading experiment. A proxy is optional. Ubuntu ARM browser setup remains untested; confirm the local browser check before collecting measurements.

Use the project's identifying User-Agent, three-second pacing and bounded retry/backoff. Respect `Retry-After`; a long wait stops the run. Keep failures and source differences visible. Browser request-event totals and client-call durations have distinct meanings explained in the networking handoff.

Earlier experiments and superseded plans are preserved in the [project history](HISTORY.md) and the verified local backup; they are removed from the active handoff.
