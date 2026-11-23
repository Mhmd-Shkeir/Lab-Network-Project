# Website Data Collection Efficiency and Network Behavior

## Internet Archive: API, Requests/BeautifulSoup, and Selenium

**Team:** Issa and Mohammad  
**Course:** Network Programming  
**Report date:** 22 November 2026  
**Status:** Analysis and evidence complete. This is a one-run macOS comparison; platform and sample limitations are disclosed.

## Executive summary

The project implements three collectors for the same 200 Internet Archive items and preserves a separate 5,600-item API dataset for analysis. All 200 benchmark records are complete for each method. The API and HTML page views differ for 195 items; the API count is higher in the saved comparison, while BS4 and Selenium agree. The captured one-run benchmark supports the API as the most efficient choice for structured metadata: it completed in 31.0 seconds with 163.2 KB of endpoint IP traffic and eight HTTP attempts, compared with 27.7–28.5 minutes for BS4 and Selenium. BS4 transferred 11.37 MB; Selenium transferred 18.63 MB across captured Archive endpoints and generated 8,933 browser resource-request events. All methods saved 200/200 records with no retries. Request counts use different definitions across HTTP clients and browser telemetry.

The final paired popularity experiment uses 17,727 complete-case items and a fresh, work-grouped holdout. Adding descriptions raised low/medium/high classification accuracy from 57.35% to 59.35%; the model remains below the requested 80% target. The numeric model with descriptions achieved log-view R-squared 0.419 and raw-view MAE 255.36. Separate description-based genre and archive-juvenile-marker classifiers scored 86.26% and 82.54%, respectively; these are different tasks and do not satisfy the popularity-accuracy target. A separate children-audience experiment scored 85.57% against provisional AI-generated labels and needs human label review. All popularity results estimate engagement with existing archived copies, not future book sales or worldwide popularity.

## 1. Objective and target

We compare the time, traffic volume, request behavior, latency, and data completeness of an API collector, Requests/BeautifulSoup (BS4), and browser-based Selenium. The target is the Internet Archive (archive.org). The shared fields are identifier, title, creators, publication year, subject tags, language, added date, scanned page count, and all-time views.

## 2. Collection design and implementation

- Fixed benchmark: 200 IDs, collected independently by each of the three methods.
- Training data: 5,600 API records, including the 200 benchmark items plus 1,800 records per genre.
- Responsible access: identifying User-Agent, three-second sequential pacing, retry/backoff, and bounded concurrency with a single global request-start limiter.
- Reproducibility: frozen ID manifests, source-pool snapshots, run logs, checksums, and field-level method comparison are retained in the repository.

The 200-item benchmark supports the method comparison. The larger API dataset supports exploratory analysis and regression; it is not a replacement for the method benchmark.

## 3. Data quality and method agreement

| Method | Benchmark rows | Complete (`ok`) |
|---|---:|---:|
| API | 200 | 200 |
| BS4 | 200 | 200 |
| Selenium | 200 | 200 |

For the shared fields, methods agree on all fields except one subject list and all-time views. The subject discrepancy occurs for one item. API all-time views differ from page values for 195 items (API minus page: minimum 1, median 2, maximum 82); BS4 and Selenium agree on page values. The reason for the API/page counter discrepancy has not been established and the values remain unaltered.

The original training CSV has 5,600 usable records and 5,391 distinct `work_group`s, with at most three items per group; the expanded linked dataset is described in Section 6. A source shift is visible: the Americana subset has median views of 282 in this full dataset, while the wider English-text pool has median views of 97. The precise Americana median differs from the genre-only comparison noted in the data dictionary because this whole-dataset figure also includes benchmark fiction records.

## 4. Network measurement protocol

### Baseline results

All three full baselines are complete: the same 200 IDs, the Mac interface, headless Selenium, and default three-second pacing. Values are single-run observations, not repeated-run estimates. API and BS4 traces are filtered to verified Internet Archive endpoint IPs; Selenium captures IPs resolved from resource hostnames in its smoke run. Selenium may contact additional hosts, so pair captured bytes with browser telemetry and disclose this scope.

| Method | Archive endpoint IP KB | Elapsed seconds | Request count | Mean client-call duration | Successes / 200 |
|---|---:|---:|---:|---:|---:|
| API | 163.2 | 30.988 | 8 | 1.204 s | 200 |
| BS4 | 11,368.3 | 1,664.082 | 200 | 5.323 s | 200 |
| Selenium | 18,634.7 | 1,712.765 | 8,933 browser events | 5.474 s/navigation | 200 |

**Metric definitions:** API/BS4 request count sums one plus redirects for every HTTP attempt, including retries. Selenium request count sums browser resource-request events; report its 200 page navigations separately. API/BS4 client duration is HTTP attempt duration; Selenium client duration is page navigation/readiness duration. The packet-level TCP ACK RTT summary is supplemental and is shown in the notebook. Captured IP-layer bytes are not decoded response-body bytes. These are one-run values; Selenium also completed 200 page navigations. Its IP capture covers endpoints resolved from hostnames in its smoke run and may omit additional browser hosts.

The Wireshark ACK-RTT distributions have sub-millisecond medians despite internet-host connections, so they are retained as packet-analysis observations but not treated as reliable end-to-end latency. The per-request and page-navigation durations are the primary latency measures.

### Platform limitation

These baseline runs are captured on macOS because that is the available machine. The Mac runner uses `lsof` instead of Linux `ss`. macOS does not include `ufw`; the PF demonstration below is a platform-specific substitute, not literal UFW evidence. If the rubric requires UFW/`ss` specifically, those requirements need a Linux environment.

## 5. Firewall, rate limiting, and concurrency

The API scraper was run on the same 20-ID subset with one and two workers and the same three-second global request-start interval:

| Workers | Successes | HTTP attempts | Minimum start gap | Max in flight | Elapsed seconds | Retries |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 20/20 | 8 | 2.993 s | 1 | 21.894 | 0 |
| 2 | 20/20 | 8 | 2.996 s | 1 | 21.854 | 0 |

The two-worker run did not shorten this workload: the global limiter kept starts three seconds apart, and observed maximum concurrency stayed at one. This confirms the rate limit was shared across workers for these short API calls; it is not evidence that more workers improve throughput. Raw run metadata is in `report/rate_limit_experiment.csv`. The project also records 24 offline tests for the shared limiter and retry behavior.

**Firewall block/recovery:** the macOS `pf` demonstration passed for `archive.org` at `207.241.224.2:443`: HTTPS returned HTTP 200 before the rule, timed out while the scoped outbound rule was active, and returned HTTP 200 after rule removal. The script released its PF enable token; the log confirms PF was disabled after cleanup. Evidence is in `screenshots/mac_pf_firewall_demo.png` and `measurements/logs/mac_pf_demo_20261122_030455_9128.log`. This is a macOS PF substitute, not UFW; a strict UFW requirement would still require Linux. Proxy configuration is optional in the assignment's technical section.

## 6. Machine-learning analysis: classification and regression

The coworker expanded the linked data to 20,271 Archive items matched to Open Library works, of which 17,727 complete-case records form the paired popularity cohort. Model selection used grouped five-fold cross-validation; the fixed holdout contains 3,006 records from 2,886 work groups, selected from new Open Library work IDs absent from the earlier 5,600-item collection. Both A/B variants use the same cohort and split. Variant A uses metadata; variant B adds the Open Library description. Full manifests, predictions, fold results, confidence intervals, and code are retained under `report/ml/` and `notebooks/05_popularity_description_comparison.ipynb`.

### Low / medium / high popularity classifier

The target is low, medium, or high all-time Archive views. The CV-selected logistic regression scored 57.35% accuracy without descriptions and 59.35% with descriptions on the fresh holdout. The majority baseline scored 35.20%. Five-fold grouped CV accuracy was 57.05% (SD 0.79 points) for A and 57.91% (SD 0.93 points) for B; the saved paired bootstrap estimates a +2.02 percentage-point holdout accuracy gain from descriptions (95% CI +0.70 to +3.39). The description model is better than baseline but does **not** meet the requested 80% accuracy threshold.

| Popularity classifier | Holdout accuracy | Macro F1 |
|---|---:|---:|
| Majority baseline | 35.20% | 0.174 |
| Metadata only (Logistic Regression) | 57.35% | 0.565 |
| Metadata + description (Logistic Regression) | 59.35% | 0.585 |

### Numeric view prediction

The regression predicts log-transformed Archive views. It has no classification accuracy; report MAE and R-squared instead. The CV-selected Ridge model with descriptions achieved R-squared 0.419 on log views and raw-view MAE 255.37, compared with 0.400 and 257.40 without descriptions. A median baseline had raw-view MAE 293.26. This is a modest improvement and individual errors remain substantial.

| Regressor | Log-view R-squared | Log-view MAE | Raw-view MAE |
|---|---:|---:|---:|
| Median baseline | -0.013 | 0.910 | 293.26 |
| Ridge, metadata only | 0.400 | 0.676 | 257.40 |
| Ridge, metadata + description | 0.419 | 0.669 | 255.37 |

### Other classification tasks above 80%

The coworker also created distinct classification experiments. These results must not be presented as popularity prediction:

- **Three-genre classification:** LinearSVC using descriptions scored 86.26% holdout accuracy, 0.859 macro F1, and 0.857 balanced accuracy across science fiction, fantasy, and mystery/thriller. Features exclude the subject tags used to define the genre labels. The labels still reflect catalogue tagging, and author overlap is reported in the saved results.
- **Archive juvenile-marker classification:** a model using descriptions scored 82.54% accuracy, 0.792 macro F1, 0.808 balanced accuracy, and 0.710 F1 for the positive juvenile-marker class. It predicts whether the Archive metadata contains a `juvenile` marker; absence of that marker does not mean the book is for adults.
- **Children intended-audience experiment:** the description model scored 85.57% accuracy on 291 fresh records, but labels were assigned by an AI under written rules and have not yet been validated by a human. Its score measures agreement with provisional labels, not verified audience classification. The repository contains an 80-record blind review sheet; the human label and note columns are blank and need to be completed before presenting this as validated.

All tasks use grouped evaluation and save splits and predictions in `report/ml/`. Accuracy depends on the task, cohort, and labels; only the first task above is the requested low/medium/high popularity classifier. No popularity model currently achieves 80% on the documented holdout.

## 7. Recommendation

Use the API when a supported endpoint supplies the needed fields. In the captured one-run comparison it completed the 200-item workload in 31.0 seconds and transferred 163.2 KB of endpoint IP traffic, versus roughly 28 minutes and 11.4–18.6 MB for BS4 and Selenium. All three saved 200 records without retries. Request-event definitions differ, and the one-run design limits generalization. Use BS4 when required fields are only available on the HTML page; use Selenium when browser rendering is essential and its added page resources are justified by the task.

For all methods, retain the identifying User-Agent, bounded request rate, retries, and failure logging. Do not use more workers as a way to bypass the global rate limit.

## 8. Limitations

- The benchmark is a single frozen 200-item sample, not a broad sample of all archive.org pages.
- API and page view counters are not identical; the cause has not been verified.
- Runs include deliberate three-second pacing, and the comparison contains one captured run per method.
- Selenium's endpoint-filtered trace covers IPv4 hosts from the smoke run; resources on unobserved hosts may be omitted from its packet-byte total.
- Packet-derived ACK-RTT medians were below 0.1 ms and are not used as end-to-end latency estimates.
- macOS `lsof` and `pf` are documented substitutes, not the requested Linux `ss` and UFW.
- The training sample is curated and genre rules are heuristic; results do not represent all books or predict future publication success. Open Library engagement counts were retrieved on 22 November, three days after the Archive view snapshot, and should be treated as near-contemporary cross-catalog signals. The children-audience labels are provisional AI-generated labels pending human review.
- Open Library coverage is incomplete and `osp_count` is sparse; model performance may differ for unmatched works or when these external counts change over time.

## 9. Open Library data reference

The enrichment uses Open Library Search API fields joined by exact Internet Archive identifier. `ratings_count` counts ratings, `readinglog_count` counts user reading-log entries, `edition_count` counts editions of a work, and `osp_count` records Open Syllabus appearances where available. Search API documentation: https://openlibrary.org/dev/docs/api/search. Field guide: https://openlibrary.org/search/howto/more. API use guidance: https://openlibrary.org/developers/api.
