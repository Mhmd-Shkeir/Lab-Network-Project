#!/bin/bash
# Isolated Linux UFW demonstration inside a disposable Docker network namespace.
# This does not modify macOS firewall rules.
set -Eeuo pipefail

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI is not installed." >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Start Docker Desktop, then rerun this script." >&2
  exit 1
fi

# The container and its firewall are discarded on exit. NET_ADMIN is scoped to
# this disposable container network namespace, not the macOS host firewall.
docker run --rm --cap-add=NET_ADMIN ubuntu:24.04 bash -lc '
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ufw curl ca-certificates
ufw --force reset
ufw default allow incoming
ufw default deny outgoing
ufw allow out 53/udp
ufw allow out 53/tcp
ufw allow out 443/tcp
ufw --force enable
printf "\n=== UFW enabled; HTTPS allowed ===\n"
ufw status verbose
curl --connect-timeout 5 --max-time 12 -fsSI https://archive.org >/dev/null
printf "HTTPS_ALLOWED=PASS\n"
ufw deny out 443/tcp
printf "\n=== Temporary outbound HTTPS block ===\n"
ufw status numbered
if curl --connect-timeout 5 --max-time 8 -fsSI https://archive.org >/dev/null 2>&1; then
  echo "HTTPS_BLOCK=FAIL (request unexpectedly succeeded)" >&2
  exit 2
fi
printf "HTTPS_BLOCK=PASS (request failed while deny rule was active)\n"
ufw --force delete deny out 443/tcp
printf "\n=== Rule removed; HTTPS recovery ===\n"
ufw status verbose
curl --connect-timeout 5 --max-time 12 -fsSI https://archive.org >/dev/null
printf "HTTPS_RECOVERY=PASS\n"
ufw disable
ufw --force reset
printf "FIREWALL_RESTORED=PASS (container destroyed on exit)\n"
'
