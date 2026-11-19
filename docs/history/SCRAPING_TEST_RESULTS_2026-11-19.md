# Open Library scraping results — 19 November 2026

Latest retry after the user restarted the router. Used the same 10 science-fiction work IDs, one visible WSL Chrome session, no parallel page requests, and a two-second pause between books.

| Method | Verified result |
|---|---|
| API | Earlier collection saved 10 complete book records. Those records were reused for comparison; no fresh API calls in this retry. |
| Selenium | Collected all 10 books with title, author, first publication year, and edition count. All 10 rows exactly match the saved API CSV. No manual verification was needed in this retry. |
| Independent Requests + BeautifulSoup | Tested one book after Selenium finished. It redirected to human verification despite HTTP 200. Collected 0 records and stopped; the other 9 were not attempted. |
| Supplemental BS4 parsing | Successfully parsed all 10 Selenium-captured pages. This checks the parser, but is not independent live BS4 scraping. |

## What we faced

- Earlier attempts had timeouts, connection-refused errors, and human verification. An earlier one-book Selenium test succeeded after the user clicked verification manually.
- The selected edition can have a different title and publication date. Fixed extraction to use the work-title link and the original-publication-year tooltip.
- Fixed a Selenium loading bug where the page body was queried too early. A subsequent attempt still failed because the connection was refused. The latest retry succeeded.
- Success followed the router restart, but we did not verify that the public IP changed or prove an IP block. Separate Requests sessions still face verification.

## Saved evidence and remaining work

Latest CSVs, work IDs, comparison, page timings, and screenshot are in `data/selenium_retry_2026-11-19_192825/`. Use `api.csv`, `selenium.csv`, and `bs4_after_router_restart.csv`. The supplemental parser CSV is labelled separately. Earlier failures and the first successful single-book scrape remain in `data/feasibility_2026-11-19_185334/`. Test code is under `scrapers/`.

The API sample retains source-reported first publication years 1950-2020. English-edition filtering is unverified and the default API ordering biases this small sample. Network packet captures, bandwidth/request/latency benchmarking, the 200-book run, and K-Means remain pending. API and Selenium collection are demonstrated for 10 matching works; independent BS4 access is still unresolved.
