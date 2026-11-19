# Networks Lab Project: checklist (Internet Archive) — Mohammad Ali + Issa

Deadline: **Wed 25 Nov 2026** (PDF); team target to finish **Mon 23 Nov**. DS project is due Tue 24 Nov.
Rule: only numbers we measured go in the report; label every statement as measured / explanation / estimate.
Owners: **M** = Mohammad (scrapers, data collection) · **I** = Issa (networking) · **Both** = cleaning, EDA, ML, report, presentation.
Full plan and reasoning: `docs/IMPLEMENTATION_PLAN.md`; PDF requirement audit: `docs/PDF_REQUIREMENTS_AUDIT_2026-11-19.md`.
The PDF does **not** require Open Library, K-Means, 200 or 2,000 records; those are our choices.

## M0 Decisions and migration (M)
- [x] Source: Internet Archive, Americana collection (archive.org HTML pages, search/metadata API, official Views API)
- [x] Earlier experiments kept as history (`HISTORY.md`): Open Library, dBooks, LibriVox, 10-record IA pilot
- [x] README, `scrapers/config.py`, checklist, data dictionary migrated to Internet Archive
- [x] Filters, sampling, duplicate rules fixed and documented (`data/manifest/manifest_meta.json`, plan §3)
- [ ] Tell the instructor/lab doctor about the switch from Open Library to Internet Archive and update row 6 of the spreadsheet (team)

## M1 Scrapers and data collection (M)
- [x] Three separate scrapers: `ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py` (+ `ia_common.py`)
- [x] Pacing (3 s gap), retries with exponential backoff + jitter, Retry-After, adaptive slow-down, circuit breaker, checkpoint/resume, per-attempt logs
- [x] Reproducible benchmark manifest: snapshot of the pool, seeded order, 200 distinct works, exclusions recorded
- [x] 10-book validation of all three scrapers (fields identical; view counts differ, API higher)
- [x] 200 books collected independently by all three methods (200/200 ok each); per-method CSVs; comparison tables.
      First HTML run had parser defects (c1920 dates, microsecond timestamps, language names): fixed, re-collected, first run kept in `data/history/`
- [x] Genre training manifest: availability + preview checked, explicit subject rules (`scrapers/genres.py`), 600 science fiction + 600 fantasy + 600 mystery/thriller,
      overlap rule, criticism/teaching/bibliography exclusions, no popularity-based selection, at most 3 per work group
- [x] 2,000 training records collected through the API (200 benchmark + 1,800 genre books, all ok); `training_api.csv`
- [x] Data dictionary, completeness report, checksums, sampling/exclusion records
- [x] Portable Selenium setup (no hard-coded browser paths) + `check_selenium_env.py`; Ubuntu VM instructions
- [x] Networking handoff for Issa (`docs/HANDOFF_NETWORKING_ISSA.md`)
- [ ] Not implemented in the scrapers: multithreading option, rate-limit comparison, proxy (see M3)

## M2 Network measurements (I) — must re-run the scrapers under capture
- [ ] Set up Ubuntu VM, run `python scrapers/check_selenium_env.py` (ARM/Apple-silicon browser may need the alternative in `docs/SETUP_UBUNTU_VM.md`)
- [ ] tcpdump / ss / iftop / nload / tshark work; capture interface chosen and written down
- [ ] 3 runs × 3 methods on `data/manifest/benchmark_200_ids.json`, rotated order, one pcap each, same pacing
- [ ] Metrics table: Method, bandwidth (KB, from pcap), time (s) with total / sleep / active, #requests (+ Selenium sub-requests), avg latency (ms) with definition
- [ ] Outliers kept; one row per run, median and mean/min/max per method
- [ ] Wireshark screenshots (conversations, IO graph, TCP RTT, TLS hosts), `ss` logs, iftop/nload screenshots
- [ ] Networking notebook with charts and screenshots

## M3 Security and responsible use (I, with M if code is needed)
- [ ] ufw: deny out 443 → show failure and retry/backoff in the logs → delete only that rule → show recovery; prove the rule was active
- [ ] Rate limiting: effect of the delay setting and of `Retry-After` handling (no unthrottled tests against archive.org)
- [ ] Multithreading: shared global pacer; sequential vs threads; needs a small addition to the scrapers (decide who writes it)
- [ ] Proxy (Squid/Tor): optional, last

## M4 Cleaning, EDA and ML (Both)
- [ ] Install analysis packages (`requirements-analysis.txt`) in Colab or a local Python (not needed on the VM)
- [ ] Clean `data/training_api.csv`: types, implausible values, duplicates, exclusions; keep raw files untouched
- [ ] EDA with pandas/matplotlib/seaborn (views raw + log, year, pages, item age, subjects, API-vs-page view differences)
- [ ] Targets: log1p(views) for regression; low/medium/high from training-set terciles for classification
- [ ] Use `sampling_stratum` / genre columns for EDA and as features or stratification, keep the 200 benchmark books flagged (`in_benchmark`)
- [ ] Split by `work_group` (grouped train/test), fit transformers/thresholds on training data only, baselines, models, metrics
- [ ] Never use last-30/7-day views or any views-derived column as an input
- [ ] K-Means on year + log(pages) as an additional exploratory analysis (optional)
- [ ] ML notebook (Jupyter or Colab)

## M5 Report and presentation (Both)
- [ ] Final report PDF following the PDF sections; measured / explanation / estimate labels; limitations
- [ ] 10-minute presentation: performance charts, visualized network traces, ML results; both speak; rehearse
- [ ] Repository complete: 3 scrapers, networking notebook, ML notebook, report PDF

## The conclusion (what it must contain)
- [ ] Best method for efficiency **and** stability, stated first, with the evidence table from M2 (not decided in advance; API was fastest in the pilot only)
- [ ] Stability evidence: failures, retries, 429s, ufw behaviour, effect of delay/threads
- [ ] When each method is still the right choice (BS4 without an API, Selenium for JS-heavy pages)
- [ ] Best settings found (delay, retries, threads, batch size)
- [ ] ML results versus baselines, and what views do/do not mean (one archived copy, not worldwide popularity or sales)
- [ ] Limitations: one site, one network, one snapshot, API-vs-page view-count difference, pilot timings are not the final comparison

## Known open points
- Views API vs page counter differ for most books (API higher); cause not verified.
- `subject:fiction` also matches some non-fiction books about fiction.
- Instructor/lab doctor has not been told about the source change (team decision).
