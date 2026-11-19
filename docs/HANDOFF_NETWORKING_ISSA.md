# Networking handoff for Issa

Mohammad's part (scrapers, manifest, data collection) is finished. **The saved CSVs and logs cannot give networking
measurements.** The final comparison (time, bandwidth, requests, latency with `ss`, `iftop`/`nload`, `tcpdump`, Wireshark)
must come from **re-running the scrapers on your machine while capturing traffic**. All timings already in the repo are
pilot/collection timings (they include deliberate 3 s waits) and must not be used as the final comparison.

## 1. Install (once)
Follow `docs/SETUP_UBUNTU_VM.md` (packages, venv, Chrome/Chromium + driver, `python scrapers/check_selenium_env.py`).
Install `tcpdump tshark iftop nload ufw` and Wireshark.

## 2. The fixed input
All three scrapers read the same list: `data/manifest/benchmark_200_ids.json` (200 identifiers, reproducible sample).
It is the default `--ids`; do not change it. Use `--limit 10` only for quick checks.

## 3. Run one scraper (always a **fresh** collection)
```bash
source .venv/bin/activate
python scrapers/ia_api_scraper.py      --out-root measurements/runs --label net_run1
python scrapers/ia_bs4_scraper.py      --out-root measurements/runs --label net_run1
python scrapers/ia_selenium_scraper.py --out-root measurements/runs --label net_run1      # add --headless if no desktop
```
Why this is always fresh: every run creates a **new** timestamped folder and refuses an existing one; nothing is cached
(BS4 uses a new `requests.Session`, Selenium a new temporary Chrome profile, no HTML is saved). Never pass `--resume`
for a measured run. After each run check `run.json`: `"resumed": false`, `records_saved: 200`, `status_counts` (all `ok` expected).
Pacing is the same for all methods (3 s gap, `--delay` / `LABNET_DELAY`). Keep it, and state it in the report.

## 4. Per-run capture procedure (suggested)
Open 3–4 terminals; start the capture first, stop it after the scraper has finished.
```bash
# A  packets (PDF command), one file per method/run
mkdir -p captures measurements
sudo tcpdump -i any port 80 or 443 -w captures/bs4_run1.pcap

# B  connections once per second (for Selenium use the browser name instead of python)
while true; do date +%s.%N; ss -t -a | grep -E 'python|chrom'; sleep 1; done > measurements/bs4_run1_ss.log

# C  bandwidth screenshots
sudo iftop -i any          # or: nload
# text log of iftop over N seconds:  sudo iftop -i any -t -s 60 > measurements/bs4_run1_iftop.txt

# D  the scraper (section 3)
```
Suggested order for 3 runs per method (reduces order/time-of-day bias): run 1 API→BS4→Selenium, run 2 Selenium→API→BS4,
run 3 BS4→Selenium→API. Same network, nothing heavy in the background. Open the pcaps in Wireshark (Statistics → Conversations,
IO Graph, Endpoints; filter by TLS SNI `archive.org`) and save screenshots for the notebook.

## 5. Where each PDF metric comes from
| PDF metric | Source |
|---|---|
| Method | scraper (`api`, `bs4`, `selenium`) |
| time (s) | `run.json` → `segments[].total_s`; also `pacing_sleep_s`, `backoff_sleep_s`, `active_s_estimate` (report total **and** active time; the deliberate waits dominate) |
| #requests | `attempts.csv` (one row per HTTP/navigation attempt, retries included). Selenium also: `page_metrics.csv` (`requests` = browser sub-requests per page) |
| avg latency (ms) | `attempts.csv` → `elapsed_s` (mean, median, max; keep outliers). TCP RTT/handshake from the pcap as a second, differently labelled number |
| bandwidth (KB) | the **pcap** (bytes to/from archive.org hosts). Secondary: `run.json` → `decoded_body_bytes_total` (API/BS4, decoded body only) and Selenium `page_metrics.csv` → `encoded_bytes` (browser-reported). Do not call decoded bytes "wire bandwidth" |
| connections | your `ss` log |
| failures/retries | `run.json` (`status_counts`, `retry_attempts_total`), `attempts.csv` (`outcome`, `backoff_wait_s`, `retry_after_s`) |

Log files live in each run folder (`measurements/runs/<method>_<timestamp>_<label>/`):
`<method>.csv`, `records.jsonl`, `attempts.jsonl`, `attempts.csv`, `run.json`, and for Selenium `page_metrics.csv`.
Column meanings: `docs/DATA_DICTIONARY.md`.

Things to say in the report instead of hiding:
- The first Selenium page of a run loads many assets into an empty profile (3.8 MB for the first page of the 200-book collection, then a median of 144 KB and
  50 browser requests per page; these are browser-reported numbers from the collection run, not measurements).
- For orientation only (collection run, includes the 3 s waits): API 8 requests; BS4 200 requests (about 229 KB decoded HTML each); Selenium 200 navigations.
- Chrome may also contact other hosts (updates, Google services). Separate them in Wireshark by SNI/IP. Check whether Chrome used QUIC (UDP 443).
- Views from the API are slightly higher than the page counter for most books (see `data/benchmark_200_comparison/`); this is data quality, not a networking result.

## 6. Firewall block / recovery (ufw)
```bash
sudo ufw status verbose                       # note the starting state (active/inactive, rules)
export LABNET_MAX_RETRIES=1 LABNET_CONNECT_TIMEOUT=5     # make the failure quick
python scrapers/ia_bs4_scraper.py --limit 3 --out-root measurements/runs --label ufw_before
sudo ufw deny out to any port 443             # (enable ufw if it was inactive; remember to restore that state)
python scrapers/ia_bs4_scraper.py --limit 3 --out-root measurements/runs --label ufw_blocked
sudo ufw status numbered                      # screenshot: the rule is active
sudo ufw delete deny out to any port 443      # remove ONLY this rule
python scrapers/ia_bs4_scraper.py --limit 3 --out-root measurements/runs --label ufw_recovered
```
Expected while blocked: `attempts.csv` shows timeouts/connection errors, retries with backoff, records with `status=failed`.
The circuit breaker stops a run after 5 failed records in a row (by design). `deny` silently drops packets, so connections time out;
`ufw reject out ...` fails immediately (optional contrast). Earlier labs found this test inconclusive under WSL; verify that the rule really blocks.

## 7. Not implemented (decide with Mohammad)
- **Multithreading, rate-limit comparison and proxy** are not in the scrapers (no `--workers` option). `ia_common.Pacer`
  (global pacing, thread-safe), `Client`, and `Run` logging are written to be reusable. If you add threads, keep a **shared** pacer so
  the total request rate is not multiplied by the number of threads, and do not run unthrottled tests against archive.org.
- Pacing is a gap between the end of one request and the start of the next, not a start-to-start rate.

## 8. Be polite and stop on warnings
The scripts stop on HTTP 403, a verification page, an over-long `Retry-After`, or 5 failed records in a row, and they slow
down automatically on 429/503. If a run aborts, read the `ABORTED:` line and `run.json`; do not work around it. Do not repeat the
200-book runs more often than needed (9 runs are planned). Archive.org's rules: https://archive.org/developers/bots.html
