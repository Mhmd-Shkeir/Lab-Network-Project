# Project checklist

Deadline: **25 November 2026**. Working finish target: **23 November**. Owners: Mohammad = scrapers/data; Issa = networking; both = analysis/report/presentation.

## Completed collection

- [x] Three separate Internet Archive scrapers with shared configuration, pacing, retry/backoff and checkpoints.
- [x] Same 200 benchmark IDs collected independently by API, BS4 and Selenium, all rows `ok`.
- [x] Training API dataset: 5,600 collector-success rows (source-quality checks remain) = 200 benchmark books + 1,800 books per genre (600 Americana + 1,200 from the wider English-text pool, flagged `in_americana`); the first 2,000 rows are unchanged.
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
- [x] Bounded `--workers` / `--min-interval` mode in all three scrapers with ONE global start-to-start request limit shared by all workers (retries included, 429/503 pauses everyone); 32 offline tests pass, including description-cleaning tests; not run against archive.org. Issa's commands are in the networking handoff.
- [x] Executed exploratory ML notebooks: grouped splits, EDA, baselines, regression/classification, learning curves and K-Means.
- [ ] Finalise the submission notebook: rerun the corrected CV-selected summary and document that the existing held-out comparisons are exploratory.
- [x] Finish and validate the 15,000-item API collection; exports contain 20,271 linked records / 17,763 description-ready records. Benchmark and earlier datasets preserved.
- [x] Complete notebook 05: paired A/B popularity models, including MLP, on 17,727 items with one fixed grouped holdout and saved CV choices/results.
- [x] Notebook 05 section 9: runnable manual book entry with A/B popularity and view-count predictions; optional metadata defaults are visible. Preserves completed experiment results.
- [x] Notebook 05 section 10: one verified training example and one held-out work, with real metadata, observed views/classes and prediction errors displayed separately from model inputs.

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

- [x] Preserve raw CSVs; separate complete-case popularity cohort: 17,727 rows, 2,544 excluded IDs/reasons, validated required inputs and quality report.
- [x] Run the paired comparison from `docs/POPULARITY_EXPERIMENT_HANDOFF.md`; preserve the completed results and document the neural-validation limitation.
- [x] Exploratory EDA: views, years, scanned pages, item age, genres and source differences.
- [x] Existing experiments use grouped train/test splits by `work_group` and training-derived transforms/thresholds.
- [ ] Validate grouping on the larger dataset using `ol_group`, and keep final model choices independent of held-out scores.
- [x] Exploratory baselines plus regression/classification and per-genre comparisons; final model selection/reporting still needs review.
- [ ] Exclude view-derived values and identifiers from predictive inputs. Document the collection flag and age as existing-engagement features; do not claim new-publication prediction. For genre/juvenile models, exclude the subject tags that define the labels.
- [x] Learning curves on the existing training snapshot; compare future datasets with a consistent evaluation protocol.
- [x] Optional exploratory K-Means in `notebooks/ml_analysis1.ipynb`.
- [x] Executed ML notebook 05 with recorded outputs and limits: existing archived-item engagement, not new-publication sales. Final report/presentation still required.

## Final submission

- [ ] Recommend a scraping strategy using the measured efficiency and stability evidence.
- [ ] Final PDF report covering scraping, networking/security, analysis and optimization.
- [ ] Ten-minute presentation with performance charts, network traces and ML results; both team members speak.
- [ ] Repository includes three scrapers, networking notebook, ML notebook and report PDF.
