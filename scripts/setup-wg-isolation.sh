#!/bin/bash
# Firewall rules for WireGuard subnet isolation.
# - 10.0.113.0/24: common subnet, can communicate with all VPN subnets.
# - 10.0.i.0/24: isolated, only within same 10.0.i.0/24.
# Run as root, e.g. from WireGuard PostUp.

WG_INTERFACE="${WG_INTERFACE:-wg0}"
COMMON_SUBNET="10.0.113.0/24"
VPN_SUPERNET="10.0.0.0/16"

# Use iptables if nft not desired
iptables -C FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$COMMON_SUBNET" -d "$VPN_SUPERNET" -j ACCEPT 2>/dev/null || \
  iptables -A FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$COMMON_SUBNET" -d "$VPN_SUPERNET" -j ACCEPT

iptables -C FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -d "$COMMON_SUBNET" -s "$VPN_SUPERNET" -j ACCEPT 2>/dev/null || \
  iptables -A FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -d "$COMMON_SUBNET" -s "$VPN_SUPERNET" -j ACCEPT

# Isolated subnets: allow only same subnet (10.0.1, 10.0.2, ... 10.0.112, 10.0.114, ...)
for i in $(seq 1 112); do
  sub="10.0.$i.0/24"
  iptables -C FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT
done
for i in $(seq 114 255); do
  sub="10.0.$i.0/24"
  iptables -C FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -s "$sub" -d "$sub" -j ACCEPT
done

# Drop other forward between wg peers (optional, if default policy is ACCEPT)
# iptables -A FORWARD -i "$WG_INTERFACE" -o "$WG_INTERFACE" -j DROP

echo "WireGuard isolation rules applied for $WG_INTERFACE"
