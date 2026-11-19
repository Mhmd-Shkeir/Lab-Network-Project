# Lab Network Project: scraping efficiency and popularity of Internet Archive books

Compare three ways of collecting the same book data from **Internet Archive** (archive.org): a Selenium browser scraper,
an independent Requests + BeautifulSoup scraper, and an API scraper. Measure their network behaviour (time, bandwidth, requests,
latency, with `ss`, `iftop`/`nload`, `tcpdump`, Wireshark), test firewall/rate-limit/threading behaviour, then use the data
for EDA and machine learning (predict low/medium/high popularity and approximate view counts of already-published books;
K-Means as an additional exploratory analysis).

Team: Mohammad Ali Shkeir (scrapers, data collection), Issa Tawil (networking). Cleaning, EDA, ML, report and presentation: both.
Deadline: Wed 25 Nov 2026. Checklist: [LABNET_PROJECT_CHECKLIST.md](LABNET_PROJECT_CHECKLIST.md). Plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## Source and sample
- Source: Internet Archive, Americana collection. Pool query (frozen in `data/manifest/manifest_meta.json`):
  `collection:americana AND mediatype:texts AND language:eng AND subject:fiction AND creator:* AND year:[1800 TO 2020] AND imagecount:[50 TO 1500]`
  → 25,722 items on 19 Nov 2026 (snapshot saved with SHA-256).
- **Benchmark: 200 books**, random (order `sha256("2026:<identifier>")`), all distinct works, collected independently by all three methods.
- **Training: 2,000 books** = the same 200 benchmark books (re-collected through the API, kept separate from the benchmark CSVs) + **600 science fiction +
  600 fantasy + 600 mystery/thriller** Americana books. Genre labels come only from explicit subject-tag rules (`scrapers/genres.py`);
  a book matching several genres gets one primary genre (precedence science fiction > fantasy > mystery/thriller) and keeps all matches as flags
  (126 of the 2,000 match more than one). Criticism, teaching guides, bibliographies, reference works and magazine issues are excluded where
  identifiable (190 books; reasons in `data/manifest/genre_exclusions.csv`). Books are drawn in hash order, **not** ordered by views or downloads.
- Duplicate handling: no duplicate identifiers; copies/volumes/editions share a `work_group` (normalised main title + first creator's surname),
  at most 3 per group. **Split train/test by `work_group`.**
- Views are engagement with one archived copy, not worldwide popularity or sales. `subject:fiction` also matches some non-fiction about fiction.

## Results of the collection (19 Nov 2026)
| | Records | Status |
|---|---:|---|
| `benchmark_200_api.csv` | 200 | 200 ok |
| `benchmark_200_bs4.csv` | 200 | 200 ok |
| `benchmark_200_selenium.csv` | 200 | 200 ok |
| `training_api.csv` | 2,000 | 2,000 ok (200 benchmark + 600 + 600 + 600), 1,947 work groups, 0 failures |

- Across the three methods all fields are identical for the 200 books **except** (a) `views_all_time`: the API is higher than the page counter for
  **195 of 200** books (by 1–82, median 2; BS4 and Selenium agree on all 200), and (b) one book whose subject list differs in one tag
  (`James, Henry <1843-1916>` on the page). These differences are kept, not corrected.
- Training views: min 7, median 282, max 184,689; each genre spans the low, medium and high ranges (see `data/completeness_report.md`).
  No zero-view book occurs (the Views API returned data for every selected book, so any genuine zero would have been kept).
- The first BS4/Selenium run had 3 rows without a publication year (`c1920`-style dates) and 5 format differences (microsecond timestamps, an unmapped language name)
  caused by my parser; I fixed it and re-collected the same 200 books. The first run is preserved in `data/history/benchmark_first_html_runs_parser_defects/`.
- Collection timings (pilot, include 3 s waits): API 8 requests, 32 s; BS4 200 requests, 881 s (577 s of it deliberate pacing, 45.8 MB decoded HTML);
  Selenium 200 navigations, 946 s, median 50 browser requests per page, 33.3 MB browser-reported (first page 3.8 MB into an empty profile, median 144 KB).
  Training: 80 API requests, 323 s.

Timings in the run folders are collection timings that include deliberate 3 s waits; they are pilot results, **not** the final network comparison.

## Repository layout
| Path | Content |
|---|---|
| `scrapers/ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py` | The three scrapers (separate, runnable, same fields, same ids) |
| `scrapers/ia_common.py`, `config.py` | Pacing, retries/backoff/Retry-After, logging, checkpoints, parsing; settings (environment-variable overrides) |
| `scrapers/build_manifest.py` (benchmark), `build_training_manifest.py` + `genres.py` (genre training set), `compare_runs.py`, `finalize_datasets.py`, `check_selenium_env.py` | Manifests and genre rules, comparison, final CSVs + completeness report, Selenium environment check |
| `data/manifest/` | Pool and genre snapshots, `benchmark_200_ids.json`, `training_ids.json`, genre availability/preview, exclusions, views eligibility checks, sampling metadata |
| `data/benchmark_200_{api,bs4,selenium}.csv`, `data/training_api.csv` | Final CSVs (Excel-readable) |
| `data/benchmark_200_comparison/`, `data/completeness_report.md` | Method comparison, completeness checks |
| `data/runs/` | Run folders: `records.jsonl` (checkpoint), `attempts.csv/.jsonl` (per attempt), `run.json` |
| `docs/DATA_DICTIONARY.md` | Every column and file |
| `docs/SETUP_UBUNTU_VM.md`, `docs/HANDOFF_NETWORKING_ISSA.md` | Setup (incl. Ubuntu VM on a MacBook) and what to run for the measurements |
| `tests/` | Offline tests of retry/backoff/abort logic (`python -m unittest discover -s tests -v`) |
| `HISTORY.md`, `docs/history/`, `data/history/`, `legacy/` | Earlier experiments (Open Library, other sources, 10-record pilot), kept as evidence |
| `captures/`, `screenshots/`, `notebooks/`, `report/` | For the networking/ML work (pcap files are not committed) |

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scrapers/check_selenium_env.py                  # Selenium/Chrome works here? (see docs/SETUP_UBUNTU_VM.md)
python scrapers/ia_api_scraper.py      --limit 10 --label try     # each run -> new folder in data/runs/
python scrapers/ia_bs4_scraper.py      --limit 10 --label try
python scrapers/ia_selenium_scraper.py --limit 10 --label try     # add --headless without a desktop
```
Without `--limit`, the 200 benchmark books are collected. Use `--out-root measurements/runs` for measurement runs so the committed collection runs stay untouched.

## Responsible access
Descriptive User-Agent (tool, version, model, as the [Internet Archive bots guide](https://archive.org/developers/bots.html) asks),
3 s gap between requests, retries with exponential backoff + jitter, `Retry-After` honoured, automatic slow-down on 429/503, and a hard stop on
HTTP 403, a verification page, an over-long `Retry-After` or 5 failed records in a row. Nothing is bypassed, spoofed or cached between runs.
A method that misses a value leaves it blank; values are never copied from another method.
