#!/bin/bash
# Finish the single Selenium baseline run after the API and BS4 runs.
# Run from the repository root in Terminal; sudo prompts locally once.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
IFACE="${1:-en0}"
CAPTURE_DIR="$ROOT/measurements/captures"
LOG_DIR="$ROOT/measurements/logs"
RUN_DIR="$ROOT/measurements/runs"
mkdir -p "$CAPTURE_DIR" "$LOG_DIR" "$RUN_DIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv; see docs/MAC_NETWORK_CAPTURE.md" >&2
  exit 1
fi

PCAP="$CAPTURE_DIR/selenium_r1.pcap"
RUNLOG="$LOG_DIR/selenium_r1.log"
SOCKLOG="$LOG_DIR/selenium_r1_lsof.log"
TCPDUMPLOG="$LOG_DIR/selenium_r1_tcpdump.log"
CONTROL_FIFO="$LOG_DIR/selenium_r1.stop.fifo"
CAPTURE_SUPERVISOR_PID=""

sudo -v

stop_capture() {
  if [[ -n "$CAPTURE_SUPERVISOR_PID" ]]; then
    if kill -0 "$CAPTURE_SUPERVISOR_PID" 2>/dev/null; then
      printf 'stop\n' > "$CONTROL_FIFO" || true
    fi
    wait "$CAPTURE_SUPERVISOR_PID" >/dev/null 2>&1 || true
  fi
  CAPTURE_SUPERVISOR_PID=""
}
cleanup() {
  stop_capture
  rm -f "$CONTROL_FIFO"
}
trap cleanup EXIT INT TERM

if compgen -G "$RUN_DIR/selenium_*_mac_baseline_r1" >/dev/null; then
  echo "A Selenium run folder with this label already exists; refusing to overwrite it." >&2
  exit 1
fi

echo "Interface: $IFACE"
CAPTURE_FILTER="$("$PYTHON" - <<'PY'
import csv, json, socket
from pathlib import Path

hosts = {"be-api.us.archive.org"}
smoke = Path("measurements/runs/selenium_20261121_211315_mac_smoke/page_metrics.csv")
if smoke.exists():
    with smoke.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                hosts.update(json.loads(row.get("hosts") or "{}"))
            except json.JSONDecodeError:
                pass
ips = set()
for host in sorted(hosts):
    try:
        ips.update(info[4][0] for info in socket.getaddrinfo(host, None, family=socket.AF_INET))
    except OSError:
        pass
print(" or ".join(f"host {ip}" for ip in sorted(ips)))
PY
)"
if [[ -z "$CAPTURE_FILTER" ]]; then
  echo "Could not resolve archive.org hosts from the saved Selenium smoke run." >&2
  exit 1
fi
echo "Capturing hosts observed in the Selenium smoke run: $CAPTURE_FILTER"
echo "Starting Selenium: fixed 200 IDs, headless Chrome, default three-second pacing."

rm -f "$CONTROL_FIFO"
mkfifo "$CONTROL_FIFO"
: > "$TCPDUMPLOG"
sudo -n /bin/bash "$ROOT/scripts/mac_tcpdump_supervisor.sh" "$IFACE" "$PCAP" "$CONTROL_FIFO" "$TCPDUMPLOG" "$CAPTURE_FILTER" &
CAPTURE_SUPERVISOR_PID=$!
for _ in $(seq 1 40); do
  if grep -q 'listening on' "$TCPDUMPLOG"; then
    break
  fi
  sleep 0.1
done
if ! grep -q 'listening on' "$TCPDUMPLOG"; then
  echo "Could not find tcpdump's child process." >&2
  exit 1
fi

sleep 2
"$PYTHON" scrapers/ia_selenium_scraper.py --headless --out-root "$RUN_DIR" --label mac_baseline_r1 >"$RUNLOG" 2>&1 &
SCRAPER_PID=$!
set +e
while :; do
  SCRAPER_STATE="$(ps -p "$SCRAPER_PID" -o stat= 2>/dev/null || true)"
  [[ -n "$SCRAPER_STATE" && "$SCRAPER_STATE" != Z* ]] || break
  date -u '+%Y-%m-%dT%H:%M:%SZ' >> "$SOCKLOG"
  lsof -nP -iTCP -iUDP >> "$SOCKLOG" 2>&1 || true
  sleep 1
done
wait "$SCRAPER_PID"
STATUS=$?
set -e
stop_capture
cat "$RUNLOG"
if [[ $STATUS -ne 0 ]]; then
  echo "Selenium baseline failed (exit $STATUS); see $RUNLOG" >&2
  exit "$STATUS"
fi
if [[ ! -s "$PCAP" ]]; then
  echo "Capture file is empty: $PCAP" >&2
  exit 1
fi
echo "Selenium baseline finished; capture: $PCAP"
