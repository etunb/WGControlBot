#!/bin/sh
set -e

WG_INTERFACE="${WG_INTERFACE:-wg0}"
WG_CONFIG_PATH="${WG_CONFIG_PATH:-/etc/wireguard/${WG_INTERFACE}.conf}"

cleanup() {
  wg-quick down "$WG_INTERFACE" >/dev/null 2>&1 || true
}

stop() {
  if [ -n "${pid:-}" ]; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  cleanup
  exit 143
}

trap stop INT TERM

if [ ! -f "$WG_CONFIG_PATH" ]; then
  echo "WireGuard config not found: $WG_CONFIG_PATH"
  exit 1
fi

wg-quick down "$WG_INTERFACE" >/dev/null 2>&1 || true
wg-quick up "$WG_CONFIG_PATH"

python -m src.main &
pid="$!"
status=0
wait "$pid" || status="$?"
cleanup
exit "$status"
