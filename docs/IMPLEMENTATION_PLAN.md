# Networks Lab Project — implementation plan (Internet Archive)

Plan of 19 Nov 2026 (draft v2, adopted). Day-to-day status: `LABNET_PROJECT_CHECKLIST.md`.
Sections 1, 9 and 10 describe the situation *before* implementation; what was actually built is in the
"Implementation notes" below and in `README.md`.

## Implementation notes (what changed from the draft while building)
- Defaults D1–D10 below were adopted unchanged unless listed here. Division of work: Mohammad = scrapers and data collection,
  Issa = networking measurements, both = cleaning/EDA/ML/report/presentation.
- Scrapers are `scrapers/ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py` with `ia_common.py`, `config.py`;
  the manifest is built by `build_manifest.py`; `compare_runs.py` and `finalize_datasets.py` produce the comparison and the final CSVs.
- The pool query returned 25,722 snapshot rows on 19 Nov (the pilot's slightly different query returned 25,772; an earlier count call returned 25,723).
- Manifest: ordering by `sha256("2026:<identifier>")`; the Views API was checked while building the manifest so every listed book has view data
  at that time (1 item had none and was excluded, 1 was excluded by the 3-per-group cap, 1 pool row was not English).
- **Training set changed (user decision, 19 Nov):** instead of 2,000 random fiction books, the training set is the 200 benchmark books + 600 science fiction +
  600 fantasy + 600 mystery/thriller books (explicit subject rules in `scrapers/genres.py`, `build_training_manifest.py`). The random 2,000-id list and its
  partial run are kept in `data/history/superseded_random_fiction_training/`. Section 3.3 below describes the earlier random design.
- The first HTML benchmark run (parser defects) was replaced by a corrected re-collection of the same 200 ids; the first run is in `data/history/`.
- The Views API returned HTTP 502 for one 100-id batch (50 and 75 worked), so batches are 50 ids.
- Pacing is a gap between the end of one request and the start of the next (3 s). For Selenium the gap also covers reading the fields.
- Selenium uses `page_load_strategy=normal`; browser sub-requests/encoded bytes come from Chrome's performance log (browser-reported).
- Multithreading, rate-limit comparison and proxy are **not** implemented in the scrapers (Issa's part; see `docs/HANDOFF_NETWORKING_ISSA.md`).
- Pilot scripts and earlier experiments moved to `legacy/`, `docs/history/`, `data/history/` (see `HISTORY.md`).

Deadline: PDF says **Wed 25 Nov 2026**; team target to finish **Mon 23 Nov**; DS project is due Tue 24 Nov.

## 0. How to read this file

Labels used everywhere (report too): **[M]** measured fact (file/log/number exists) · **[E]** explanation, not tested ·
**[S]** estimate/extrapolation · **[D]** decision still needed (a recommended default is given).
Status marks: ✅ completed · 🔧 completed but must change · ⬜ remaining.

Correction to my earlier note 8: the PDF does **not** mandate Open Library or K-Means. Goal 4 says "prediction,
classification, or trend analysis"; the ML list names regression (e.g. popularity), classification, and clustering
(e.g. K-Means). So **popularity regression + classification is the main ML**, and **K-Means stays as an additional
exploratory analysis** from our original proposal.

---

## 1. Where we are

### ✅ Completed (evidence exists)
- Repo `Mhmd-Shkeir/Lab-Network-Project` cloned/pushed; folders and M1–M5 checklist pushed.
- WSL Ubuntu venv with `requests`, `bs4`, `selenium`; Chrome for Testing 157 + chromedriver; headless and visible Selenium both ran.
- Open Library evidence (kept as history, **no more requests to openlibrary.org**): API and visible Selenium matched on 10/10 works; independent BS4 got a human-verification page.
- Source checks for dBooks, LibriVox, Open Textbook Library (`SOURCE_OPTIONS_CHECK_*.md`).
- Internet Archive: single-item check (`prideprejudice00aust`, 313,037 views by API, BS4, Selenium) and a **10-record three-method pilot** (`data/archive_timed_pilot_2026-11-19/`), no gate, no errors.
- Official Views API endpoint verified: `https://be-api.us.archive.org/views/v1/short/<id,id,...>` (the guessed `archive.org/services/views/...` route is 404).

### 🔧 Must change
| Item | Problem | Change |
|---|---|---|
| `README.md`, `scrapers/config.py`, checklist | Describe Open Library, `work_id`, `edition_count`, K-Means as the only ML | Migrate to Internet Archive schema and this plan |
| Pilot sample | Sorted by identifier (`02…`, `100…`), has duplicate volumes/copies, "fiction" includes books about fiction | Seeded random sample from a saved snapshot, duplicate rule (§3) |
| Pilot timing | Wall time dominated by 3 s sleeps and one slow request per method | Record total, sleep and active time separately; keep outliers (§5) |
| Pilot Selenium | `page_load_strategy=eager`, subresources not counted | Count browser subrequests and bytes (§5) |
| Pilot script location | Lives in `data/` | Rebuild as three scripts + common module in `scrapers/` |
| Pilot error handling | Any exception ends the run, no retry/backoff | Retry/backoff, checkpoint/resume, circuit breaker (§4) |
| User-Agent | Names the tool, no project/contact policy | Team decides contact text (§9 D5) |
| Uncommitted Codex files | Handoffs, scripts, data folders untracked | Review, then commit (no raw HTML bulk) |

### ⬜ Remaining
Final filters/manifest, three production scrapers, 200-record 3-method collection, repeated benchmark with captures,
ufw block/recovery, rate-limit and multithreading tests, ~2,000-record API collection, cleaning, EDA, ML, networking
notebook, ML notebook, report PDF, 10-minute presentation.

---

## 2. Pilot facts, explanations, estimates (10 records, one run)

| Label | Statement |
|---|---|
| [M] | Same 10 identifiers through API, Requests+BS4, visible Selenium; no verification page, no failures. |
| [M] | Total elapsed: API 5.50 s, BS4 75.40 s, Selenium 67.91 s (incl. 1.80 s browser start). |
| [M] | Deliberate sleep: API 3 s (1 gap), BS4 27 s, Selenium 27 s. Sum of request/navigation times: API 2.50 s, BS4 47.3 s, Selenium 38.1 s. |
| [M] | Slowest single items (kept, not removed): BS4 `100perfectgirl0000wann` 23.69 s; Selenium first page `02713411.5992.emory.edu` 25.59 s. Other BS4 requests 1.28–4.40 s; other Selenium navigations 1.09–1.79 s. |
| [M] | Median / mean per request: BS4 2.56 s / 4.73 s; Selenium 1.42 s / 3.81 s (computed from saved metrics). |
| [M] | Requests: API 2 (one search call + one views call for 10 ids); BS4 10; Selenium 10 navigations (subresources **not** counted). |
| [M] | Decoded body bytes: API 5,160 total; BS4 2,348,098 total (218–266 KB/page). Not wire bytes. Selenium bytes not measured. |
| [M] | BS4 CSV = Selenium CSV on all 9 fields × 10 rows. API differs from both **only** in `views_all_time`. |
| [M] | API views are higher than the page on 10/10 records, by 1–48 (0.3–1.3 %). Largest: `02lastmohicans00cooprich` 4,552 vs 4,504. |
| [M] | First HTML parser missed creators on 7/10 pages and kept duplicate subject tags; corrected parser fixed both; timings were not re-run after the fix. |
| [M] | Pilot search matched 25,772 candidates (`numFound`). |
| [E, untested] | Page counters lag or are cached versus the Views API. Reasoning: API was called first (≈19:44:38) and pages later, yet pages are lower, so "counters grew between calls" does not explain it. Selenium (fetched ~1–2 min after BS4) equals BS4 exactly. |
| [E, untested] | The two 23–26 s items are network/server variance. Cause unknown. |
| [E, untested] | The API is more efficient because of fewer, smaller requests. Supported by counts/bytes, **not yet** by repeated timing. |
| [S] | HTML run of 200 records ≈ 18–26 min (BS4: 200 × (3 s + median 2.56 s) = 18.5 min; with mean 4.73 s = 25.8 min). Selenium ≈ 15–23 min with `eager` loading; slower with full loading. |
| [S] | API, 10 ids per batch: ≈ 3 min for 200 and ≈ 30 min for 2,000. Larger batches untested. |
| [S] | Whole benchmark (3 runs × 3 methods) ≈ 2.5–4 h of machine time, excluding setup/analysis. |

Do not claim "Selenium is faster than BS4": the pilot cannot support it (one run, dominated by sleep and one outlier each).

---

## 3. Data definition (Internet Archive only)

**One provider:** archive.org detail pages (HTML + Selenium) and Internet Archive APIs (search/metadata + Views API).
Open Library and dBooks stay documented as prior experiments, not mixed into the data.

### 3.1 Candidate pool (starts from the pilot's Americana query) — [D1] confirm values
```text
collection:americana AND mediatype:texts AND language:eng AND subject:fiction
AND creator:* AND year:[1800 TO 2020] AND imagecount:[50 TO 1500]
```
- Changes vs pilot: year range narrowed to 1800–2020 (pilot 1500–2026) and an imagecount upper bound of 1,500 to avoid very large multi-volume scans. Both bounds are my proposal, not tested.
- `subject:fiction` matches any subject tag containing "fiction", so a few non-fiction books about fiction remain. Keep it (continuity with the pilot) and **state this limitation**.
- Pool size will be re-counted at snapshot time; do not quote 25,772 for the new query.

### 3.2 Fields (same for all three methods)
`identifier, title, creators, publication_year, subjects, language, addeddate, scanned_page_count, views_all_time`
plus provenance: `method, source_url, retrieved_at_utc, run_id, http_status, attempts, error`.
- `publication_year` = year of this archived item's edition, not first publication.
- `scanned_page_count` = scanned images (`imagecount`), not printed pages.
- `creators` may include illustrators/printers; keep the raw list and derive `first_creator`.
- `views_all_time`: API value = **training label**; HTML values are stored per method as observed.
  Never overwrite one with the other. Last-30-day / last-7-day views are **not** collected as predictors (target leakage).
- Normalization rules (written once, applied to all methods): collapse whitespace; de-duplicate subject tags;
  language code `eng`; `addeddate` kept as UTC ISO string.

### 3.3 Reproducible sampling
1. **Snapshot**: page through the pool once (identifier + the metadata fields above), slowly, and save
   `data/pool_snapshot_<date>.csv` with `numFound`, query, timestamp and SHA-256 in `data/manifest_meta.json`. [S: ≈ 11 MB for ≈ 26k rows]
2. **Group key** `work_group` = normalized title (lowercase, no punctuation, strip volume/part/edition markers such as `v.2`, `vol 3`, `3rd ed`)
   + normalized first-creator surname.
3. **Seeded order**: `random.Random(2026)` permutation of the snapshot (seed stored in the manifest).
4. **Benchmark set (200)**: first 200 items in that order that pass the exclusion rules and have a **distinct** `work_group`.
   Saved as `data/benchmark_200_ids.json` — the single list all three methods use.
5. **Training set (~2,000 usable)**: continue down the same order, keeping at most **3 items per `work_group`**, until ~2,000 items have all fields and `have_data=true` for views.
   The 200 benchmark items are a random subset of it. [S: expect to over-draw by roughly 25 %; the real rate is measured on the 200.]
6. Exclusions (each counted and listed in `data/exclusions.csv`): missing title/creator/year/imagecount/addeddate, `have_data=false`, duplicate identifier,
   over the 3-per-group cap, non-English after check.
7. Keep a "no-views" tally: items dropped for missing views may bias the sample toward more-viewed items; report it.

### 3.3b Duplicate and leakage handling
- Exact duplicate identifiers: dropped.
- Same `work_group`: counted, capped (3 for training, 1 for the benchmark), and **always in the same train/test fold** (§7).
- Known pilot examples: `02713411.5992/5993.emory.edu` (same title) and `100perfectgirl0000/0003wann` (same title).

---

## 4. Scraper design (three scripts + shared module)

Files: `scrapers/ia_common.py`, `ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py`, `build_manifest.py`, `config.py`.

- **Identity**: descriptive User-Agent with project name/version, no personal details; same string for Requests and Selenium. No spoofing, no cookie transfer, no IP change, no verification clicking.
- **Rate limiting**: one shared limiter (minimum interval between request starts across all threads). Baseline 3 s, as in the pilot. [D4] re-read `archive.org/developers/bots.html` and write the stated limits into the README before the first run (I have not re-read it).
- **Retries/backoff**: timeouts (15 s connect, 45 s read, as in the pilot); retry only on timeout/connection error/429/5xx (and 408); max 4 retries; waits 2, 4, 8, 16 s + jitter, capped at 60 s; honor `Retry-After`; no retry on other 4xx.
  On 429/503 the limiter interval doubles (cap 30 s) and decays after 50 clean requests.
- **Circuit breaker**: stop the run after 5 consecutive failures or on any 403/verification page; write a failure summary; never route around it.
- **Logging**: one JSONL line per **attempt** (id, url, attempt no., start, end, status, decoded bytes, redirects, exception). Failed attempts stay in the log.
- **Checkpoint/resume**: append each finished record; a restart skips finished ids. A record failed by one method stays failed in that method's CSV (never filled from the API).
- **Same fields, same IDs**: every scraper reads `benchmark_200_ids.json` (or the training ID list for API-only) and writes its own CSV.
- **API scraper**: batches of ids for the search call and the Views call. [D3] test batch sizes (10 → 50 → 100) on small runs and record the largest that works before timing the 2,000 run.
- **BS4 scraper**: `requests.Session`, detail page, selectors from the pilot (`h1.item-title`, `dl.metadata-definition`, `dl[aria-label="Item creator metadata"]`, `section.item-stats-summary [itemprop="userInteractionCount"]`).
- **Selenium scraper**: visible Chrome in WSLg, fresh temporary profile per run (cold cache), `page_load_strategy=normal` for the benchmark ([D6] pilot used `eager`; if we keep `eager`, report it), wait for `h1.item-title`, extraction from the live page.
- **Selenium subresource measurement** (required for fair bandwidth/request counts): enable Chrome performance logging and, after each navigation, read `Network.requestWillBeSent`, `responseReceived`, `loadingFinished` (`encodedDataLength`); cross-check with the page's Resource Timing (`transferSize`, `duration`). Record per page: number of requests, encoded bytes, hosts contacted. Run-level wire bytes come from the pcap (§5), and browser-log bytes are reported as a second, differently labelled column.

---

## 5. Network measurement protocol (PDF: Networking Observation)

### 5.1 Per run (9 runs: 3 methods × 3 runs, on the same 200 ids)
- Run order rotated: run 1 API→BS4→Selenium, run 2 Selenium→API→BS4, run 3 BS4→Selenium→API (reduces ordering/time-of-day bias).
- Same network, same machine state, nothing else heavy running; note Wi-Fi/Ethernet and the time of day. Do not publish the public IP.
- Capture per run: `sudo tcpdump -i any port 80 or 443 -w captures/<method>_run<N>.pcap` (PDF command). The pcap includes other hosts Chrome contacts; split by TLS SNI/DNS in Wireshark/tshark.
- Check whether Chrome used QUIC (UDP/443) in the pcap and say so; do not disable it silently. [E] it may matter for `ss -t` and for the ufw rule.
- Connections: `ss -t -a | grep python` for the Python methods; for Selenium also sample `chrome`/`chromedriver` (they are not `python`). Sample every 1 s into a log and keep a screenshot.
- Bandwidth: `iftop` (screenshot + `-t` text log) and `nload` (screenshot). Totals come from the pcap, not from the screenshots.
- Wireshark/tshark (reuse Lab 2 commands: `-z io,stat,0 -z conv,tcp -z io,phs`): conversations, IO graph, endpoints, TCP RTT, TLS handshake time, DNS lookups. Save screenshots for the notebook.
- Client logs (§4) provide request count and latency.

### 5.2 Metrics table (PDF: Method, bandwidth (KB), time (s), #requests, avg latency (ms))
| Column | Source and definition |
|---|---|
| bandwidth_KB (primary) | pcap bytes to/from archive.org hosts, both directions, per run |
| decoded_body_KB (secondary) | sum of response body sizes from client log (Requests/API only) |
| browser_encoded_KB (secondary) | Chrome Network log, Selenium only |
| time_total_s | start of first request to last record written |
| sleep_s / active_s | deliberate waits / total − sleep; reported **separately** |
| requests | client log attempts (retries counted, redirects counted); Selenium also total subrequests |
| avg_latency_ms | mean per-request time from the client log; also median, p95, max |
| tcp_rtt_ms (supporting) | from pcap (SYN→SYN/ACK); the pcap cannot show HTTP latency inside TLS |
| records_ok / failed / retries | counts |

### 5.3 Outliers and reporting rules
- Report **all** runs (one row per run) and the median per method **and** the mean, min and max. Slow items stay in the data and are marked in charts.
- A "without outlier" number may appear only as a labelled sensitivity check beside the raw one.
- If runs disagree widely, say so; do not pick the best run.
- Explanations (cache, server load, network variance) are written as **[E]** unless a capture shows the cause (e.g. retransmissions, DNS delay).
- View-count differences between API and HTML are reported per record in a data-quality table (and chart) and per run, including drift of the same id between runs.

---

## 6. Security and responsible-use experiments (PDF: Security + Firewall control)
Kept **out of** the baseline table.
1. **Feasibility first (Fri):** `sudo ufw status verbose` (record the starting state), check that ufw actually enforces rules under WSL (the earlier Lab 2 deny-443 test was inconclusive).
   [D7] If ufw cannot enforce in WSL, document that and use an iptables/nft equivalent or another Linux host, stating clearly what was used.
2. **Block/recovery:** with ≤10 records: baseline works → `sudo ufw deny out to any port 443` (shows in `ufw status numbered`) → scraper fails with logged errors, time-to-fail, retry/backoff behavior, capture showing SYN retransmits or no reply (a `deny` drops silently; optional `reject` for contrast) → delete **only that rule** → scraper recovers → restore the original ufw state. Screenshots of each step.
3. **Allow/deny ports:** show allow vs deny for 443 (and 80 if relevant) with the same pass/fail evidence. If both TCP and UDP 443 are affected by the rule, note it.
4. **Rate limiting:** sequential at 3 s vs a shorter interval within the limits found in [D4]; record 429/slowdown behavior if any. Stop at the first 429.
5. **Multithreading:** ThreadPoolExecutor with workers {1, 2, 4} (HTML) and the **same global rate cap** across workers, so total request rate is not multiplied by thread count. Compare time, requests, failures, latency. Selenium threading (multiple browsers) is optional and heavy.
   An unthrottled threaded run against the real site is **not** done by default; if wanted, only ≤30 records, ≤4 workers, abort on first 429/slowdown [D8], or use a local test server.
6. **Proxy (Squid/Tor): optional**, last priority; Tor is not recommended for this site.

---

## 7. Data analysis and ML (PDF: Data Cleaning & Analysis)

### 7.1 Cleaning and EDA (pandas, matplotlib, seaborn)
- Input: the API-collected training CSV (~2,000) + the three-method 200 CSVs. Raw files are never edited; cleaning writes new files.
- Exclusion table (count per reason), missing-value table, duplicate/group summary, year and pages checks, type checks.
- Plots: views (raw and log), year histogram, scanned pages, item age vs views, views by decade, creators count, top subjects, correlation matrix, API-vs-HTML view differences, method agreement on the 200.

### 7.2 Targets and features
- Target: `views_all_time` (API snapshot). Regression target `log1p(views)`. Classification: low/medium/high = training-set terciles (thresholds fit on training data only and applied unchanged to test).
- Features (allowed at prediction time): publication year, scanned page count, item age at snapshot (`snapshot − addeddate`), number of creators, number of subjects, subject and title TF-IDF (capped vocabulary). `language` is constant (English) and dropped.
- Never in features: views in any window, the class label, anything derived from views. Include the snapshot date in the notebook.

### 7.3 Splitting, baselines, models
- Hold-out test set 20 % with `GroupShuffleSplit` by `work_group` (seed 2026), touched once at the end. Cross-validation on the training part with `GroupKFold`/`StratifiedGroupKFold`. Transformers, TF-IDF vocabulary and thresholds are fit inside the training folds.
- Baselines: regression — training mean/median of log views; classification — most-frequent and stratified dummy classifiers.
- Models: Ridge / linear, RandomForest, GradientBoosting (regression); logistic regression, RandomForest (classification).
- Metrics: MAE, RMSE, R², Spearman on log scale, and MAE back in raw views; accuracy, macro-F1, confusion matrix. Compare each model to its baseline and report if it does not beat it.
- Interpretation limits stated in the report: views are engagement with one archived copy, not worldwide popularity or sales; a snapshot supports estimating hidden views of **existing** items, not forecasting an unpublished book.

### 7.4 K-Means (additional, exploratory — first to cut if short on time)
Features: `publication_year`, `log(scanned_page_count)`, standardized; k by elbow + silhouette; clusters profiled afterwards by views (views are not a clustering input). Edition count is not available from Internet Archive, so the original year + edition-count idea changes to year + pages.

---

## 8. Deliverables map (PDF)
| PDF item | Where |
|---|---|
| Three scraper scripts | `scrapers/ia_api_scraper.py`, `ia_bs4_scraper.py`, `ia_selenium_scraper.py` (+ common, manifest builder) |
| Same fields, CSV | `data/benchmark_200_{api,bs4,selenium}_run<N>.csv`, `data/training_api.csv` |
| ss, iftop/nload, tcpdump, Wireshark | `notebooks/networking_analysis.ipynb` + `screenshots/` (pcaps in `captures/`, not committed) |
| ufw, threads, rate limiting, proxy (optional) | same notebook, separate section, not in baseline table |
| EDA + ML | `notebooks/ml_analysis.ipynb` (Jupyter/Colab) |
| Final report PDF | `report/` — sections follow the PDF's 5 sections, labels [M]/[E]/[S], limitations, repro commands, manifest hash |
| 10-min presentation | performance charts, network trace visuals, ML results; ≈ 1 min intro, 3 min scraping+design, 3 min network, 2 min ML, 1 min conclusion; both speak |

Conclusion must contain: best method for efficiency **and** stability with the evidence table; failure/429/ufw behavior; when BS4/Selenium are still right; best thread/delay/retry settings; ML results vs baselines; limitations (one network, one site, snapshot, views discrepancy).

---

## 9. Decisions needed from the team
| ID | Decision | Recommended default |
|---|---|---|
| D1 | Final pool query (year 1800–2020, imagecount 50–1500, keep `subject:fiction`) | As in §3.1 |
| D2 | Duplicate caps | 1 per group for the 200, ≤3 per group for training |
| D3 | API batch size | Test 10/50/100, use the largest that works |
| D4 | Request pacing | 3 s baseline; confirm against `bots.html` first |
| D5 | User-Agent contact text | Project name + version; contact policy by the team |
| D6 | Selenium page-load strategy | `normal` for the benchmark |
| D7 | ufw not enforcing in WSL | Document, use equivalent, state it |
| D8 | Unthrottled thread test | Skip, or ≤30 records / ≤4 workers |
| D9 | Row 6 in the spreadsheet and instructor | Update to Internet Archive; tell the instructor/lab doctor |
| D10 | Who does what (Mohammad / Issa) | Suggestion: scrapers + captures vs data/ML + notebooks; swap for review |

---

## 10. Schedule (19–25 Nov) and risks
| Day | Work |
|---|---|
| Thu 19 | Approve plan; update README/config/checklist; install ML packages (Windows Python or Colab, not the slow WSL venv); no collection |
| Fri 20 | Build common module + three scrapers; tooling checks (tcpdump permissions, tshark, ss, iftop, nload, ufw enforcement); pool snapshot; manifest; 10-record smoke test |
| Sat 21 | 200-record validation (3 methods, view-difference table); benchmark runs with captures (long, run in background) |
| Sun 22 | Threads, rate limit, ufw block/recovery; API 2,000 collection; cleaning/EDA/ML; networking notebook |
| Mon 23 | ML notebook, report, slides, rehearsal (target finish) |
| Tue 24 | Buffer (DS project due) |
| Wed 25 | Deadline |

Cut order if behind: proxy → K-Means → unthrottled threads → repeats from 3 to 2 for HTML methods (state it) → training size below 2,000 (state the real size).
Risks: Archive rate limiting or outages (back off, report), ufw under WSL, Selenium timeouts, pcap size, low model skill (report honestly), time overlap with finals and other jobs.

---

## 11. Checklist

### M0 — Approve and migrate (Thu 19)
- ✅ Repo, folders, WSL venv, Chrome/Selenium working
- ✅ Internet Archive 10-record pilot with all three methods, timings and view comparison
- ⬜ Team/instructor decision D1–D10 (§9)
- 🔧 Update `README.md`, `scrapers/config.py`, row 6; retire Open Library wording; keep prior evidence
- 🔧 Replace the old checklist with this one; review and commit the untracked Codex files (no bulk raw HTML)
- ⬜ Re-read Internet Archive automated-access guide and record limits

### M1 — Environment and tooling checks (Fri 20)
- ⬜ `tcpdump` (sudo), `tshark`, `ss`, `iftop`, `nload` run in WSL; capture interface chosen and noted
- ⬜ `ufw` enforces rules in WSL (feasibility test with a harmless rule)
- ⬜ ML packages available (Windows Python/Colab); notebook tooling works
- ⬜ Selenium performance-log capture verified on 2–3 pages

### M2 — Data definition, snapshot, scrapers (Fri 20)
- ⬜ Pool snapshot saved with `numFound`, query, timestamp, hash
- ⬜ Group key and seeded order; `benchmark_200_ids.json`; exclusion log
- ⬜ `ia_common.py` with limiter, retries/backoff, breaker, logging, checkpoint
- ⬜ Three scrapers writing the same fields and provenance columns
- ⬜ 10-record smoke test against the old pilot values (title/creators/year/subjects/pages/addeddate must match; views differences recorded)

### M3 — 200 records, three methods (Sat 21)
- ⬜ 200 ids × 3 methods, each its own CSV
- ⬜ Coverage table: matched in all three, missing, per-field differences, per-record view differences
- ⬜ Failures/retries listed; nothing filled from another method

### M4 — Benchmark with network evidence (Sat 21–Sun 22)
- ⬜ 9 runs (rotated order), one pcap each, `ss` log, iftop/nload screenshots, client JSONL logs, Selenium browser-log
- ⬜ Metrics table: one row per run + median/mean/min/max per method; total/sleep/active time separate; outliers kept
- ⬜ Wireshark screenshots (conversations, IO graph, TCP RTT, TLS SNI/hosts)
- ⬜ Measured / explanation / estimate labels applied

### M5 — Security experiments (Sun 22)
- ⬜ ufw deny out 443: fail → delete only that rule → recover → original state restored, with evidence
- ⬜ Rate-limit test; threads {1,2,4} with global cap
- ⬜ Proxy (optional)

### M6 — Training data and ML (Sun 22)
- ⬜ API collection of ~2,000 usable records (batch size tested first, paced, resumable)
- ⬜ Cleaning log, EDA notebook sections
- ⬜ Grouped split, baselines, regression, classification, metrics vs baselines
- ⬜ K-Means (additional) and cluster profile
- ⬜ ML notebook saved with outputs

### M7 — Report and presentation (Mon 23)
- ⬜ Networking notebook with charts and screenshots
- ⬜ Report PDF with conclusion, limitations, reproducibility section
- ⬜ 10-minute presentation, rehearsed, both speak
- ⬜ Repo final: three scripts, two notebooks, report PDF, README with run instructions
