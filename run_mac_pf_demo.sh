#!/bin/bash
# Temporary, scoped macOS PF demonstration for the lab network project.
# Uses a nested com.apple anchor and releases only this script's PF token.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
IFACE="${1:-en0}"
TARGET_IP="207.241.224.2"
RUN_TAG="$(date +%Y%m%d_%H%M%S)_$$"
ANCHOR="com.apple/000.labnet-demo-${RUN_TAG}"
RULE_FILE="$(mktemp)"
LOG_FILE="$ROOT/measurements/logs/mac_pf_demo_${RUN_TAG}.log"
PF_TOKEN=""
ANCHOR_LOADED=0
mkdir -p "$ROOT/measurements/logs"
exec > >(tee "$LOG_FILE") 2>&1

cleanup() {
  local exit_status=$?
  trap - EXIT
  if [[ "$ANCHOR_LOADED" == 1 ]]; then
    sudo pfctl -a "$ANCHOR" -F rules || true
  fi
  if [[ -n "$PF_TOKEN" ]]; then
    sudo pfctl -X "$PF_TOKEN" || true
  fi
  rm -f "$RULE_FILE"
  echo "Log: $LOG_FILE"
  exit "$exit_status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ ! "$IFACE" =~ ^[[:alnum:]_.-]+$ ]]; then
  echo "Invalid interface name: $IFACE" >&2
  exit 2
fi

sudo -v

check_https() {
  curl --silent --show-error --connect-timeout 5 --max-time 12 \
    --resolve "archive.org:443:${TARGET_IP}" \
    -o /dev/null -w 'HTTP status: %{http_code}; remote: %{remote_ip}\n' \
    https://archive.org/
}

echo "Interface: $IFACE"
echo "Target: archive.org ($TARGET_IP), TCP/443"
echo "Baseline check (HTTPS should succeed):"
check_https

ENABLE_OUTPUT="$(sudo pfctl -E 2>&1)" || {
  printf '%s\n' "$ENABLE_OUTPUT"
  echo "Could not acquire a PF enable reference." >&2
  exit 1
}
printf '%s\n' "$ENABLE_OUTPUT"
PF_TOKEN="$(printf '%s\n' "$ENABLE_OUTPUT" | sed -nE 's/.*[Tt]oken[[:space:]]*:[[:space:]]*([0-9]+).*/\1/p' | tail -1)"
if [[ -z "$PF_TOKEN" ]]; then
  echo "Could not read PF's enable token; no rules were loaded." >&2
  exit 1
fi

printf 'block drop out quick on %s inet proto tcp from any to %s port 443\n' \
  "$IFACE" "$TARGET_IP" > "$RULE_FILE"
sudo pfctl -a "$ANCHOR" -f "$RULE_FILE"
ANCHOR_LOADED=1
echo "Temporary PF rule loaded in $ANCHOR:"
sudo pfctl -a "$ANCHOR" -sr

echo "Block check (HTTPS should fail):"
if check_https; then
  echo "HTTPS_BLOCK=FAIL (request unexpectedly succeeded)" >&2
  exit 2
else
  echo "HTTPS_BLOCK=PASS (target TCP/443 was blocked)"
fi

sudo pfctl -a "$ANCHOR" -F rules
ANCHOR_LOADED=0
echo "Temporary anchor rule removed."
echo "Recovery check (HTTPS should succeed):"
check_https
echo "HTTPS_RECOVERY=PASS"
echo "PF demo complete; cleanup releases this script's PF enable token."
