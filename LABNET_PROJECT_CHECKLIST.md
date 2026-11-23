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

## Platform and remaining work

The team completed the baseline and firewall evidence on macOS. The project does not claim Linux `ss` or UFW compliance: macOS `lsof` and `pf` were used and the platform limitation is documented. The PDF rubric must be checked against this substitution before submission. Three repetitions per method were a team protocol goal; one captured run per method is currently available.

### Mohammad

- [x] Bounded `--workers` / `--min-interval` mode in all three scrapers with one global request-start limit shared across workers (including retries and 429/503 pauses); 24 offline tests passed, not against archive.org.
- [x] Create and execute `notebooks/ml_analysis.ipynb`: validate all 5,600 rows; write a separate cleaned modeling table; inspect distributions and source differences; use one shared `work_group` split; compare low/medium/high classification against a majority-class baseline and numeric log-view regression against a median baseline; report accuracy, error metrics, confusion matrix and limitations.

### Both

- [x] Agree on measurement definitions; definitions are in the report.
- [ ] Update spreadsheet row 6 to identify Internet Archive and current fields accurately.

## Networking and security deliverables

- [x] Same 200 IDs, pacing, and headless browser settings for all methods; all runs used the available Mac. Linux preference is disclosed as unmet.
- [ ] Three fresh runs per method with rotated order (team protocol; the PDF does not prescribe three repeats).
- [x] Per run: transferred KB, elapsed seconds, request/event counts and clearly defined latency; one full captured run per method is complete. Three-repeat protocol remains outstanding if time allows.
- [x] Mac `lsof` logs, `iftop`/`nload`, three Wireshark Conversations views, Selenium I/O graph and RTT screenshot are present. Linux `ss` is unavailable on this Mac.
- [x] macOS `pf` HTTPS block/recovery test passed and was captured; disclose that it is not UFW. Sequential-versus-threaded comparison is complete.
- [x] Small 20-item API comparison with one versus two workers and the same 3-second global request-start limit; both runs had 20/20 successes, zero retries, and one request in flight.
- [x] Networking notebook with refreshed tables, charts, screenshots and platform limitations.
- [ ] Proxy configuration only if useful and time permits; optional in the assignment.

## Data analysis and ML

- [x] Preserve raw CSVs; write cleaning output separately and report exclusions.
- [x] EDA: views, years, scanned pages, item age, genres and source differences.
- [x] Grouped training/test split by `work_group`; fit transforms on training data only.
- [x] Compare a median baseline with regression and evaluate overall, by genre, and by source.
- [x] Exclude view-derived values and sampling/provenance fields from predictive inputs; genre features may be used.
- [x] Training-size curve on the fixed grouped holdout; describe it as a sensitivity check, not repeated cross-validation.
- [ ] Optional K-Means as an additional exploratory analysis.
- [x] ML notebook with outputs and honest limits: the snapshot estimates existing archived-item engagement, not new-publication sales.
- [x] Open Library enrichment by exact Internet Archive identifier and expanded Archive collection: 20,271 linked records; paired popularity cohort has 17,727 rows. Current popularity accuracy is 59.35% with descriptions vs 57.35% without, below 80%; numeric regressor raw-view MAE is 255.36. The earlier 5,600-item experiment is historical and not the final estimate.

## Final submission

- [x] Recommend the API when a supported endpoint supplies required fields; one-run captured results show much lower time and endpoint traffic.
- [x] Final PDF report covering scraping, networking/security, analysis and optimization.
- [ ] Ten-minute presentation with performance charts, network traces and ML results; both team members speak.
- [ ] Complete the human review of provisional children-audience labels.
- [x] Repository includes three scrapers, networking notebook, ML notebook and report PDF.
