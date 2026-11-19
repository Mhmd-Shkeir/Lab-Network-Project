# Open Library scraping tests — 19 November 2026

Tested in WSL Ubuntu with Python Requests/BeautifulSoup and visible Selenium Chrome. The current pilot selected 10 distinct science-fiction work IDs with reported first publication years from 1950 to 2020. English-edition filtering remains unverified. The API default ordering is a biased convenience sample.

| Method | Actual result |
|---|---|
| API | Collected all four required fields for 10 works. Two successful batch responses supplied candidates for the saved sample. |
| Independent Requests + BeautifulSoup | Both attempted book pages redirected to human verification, despite HTTP 200 responses. Collected 0 records; the other 8 were not attempted. |
| Selenium, earlier single-book test | After the user completed verification, collected The Time Machine, H. G. Wells, 1895, and 1,147 editions. Total elapsed time was 67.12 seconds including the manual wait. |
| Selenium, current 10-book pilot | Initial run encountered a missing-body page-loading bug, which was fixed. The retry reached a connection-refused error on the first target. One ordinary reload also failed. Collected 0 pilot records; the other 9 were not attempted. |
| Supplemental BS4 parser check | Correctly parsed the earlier Selenium-captured book HTML locally. This is not independent live BS4 success. |

## Problems and fixes

- Experienced timeouts, connection-refused errors, and human-verification redirects. The API worked during this pilot. An IP-wide or permanent block is not confirmed.
- The user completes human verification. The scraper then resumes automatically. An API or separate Requests session does not inherit that browser verification.
- The displayed edition title can differ from the work title. The parser now reads the work-title link and the first-publication-year tooltip, rather than the selected edition's publication date.
- Fixed the Selenium missing-body loading error. The runner now also stops after 90 seconds of persistent connection errors while continuing to wait for manual verification when that page is available. That new timeout handling has been syntax-checked, not rerun live.

## Evidence and remaining work

Results and fixed IDs are in `data/feasibility_2026-11-19_185334/`. This contains `api.csv`, header-only `bs4.csv` and `selenium.csv`, `work_ids.json`, observations, the Selenium error screenshot, and the earlier successful book evidence under `prior_single_book/`. Rerunnable code is in `scrapers/feasibility_check_2026_11_19.py`; the earlier single-book scraper is also saved there.

The two API calls took 11.638 seconds combined and returned 194,756 decoded response-body bytes. These exclude deliberate delays and are not captured network bandwidth. No packet captures, browser request counts, three-run benchmark, 200-book collection, or ML analysis were completed in this test.

API collection is feasible and manual-assisted Selenium succeeded for one book. The shared 10-book pilot is incomplete. Reliable HTML access and independent BS4 extraction remain unresolved, so a three-method efficiency winner cannot yet be justified.
