# Networks Lab Project: Open Library (Mohammad Ali + Issa)

Deadline: **Wed 25 Nov 2026** (PDF). Dates below are a suggestion (DS project is due 24 Nov).
Rule from the earlier labs: only put numbers you measured in the report.

## M1: Setup and target (15-16 Nov)
- [ ] Confirm the deadline with the instructor (PDF says 25 Nov, earlier note said 28/29)
- [ ] Fix row 6 text: add security (ufw, rate limiting, threads) and the tool names (ss, iftop, tcpdump, Wireshark)
- [ ] Define the fields: title, author, first_publish_year, edition_count
- [ ] Define the query/subject and the sample size (e.g. 500-1000 books, same set for all 3 methods)
- [ ] Create the repo and folders: scrapers/, data/, captures/, screenshots/, notebooks/, report/
- [ ] Set up WSL Ubuntu: venv, tshark, ss, iftop, nload, ufw, Chrome + chromedriver (Selenium failed here last time)
- [ ] Check Open Library rules (robots.txt, rate limits) and send a proper User-Agent

## M2: Build and validate the three scrapers (17-18 Nov)
Methods: Selenium, BeautifulSoup, Open Library Search API.
CSV columns (same for all): `work_id`, `title`, `author`, `first_publish_year`, `edition_count`.
`work_id` is the key used to match rows across the three CSVs.

**Step A: 10-book pilot (then STOP and review with the team)**
- [ ] Pick one fixed search: query, filters and sort order written down
- [ ] 10 distinct works, same search for all three methods
- [ ] Each scraper exports its own CSV independently
- [ ] Comparison report: works retrieved per method, works matched in all three, missing or different fields
- [ ] If results differ: check query, filters, sort order first
- [ ] Any unresolved mismatch goes back to the team before scaling up
- [ ] Hand-off: 3 pilot scripts, 3 CSVs, comparison, any errors seen

**Step B: 200 works (only after the pilot is reviewed)**
- [ ] Fixed query, filters and sort order (same as the pilot)
- [ ] 200 distinct works per method
- [ ] Verify all three methods cover the same works
- [ ] If fewer than 200 comparable records: show how many match and explain why, before changing the target
- [ ] Rate limiting and error handling (429/403, retries, timeouts)

## M3: Benchmark the final 200-work sample (19-21 Nov)
**Baseline benchmark**
- [ ] Each method runs 3 times on the same 200 works, same network and cache conditions
- [ ] Per run record: total runtime, bytes transferred, HTTP request count, average request latency, successful records
- [ ] Keep the raw results (one row per run) and report the **median runtime** per method
- [ ] HTTP request count and latency come from client request logs
- [ ] Network evidence: `tcpdump`, `ss`, and `iftop` or `nload`
- [ ] Open the captures in Wireshark and save screenshots for the notebook

**Kept separate from the baseline (never mixed into the comparison table)**
- [ ] Multithreading test (sequential vs threads vs threads with rate limit)
- [ ] ufw: `deny out 443`, show the scraper failing, delete only that rule, show it working again (prove the rule was active)
- [ ] Proxy (Squid/Tor): optional, only if time allows

**Output**
- [ ] Networking notebook with charts and screenshots

## M4: Data cleaning and ML (21-22 Nov)
- [ ] Input: one verified CSV from the final 200-work collection
- [ ] Remove duplicate `work_id`s
- [ ] Document every missing value that was excluded during cleaning (how many, which field)
- [ ] Features for K-Means: `first_publish_year` and `edition_count` only
- [ ] Check odd years and types
- [ ] EDA with pandas/matplotlib/seaborn (year histogram, edition-count distribution)
- [ ] K-Means on publication year + edition count (log-scale edition count, standardize)
- [ ] Pick k with elbow + silhouette; visualize the clusters
- [ ] Describe each cluster in plain words
- [ ] ML notebook (Jupyter or Colab)

## M5: Conclusion, report and presentation (23-24 Nov)
- [ ] Final report PDF
- [ ] 10-minute presentation: performance charts, network trace visuals, ML results
- [ ] Repo complete: 3 scrapers, networking notebook, ML notebook, report PDF
- [ ] Rehearse under 10 minutes, both of you speak

## The conclusion (what it must contain)
The PDF goal 5: "recommend the best scraping strategy for efficiency and stability".
- [ ] One clear winner, stated first (expected: API)
- [ ] Evidence table from M3: time, bandwidth, requests, latency per method
- [ ] Efficiency: why (structured JSON vs full HTML vs a full browser loading scripts/images)
- [ ] Stability: failures seen, 429s, ufw block behavior, effect of threads and rate limiting
- [ ] When each method is still the right choice (BS4 with no API, Selenium for JS-heavy pages)
- [ ] Best settings: threads, delay between requests, retries
- [ ] ML link: what K-Means showed about the books, and that the data collected is the same whichever method was used
- [ ] Limitations: sample size, single runs, one network, anything not tested (say so honestly)
