#!/bin/bash
# Firewall rules for WireGuard subnet isolation.
# Usage:
#   WG_INTERFACE=wg0 scripts/setup-wg-isolation.sh up
#   WG_INTERFACE=wg0 scripts/setup-wg-isolation.sh down

set -e

ACTION="${1:-up}"
WG_INTERFACE="${WG_INTERFACE:-wg0}"
COMMON_SUBNET="10.0.113.0/24"
VPN_SUPERNET="10.0.0.0/16"

rule() {
  action="$1"
  shift
  if [ "$action" = "up" ]; then
    iptables -C "$@" 2>/dev/null || iptables -A "$@"
  else
    while iptables -C "$@" 2>/dev/null; do
      iptables -D "$@" || true
    done
  fi
}

case "$ACTION" in
  up|down) ;;
  *)
    echo "Usage: $0 [up|down]"
    exit 1
    ;;
esac

rule "$ACTION" FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$COMMON_SUBNET" -d "$VPN_SUPERNET" -j ACCEPT
rule "$ACTION" FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -d "$COMMON_SUBNET" -s "$VPN_SUPERNET" -j ACCEPT

for i in $(seq 1 112); do
  sub="10.0.$i.0/24"
  rule "$ACTION" FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT
done

for i in $(seq 114 255); do
  sub="10.0.$i.0/24"
  rule "$ACTION" FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT
done

rule "$ACTION" FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$VPN_SUPERNET" -d "$VPN_SUPERNET" -j DROP

echo "WireGuard isolation rules $ACTION for $WG_INTERFACE"
