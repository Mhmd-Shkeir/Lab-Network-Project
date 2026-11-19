# History: earlier experiments (kept as evidence, not used by the final scrapers)

The notes below were written on 19 Nov 2026 during source selection. Paths **inside** these notes use the old locations;
files were moved (`data/<folder>` → `data/history/<folder>`, root notes → `docs/history/`, old scripts → `legacy/`).

| Step | What happened | Evidence |
|---|---|---|
| Open Library (first choice) | API and visible Selenium matched on 10 works; independent Requests/BS4 got the human-verification page, and Open Library asks clients not to scrape HTML. We stopped requesting openlibrary.org and did not try to bypass anything. | `docs/history/CLAUDE_HANDOFF_2026-11-19.md`, `docs/history/SCRAPING_TEST_RESULTS_2026-11-19.md`, `data/history/feasibility_2026-11-19_185334/`, `data/history/selenium_retry_2026-11-19_192825/` |
| Other sources | dBooks (1 book matched by all 3 methods, no popularity label), LibriVox (works, but robots.txt carries an `ai-train=no` signal), Open Textbook Library (crawl-delay 120 s) | `docs/history/SOURCE_OPTIONS_CHECK_2026-11-19.md`, `data/history/source_checks_2026-11-19/` |
| Goal change | Popularity (low/medium/high and approximate views) needs a measured label → Internet Archive has the official Views API | `docs/history/POPULARITY_GOAL_SOURCE_CHECK_2026-11-19.md`, `data/history/popularity_source_check_2026-11-19/` |
| Internet Archive pilot | 10 records, API / BS4 / Selenium, one run. API 5.5 s, BS4 75.4 s, Selenium 67.9 s (3 s sleeps included; one slow request per HTML method). Views API 1–48 higher than the page counter on 10/10. | `docs/history/ARCHIVE_TIMED_PILOT_HANDOFF_2026-11-19.md`, `docs/history/PROJECT_UPDATE_BEFORE_COLLECTION_2026-11-19.md`, `data/history/archive_timed_pilot_2026-11-19/` (raw HTML pages not committed) |
| Random training list (superseded) | A first training list of 2,000 random Americana fiction books was built and 400 were collected before the design changed to genre strata | `data/history/superseded_random_fiction_training/` |
| First HTML benchmark run (parser defects) | BS4/Selenium had 3 partial rows (`c1920` dates not read) and 5 timestamp/language format differences; parser fixed, same 200 books re-collected | `data/history/benchmark_first_html_runs_parser_defects/` |
| PDF audit | Checklist of the assignment's explicit requirements | `docs/PDF_REQUIREMENTS_AUDIT_2026-11-19.md` |

`legacy/` holds the Open Library scripts and the first Selenium check. They contain machine-specific browser paths and are **not** portable; the
current, portable scripts are in `scrapers/`.

The pilot timings are pilot results only. The final network comparison is produced by re-running the scrapers under packet capture
(`docs/HANDOFF_NETWORKING_ISSA.md`).
