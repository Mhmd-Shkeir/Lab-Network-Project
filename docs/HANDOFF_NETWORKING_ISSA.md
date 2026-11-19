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

**Multithreading is still to be implemented**, with Mohammad's code support. The existing sequential pacer does not guarantee a global limit when multiple workers call it concurrently. Add/test a bounded workers option and shared rate limiter locally first; then compare workers 1/2/4 with the same total request cap. Do not run an unthrottled experiment on archive.org. Rate-limit comparisons are also pending; proxy setup is optional.

## Outputs to return

Commit the networking notebook, readable measurement tables and selected screenshots. Preserve raw captures locally or in an agreed shared location: `.pcap` files and `measurements/` are intentionally ignored by Git. Return the run settings and exact repository commit used. The project still needs the ML notebook, optimization report and ten-minute presentation.
