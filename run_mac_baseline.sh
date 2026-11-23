#!/bin/bash
# Run the 9 fixed 200-book baseline collections on macOS, each with its own pcap.
# Start this from the repository root in Terminal; sudo will prompt locally once.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PYTHON="$ROOT/.venv/bin/python"
IFACE="${1:-$(route -n get default | awk '/interface:/{print $2; exit}')}"
REPETITIONS="${2:-3}"
CAPTURE_DIR="$ROOT/measurements/captures"
LOG_DIR="$ROOT/measurements/logs"
RUN_DIR="$ROOT/measurements/runs"
mkdir -p "$CAPTURE_DIR" "$LOG_DIR" "$RUN_DIR"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing .venv. Create it with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-analysis.txt" >&2
  exit 1
fi
if [[ -z "$IFACE" ]]; then
  echo "Could not detect the default network interface. Pass it as the first argument." >&2
  exit 1
fi
if [[ "$REPETITIONS" -lt 1 || "$REPETITIONS" -gt 3 ]]; then
  echo "Repetitions must be 1, 2, or 3." >&2
  exit 1
fi

echo "Interface: $IFACE"
echo "Runs: $((REPETITIONS * 3)) x fixed 200 IDs. Order rotates across repetitions."
echo "Packet captures include all interface traffic matching DNS/HTTP/HTTPS. Pause unrelated downloads/sync."
CAPTURE_SUPERVISOR_PID=""
CONTROL_FIFO=""
cleanup() {
  if [[ -n "$CAPTURE_SUPERVISOR_PID" ]]; then
    if kill -0 "$CAPTURE_SUPERVISOR_PID" 2>/dev/null; then
      printf 'stop\n' > "$CONTROL_FIFO" || true
    fi
    wait "$CAPTURE_SUPERVISOR_PID" >/dev/null 2>&1 || true
  fi
  [[ -z "$CONTROL_FIFO" ]] || rm -f "$CONTROL_FIFO"
}
trap cleanup EXIT INT TERM

run_one() {
  local method="$1" rep="$2" script="$3" capture="$4"
  local pcap="$CAPTURE_DIR/${method}_r${rep}.pcap"
  local runlog="$LOG_DIR/${method}_r${rep}.log"
  local socklog="$LOG_DIR/${method}_r${rep}_lsof.log"
  local dumplog="$LOG_DIR/${method}_r${rep}_tcpdump.log"
  local fifo="$LOG_DIR/${method}_r${rep}.stop.fifo"
  local label="mac_baseline_r${rep}"
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Starting $method repetition $rep"
  sudo -v
  rm -f "$fifo"
  mkfifo "$fifo"
  : > "$dumplog"
  CONTROL_FIFO="$fifo"
  sudo -n /bin/bash "$ROOT/scripts/mac_tcpdump_supervisor.sh" "$IFACE" "$pcap" "$fifo" "$dumplog" 'port 80 or port 443 or port 53' &
  CAPTURE_SUPERVISOR_PID=$!
  for _ in $(seq 1 40); do
    if grep -q 'listening on' "$dumplog"; then break; fi
    if ! kill -0 "$CAPTURE_SUPERVISOR_PID" 2>/dev/null; then
      cat "$dumplog" >&2
      echo "tcpdump did not start; check the interface and local sudo access." >&2
      exit 1
    fi
    sleep 0.1
  done
  if ! grep -q 'listening on' "$dumplog"; then
    cat "$dumplog" >&2
    echo "tcpdump did not start; check the interface and local sudo access." >&2
    exit 1
  fi
  set +e
  if [[ "$method" == "selenium" ]]; then
    "$PYTHON" "scrapers/$script" --headless --out-root "$RUN_DIR" --label "$label" >"$runlog" 2>&1 &
  else
    "$PYTHON" "scrapers/$script" --out-root "$RUN_DIR" --label "$label" >"$runlog" 2>&1 &
  fi
  local scraper_pid=$!
  # On macOS kill -0 also succeeds for a zombie child. Stop polling once ps
  # shows that the scraper has exited, then reap it with wait below.
  while :; do
    local scraper_state
    scraper_state="$(ps -p "$scraper_pid" -o stat= 2>/dev/null || true)"
    [[ -n "$scraper_state" && "$scraper_state" != Z* ]] || break
    date -u '+%Y-%m-%dT%H:%M:%SZ' >> "$socklog"
    lsof -nP -iTCP -iUDP >> "$socklog" 2>&1 || true
    sleep 1
  done
  wait "$scraper_pid"
  local status=$?
  set -e
  printf 'stop\n' > "$CONTROL_FIFO" || true
  wait "$CAPTURE_SUPERVISOR_PID" >/dev/null 2>&1 || true
  CAPTURE_SUPERVISOR_PID=""
  rm -f "$CONTROL_FIFO"
  CONTROL_FIFO=""
  cat "$runlog"
  if [[ $status -ne 0 ]]; then
    echo "$method repetition $rep failed (exit $status); see $runlog" >&2
    exit "$status"
  fi
  if [[ ! -s "$pcap" ]]; then
    echo "Capture file is empty: $pcap" >&2
    exit 1
  fi
  echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Finished $method repetition $rep; capture: $pcap"
}

# Rotated order: API / BS4 / Selenium, then Selenium / API / BS4, then BS4 / Selenium / API.
for rep in $(seq 1 "$REPETITIONS"); do
  case "$rep" in
    1) order="api bs4 selenium" ;;
    2) order="selenium api bs4" ;;
    3) order="bs4 selenium api" ;;
  esac
  for method in $order; do
    case "$method" in
      api) script="ia_api_scraper.py" ;;
      bs4) script="ia_bs4_scraper.py" ;;
      selenium) script="ia_selenium_scraper.py" ;;
    esac
    run_one "$method" "$rep" "$script" fixed_200
  done
done

echo "All baseline runs finished. Do not commit pcap files; measurements/ is ignored."
echo "Save iftop/nload/Wireshark screenshots under screenshots/ before preparing the report."
