# Project checklist

Deadline: **25 November 2026**. Working finish target: **23 November**. Owners: Mohammad = scrapers/data; Issa = networking; both = analysis/report/presentation.

## Completed collection

- [x] Three separate Internet Archive scrapers with shared configuration, pacing, retry/backoff and checkpoints.
- [x] Same 200 benchmark IDs collected independently by API, BS4 and Selenium, all rows `ok`.
- [x] Training API dataset: 5,600 complete rows = 200 benchmark books + 1,800 books per genre (600 Americana + 1,200 from the wider English-text pool, flagged `in_americana`); the first 2,000 rows are unchanged.
- [x] Genre rules, frozen manifests, sampling/exclusion records and source differences documented.
- [x] Final CSVs, completeness report, comparison and checksums.
- [x] Publication-year, timestamp and language parsing corrections; corrected HTML collections retained.
- [x] Repository organized for the networking handoff; earlier experiments backed up and preserved in Git history.

## Next work session

### Issa

- [ ] Set up Ubuntu and a compatible Chrome/Chromium browser and driver; pass `check_selenium_env.py`.
- [ ] Choose the VM's capture interface and verify tcpdump, ss, iftop, nload and Wireshark/tshark.
- [ ] Capture one three-book smoke run of each method; check connection logs, browser metrics, counters and byte attribution before full runs.
- [ ] Verify ufw can enforce a temporary HTTPS block and recover, restoring its initial state.
- [ ] Start the repeated 200-book measurements only after these checks pass.

### Mohammad

- [ ] Help resolve scraper/setup issues from Issa's smoke checks.
- [x] Bounded `--workers` / `--min-interval` mode in all three scrapers with ONE global start-to-start request limit shared by all workers (retries included, 429/503 pauses everyone); 24 offline tests pass; not run against archive.org. Issa's commands are in the networking handoff.
- [ ] Begin the ML notebook: load `training_api.csv`, validate types and groups, inspect distributions and define the prediction task.

### Both

- [ ] Agree on the measurement definitions before the full runs.
- [ ] Update spreadsheet row 6 to identify Internet Archive and the current fields accurately.

## Networking and security deliverables

- [ ] Same 200 IDs, same Linux environment and documented browser/cache settings for all methods.
- [ ] Three fresh runs per method with rotated order (team protocol; the PDF does not prescribe three repeats).
- [ ] Per run: transferred KB, elapsed seconds, request/event counts and clearly defined latency; keep every run and outlier.
- [ ] ss logs, iftop/nload evidence, packet captures and Wireshark screenshots.
- [ ] Firewall block/recovery, rate-limit comparison and sequential-versus-threaded experiment.
- [ ] Networking notebook with tables, charts, screenshots and limitations.
- [ ] Proxy configuration only if useful and time permits; optional in the assignment.

## Data analysis and ML

- [ ] Preserve raw CSVs; write cleaning output separately and report exclusions.
- [ ] EDA: views, years, scanned pages, item age, genres and source differences.
- [ ] Grouped training/test split by `work_group`; fit transforms and popularity thresholds on training data only.
- [ ] Baselines plus regression/classification; evaluate overall and by genre.
- [ ] Exclude view-derived values and sampling/provenance fields from predictive inputs; genre features may be used.
- [ ] Learning curves to assess whether additional training data helps.
- [ ] Optional K-Means as an additional exploratory analysis.
- [ ] ML notebook with outputs and honest limits: the snapshot estimates existing archived-item engagement, not new-publication sales.

## Final submission

- [ ] Recommend a scraping strategy using the measured efficiency and stability evidence.
- [ ] Final PDF report covering scraping, networking/security, analysis and optimization.
- [ ] Ten-minute presentation with performance charts, network traces and ML results; both team members speak.
- [ ] Repository includes three scrapers, networking notebook, ML notebook and report PDF.
