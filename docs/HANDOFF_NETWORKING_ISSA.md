# Networking handoff for Issa

The final data is collected. Your task is to produce the measured network comparison and security experiments by running the three scrapers under capture. Start with [Ubuntu setup](SETUP_UBUNTU_VM.md). Use the [data dictionary](DATA_DICTIONARY.md) for output columns.

## First smoke check

Use one Linux environment for all three methods. If the Mac's Ubuntu browser cannot be made to work, run **all three measured methods** on another working Linux environment; mixing one method from another computer confounds the comparison.

```bash
source .venv/bin/activate
python scrapers/check_selenium_env.py
python scrapers/ia_api_scraper.py --limit 3 --out-root measurements/runs --label smoke
python scrapers/ia_bs4_scraper.py --limit 3 --out-root measurements/runs --label smoke
python scrapers/ia_selenium_scraper.py --limit 3 --out-root measurements/runs --label smoke
```

Each smoke run contacts the website. Confirm logging and capture on this small workload before the 200-item runs. These initial runs validate setup; keep them separate from the main benchmark.

## Capture one full run

Find the VM's network interface with `ip -brief address` and `ip route show default`. Replace `ens33` below with the actual interface. Use that same interface for packet and bandwidth observation.

```bash
mkdir -p captures measurements
TASK_IFACE=ens33
sudo tcpdump -i "$TASK_IFACE" -n -s 0 -w captures/bs4_run1.pcap 'port 80 or port 443 or port 53'
```

Start capture first. In another terminal, log connections, including process names and UDP:

```bash
while true; do
  date -Is
  ss -tanp
  ss -uanp
  sleep 1
done > measurements/bs4_run1_ss.log
```

Observe bandwidth with `sudo iftop -i "$TASK_IFACE"` and `nload "$TASK_IFACE"`; save screenshots. An optional text observation is `sudo iftop -i "$TASK_IFACE" -t -s 60 > measurements/bs4_run1_iftop.txt`. This covers 60 seconds, not necessarily the full run.

Run one collector in another terminal:

```bash
python scrapers/ia_bs4_scraper.py --out-root measurements/runs --label net_run1
```

For other methods substitute `ia_api_scraper.py` or `ia_selenium_scraper.py`. Stop the capture and connection logger after that collector finishes. Use distinct filenames and labels for every run.

The default input is `data/manifest/benchmark_200_ids.json`. Keep these 200 IDs fixed. Never use `--resume` in a fresh measurement: each run should have `resumed: false`, 200 saved records and a checked status breakdown in `run.json`. Record any failures rather than replacing the data from another method.

## Comparison protocol

Perform three runs per method. Rotate order: API/BS4/Selenium, then Selenium/API/BS4, then BS4/Selenium/API. Keep the network, machine, three-second delay and browser mode consistent. Use a new browser profile per run, as the script already does; a new profile does not reset server or operating-system caches.

| Metric | Definition and source |
|---|---|
| Elapsed seconds | `run.json` segment `total_s`; includes browser startup where applicable. Report pacing, backoff and estimated active time separately. |
| API/BS4 request count | Sum `1 + redirects` across HTTP attempt rows; retries remain included. |
| Selenium request events | Sum `requests` in `page_metrics.csv`; these are browser resource-request events, which can include cache activity, rather than a count inferred from encrypted packets. Report the 200 page navigations separately. |
| Client-call duration | API/BS4: `attempts.csv.elapsed_s` is an HTTP call duration. Selenium: it is navigation/readiness duration. Label these distinct scopes; do not describe a browser navigation as one resource's HTTP latency. |
| Network latency | TCP RTT from packet evidence, labelled separately from client-call durations. Identify any UDP/QUIC traffic rather than treating it as TCP. |
| Transferred KB | Captured bytes in both directions for the scraper's flows, with the byte layer/unit stated. Include related service/CDN hosts needed by the page; separate unrelated background traffic. |
| Completeness/stability | Status counts, retries, errors, timeouts and comparison results. |

Keep every run and valid slow request. Report per-run values and medians; compare like workloads. Browser-reported encoded bytes and decoded response-body bytes are secondary measurements, not packet-level bandwidth.

In Wireshark, identify hosts using DNS/TLS information, then inspect entire corresponding conversations. An SNI filter alone shows handshake packets, not every byte of a connection. The capture includes port 53 for ordinary DNS and UDP 443 for possible QUIC; encrypted DNS may appear differently. Save conversations, IO graphs and latency screenshots. Explain the mean-latency scope in the notebook before interpreting the table.

## Firewall and threading experiments

Keep experiments separate from the baseline. Record `sudo ufw status verbose` and the initial rules. In an isolated VM, verify ufw is active, then demonstrate working HTTPS, add a temporary outbound port-443 deny rule, observe failure, remove only that rule and demonstrate recovery. Restore the original state. Use a small workload; shorter retry/timeouts can be set in that terminal with `LABNET_MAX_RETRIES=1`, `LABNET_CONNECT_TIMEOUT=5` and `LABNET_READ_TIMEOUT=5`. Restore ordinary settings before baseline measurements. Preserve captures and screenshots proving each state.

### Multithreading and rate limiting (`--workers`, `--min-interval`)

Implemented and tested **offline only** (local fake servers; 24 offline tests pass on Windows and Linux/WSL); it has not been run against archive.org.

How it works:
- `--workers N` runs N worker threads (API: batches in parallel; BS4: one page per task; Selenium: one Chrome per worker). The number of workers is bounded: 1–8, Selenium 1–4.
- All workers share **one global limit**: request **starts** (first tries *and* retries) are at least `--min-interval` seconds apart, so the total rate is at most 1 / `--min-interval` whatever N is. More workers only overlap the waiting for slow responses. `--min-interval` below 0.5 s is refused.
- A 429/503 doubles the shared interval and pauses **all** workers for `Retry-After`; HTTP 403, a verification page or 5 failed records in a row stop every worker.
- Without `--workers` the scrapers behave exactly as before (sequential, `--delay` seconds between the *end* of one request and the *start* of the next). The two modes are **not** the same limiter: for a fair sequential-versus-threaded comparison use `--workers 1` as the control, so every run uses the same start-to-start limiter.
- Each worker has its own connection (`requests.Session` / Chrome), so `ss` shows up to N connections.

Smoke check first (a few requests only):
```bash
python scrapers/ia_bs4_scraper.py --workers 2 --min-interval 1 --limit 6 --out-root measurements/runs --label thr_smoke
```

Threading experiment (separate from the baseline; BS4 is the suggested method; same 200 ids, same cap for every worker count):
```bash
# cap = 1 request start per second for the whole program, control then 2 and 4 workers
python scrapers/ia_bs4_scraper.py --workers 1 --min-interval 1 --out-root measurements/runs --label thr_w1_i1_run1
python scrapers/ia_bs4_scraper.py --workers 2 --min-interval 1 --out-root measurements/runs --label thr_w2_i1_run1
python scrapers/ia_bs4_scraper.py --workers 4 --min-interval 1 --out-root measurements/runs --label thr_w4_i1_run1
# same again with the baseline cap of 3 s (expect little difference, see below)
python scrapers/ia_bs4_scraper.py --workers 1 --min-interval 3 --out-root measurements/runs --label thr_w1_i3_run1
python scrapers/ia_bs4_scraper.py --workers 2 --min-interval 3 --out-root measurements/runs --label thr_w2_i3_run1
python scrapers/ia_bs4_scraper.py --workers 4 --min-interval 3 --out-root measurements/runs --label thr_w4_i3_run1
```
Optional: `ia_api_scraper.py --workers 2 --min-interval 3 --batch-size 10 ...` (use `--batch-size 10` so there are enough batches to share) and `ia_selenium_scraper.py --workers 2 --min-interval 3 ...` (heavy, one Chrome per worker). Repeat each setting (the team protocol uses three runs), start the packet capture first as above, and do not go below `--min-interval 1` on archive.org without agreeing it with Mohammad.

Rate-limit comparison: run the same `--workers 1` command with different `--min-interval` values (for example 3 and 1) and compare `total_s`, `pacing_sleep_s`, retries and any 429/503.

Check each run in `run.json` → `rate_limit`:

| Field | Meaning |
|---|---|
| `mode`, `workers`, `interval_s` | settings used (`shared_start_interval`; sequential runs show `sequential_gap`) |
| `min_start_gap_s` | smallest gap between any two request starts; should be about `interval_s` or larger (small timer jitter is possible) |
| `max_requests_in_flight` | most requests running at once; must be ≤ `workers` |
| `attempts_per_second_overall` | attempts / observed span; must stay below 1 / `interval_s` |
| `interval_s_at_end` | larger than `interval_s` if a 429/503 made the run slow down |

`attempts.csv` now also has `t_start_s`, `t_end_s` (seconds since the run began) and `worker`, so you can plot concurrency over time. With several workers the sleep totals in `run.json` are summed over threads and `active_s_estimate` is `null`; compare `total_s` instead.

What to expect (hypotheses, **not results**): the collection run had a median BS4 request time of about 1.2 s. With a 3 s cap the limiter, not the latency, sets the speed, so 1, 2 and 4 workers should take about the same total time; with a 1 s cap one worker is limited by the 1.2 s latency and two or more workers should approach the cap. Report what you actually measure, including any increase in per-request latency or failures with more workers. Proxy setup is optional.

## Outputs to return

Commit the networking notebook, readable measurement tables and selected screenshots. Preserve raw captures locally or in an agreed shared location: `.pcap` files and `measurements/` are intentionally ignored by Git. Return the run settings and exact repository commit used. The project still needs the ML notebook, optimization report and ten-minute presentation.
