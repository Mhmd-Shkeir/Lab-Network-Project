# Ten-minute presentation outline

**Status:** Report PDF and network evidence are complete; build the ten-minute slide deck and state that macOS PF is a platform substitute, not UFW. Suggested division: Issa presents networking and security; Mohammad presents collection and ML; both give the recommendation.

| Slide | Time | Speaker | Content |
|---|---:|---|---|
| 1. Project and question | 0:40 | Both | Internet Archive; compare API, BS4, and Selenium for a fixed 200-item workload. |
| 2. Dataset and collectors | 1:00 | Mohammad | Shared fields, 200 benchmark records per method, separate 5,600-row API training set. |
| 3. Network measurement method | 1:00 | Issa | Same Mac interface, three-second pacing, endpoint-scoped packet bytes, request counts, client durations, and platform limits. |
| 4. Captured performance results | 1:40 | Issa | Single-run values for bytes, elapsed time, requests, latency, completeness. State that there are no repeated-run medians. |
| 5. Traffic and security | 1:30 | Issa | Wireshark Conversations/I/O graph/RTT screenshots; PF HTTPS block/recovery evidence; clearly disclose that macOS PF is not UFW. |
| 6. Rate limiting and threading | 1:00 | Issa | 20-ID API check: 1 vs 2 workers at a shared 3-second interval, with no speedup and no retries. |
| 7. EDA and ML models | 1:30 | Mohammad | Views skew and source difference; shared work-group holdout; text classifier (69.2% with Open Library counts vs 58.8% baseline; 65.0% grouped CV; 32.1% majority baseline) and numeric regression (MAE 263 views vs 317 baseline, 358 majority baseline). Explain that 69.2% is below the requested 80%, and regression uses error metrics, not accuracy. |
| 8. Recommendation and limitations | 1:40 | Both | API preference supported by the captured one-run comparison; state the one-run and endpoint-scope limits. Discuss archived-item views, source/genre bias, and one-holdout limit. |

## Evidence to insert

- Slide 4: `report/network_measurements.csv` and `report/network_summary.csv`; the executed notebook contains the completed one-run comparison.
- Slide 5: selected labeled screenshots from `screenshots/`.
- Slide 6: `report/rate_limit_experiment.csv`; do not treat offline tests as live results.
- Slide 7: charts and holdout metrics from `notebooks/ml_analysis.ipynb`.
