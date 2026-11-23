# macOS measurement workflow

This Mac has Chrome, `tcpdump`, `iftop`, and `nload`. macOS is not Linux: it does not provide `ufw` or `ss`. The supplied runner can collect the same fixed 200-item workload with a separate packet capture for each run, but a `pf` firewall demonstration is not the assignment's literal UFW demonstration. State this limitation in the report or use a Linux VM/host for that requirement.

## Before the baseline

1. From Terminal, use the repository root. Create the documented `.venv` if needed.
2. Confirm the Selenium environment: `.venv/bin/python scrapers/check_selenium_env.py --headless`.
3. Confirm the interface printed by `route -n get default` (normally `en0`) is the active Internet interface.
4. Pause unrelated downloads, cloud sync, streaming, and browser traffic. The initial all-interface capture can include substantial unrelated traffic; retain endpoint-filtered traces for the comparison.
5. In another Terminal window, run `sudo iftop -i en0` and `nload en0` during a baseline run. Save screenshots with `Shift-Command-4` to `screenshots/` and include a short caption naming the method and repetition. Screenshots are required human evidence.

## Run the baseline captures

Start the runner from the repository root in an interactive Terminal:

```bash
./run_mac_baseline.sh en0 1
```

Enter the Mac administrator password only in Terminal when `sudo` prompts; do not put it in chat. The second argument selects 1-3 repetitions. With `1`, the runner captures one full 200-item run of API, BS4, and headless Selenium in that order. With `3`, it rotates order across all nine runs. It uses the fixed 200-ID manifest and the project's three-second pacing, and stores run folders, logs, and `.pcap` files under ignored `measurements/`. Each run is captured separately. Do not use the saved smoke runs or the historical `data/runs/` timings as baseline measurements. One repetition gives a first comparison, not the planned three-run medians.

The current one-repetition plan is one full 200-item run per method, not three repeated trials. The API and BS4 PCAPs were filtered after capture to the archive.org endpoint IPs identified in the scraper's `lsof` snapshots and TLS SNI. The original all-interface files included unrelated traffic and were removed to protect disk space. Run Selenium separately with `./run_mac_selenium_baseline.sh en0`; it resolves the resource hostnames observed in the saved Selenium smoke run and captures those endpoints. Each final pcap is therefore endpoint-scoped; it does not claim all background interface bytes.

The runner writes connection snapshots with `lsof` because `ss` is unavailable on macOS. This is a documented platform substitution and is not the exact requested Linux tool. The Selenium continuation refreshes `sudo` during the run and stops the actual `tcpdump` child process.

## Wireshark evidence and firewall

Open each pcap in Wireshark, inspect **Statistics → Conversations** and **Statistics → I/O Graphs**, and save readable screenshots with method/repetition labels. For latency, report TCP RTT from packet analysis separately from the scraper's request/navigation duration. The Selenium request-event count is browser telemetry, not a packet-derived request count.

UFW is Linux-only. Do not claim that macOS `pf` demonstrates UFW. A UFW block/allow demonstration requires the team to run it on Linux. If a macOS `pf` test is approved as supplementary evidence, preserve the initial ruleset, use a temporary isolated rule, verify recovery, and restore the initial ruleset.

For a scoped macOS substitute, run `bash ./run_mac_pf_demo.sh en0` from the repository root. It verifies HTTPS to one Internet Archive endpoint, loads a temporary outbound TCP/443 block in a uniquely named nested `com.apple` anchor, verifies the request fails, removes only that anchor's rules, verifies HTTPS recovers, and releases its PF enable token. It does not reload or flush the system ruleset. The script writes a log to `measurements/logs/`; save a Terminal screenshot showing the baseline, blocked, recovery, and cleanup messages. Report this as a macOS `pf` substitute, not as UFW evidence.

## Optional isolated UFW demo without a full Ubuntu VM

The Ubuntu/UFW Docker demo script was removed from the repository (the firewall demonstration was done on the Mac with `pf`; see `run_mac_pf_demo.sh`). It is in the Git history.
