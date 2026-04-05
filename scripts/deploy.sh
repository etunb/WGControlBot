#!/bin/bash
# Deploy WireGuard for the bot: generate keys, set random port, apply isolation rules.
set -e

WG_INTERFACE="${WG_INTERFACE:-wg0}"
WG_DIR="${WG_DIR:-/etc/wireguard}"
CONFIG="$WG_DIR/${WG_INTERFACE}.conf"
PORT="${WG_PORT:-$(shuf -i 51820-51850 -n 1)}"

echo "WireGuard interface: $WG_INTERFACE, port: $PORT"

# Check WireGuard installation
if ! command -v wg &>/dev/null; then
  echo "WireGuard is not installed. Please install wireguard-tools:"
  echo "  apt-get install -y wireguard-tools  # Debian/Ubuntu"
  exit 1
fi

# Generate server keys if config doesn't exist
if [ ! -f "$CONFIG" ]; then
  mkdir -p "$WG_DIR"
  umask 077
  wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
  SERVER_PRIVATE=$(cat "$WG_DIR/server_private.key")
  SERVER_PUBLIC=$(cat "$WG_DIR/server_public.key")

  # Determine external interface for NAT (outgoing internet)
  MAIN_IFACE="${WG_MAIN_IFACE:-}"
  if [ -z "$MAIN_IFACE" ] && command -v ip >/dev/null 2>&1; then
    MAIN_IFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
  fi
  if [ -z "$MAIN_IFACE" ]; then
    MAIN_IFACE="eth0"
    echo "Warning: Could not auto-detect external interface. Defaulting to eth0."
    echo "         Set WG_MAIN_IFACE if your interface is different."
  fi

  cat > "$CONFIG" << EOF
[Interface]
PrivateKey = $SERVER_PRIVATE
ListenPort = $PORT
Address = 10.0.113.1/24
PostUp = iptables -A FORWARD -i $WG_INTERFACE -j ACCEPT; iptables -t nat -A POSTROUTING -o $MAIN_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i $WG_INTERFACE -j ACCEPT; iptables -t nat -D POSTROUTING -o $MAIN_IFACE -j MASQUERADE
EOF
  echo "Created $CONFIG with ListenPort=$PORT (external interface: $MAIN_IFACE)"
  echo "Server public key: $SERVER_PUBLIC"
else
  echo "WireGuard config already exists: $CONFIG"
  SERVER_PUBLIC=$(cat "$WG_DIR/server_public.key" 2>/dev/null || echo '')
fi

# Apply isolation rules (optional)
if [ -f "scripts/setup-wg-isolation.sh" ]; then
  chmod +x scripts/setup-wg-isolation.sh
  WG_INTERFACE="$WG_INTERFACE" ./scripts/setup-wg-isolation.sh || true
fi

# Bring up the interface (ignore if already up)
wg-quick up "$WG_INTERFACE" 2>/dev/null || true

# Output instructions for config.yaml
echo ""
echo "Add the following to your config.yaml under the 'server' section:"
echo "  public_key: \"$SERVER_PUBLIC\""
echo "  endpoint: \"YOUR_SERVER_IP_OR_DOMAIN\""
echo "  port: $PORT"
echo ""
echo "If needed, set WG_INTERFACE, WG_DIR, WG_PORT, or WG_MAIN_IFACE environment variables."
