#!/bin/bash
# Example deploy script: install WG, generate keys, set random port, run isolation rules, run bot.
set -e

WG_INTERFACE="${WG_INTERFACE:-wg0}"
WG_DIR="${WG_DIR:-/etc/wireguard}"
CONFIG="$WG_DIR/${WG_INTERFACE}.conf"
PORT="${WG_PORT:-$(shuf -i 51820-51850 -n 1)}"

echo "WireGuard interface: $WG_INTERFACE, port: $PORT"

# Install WireGuard if needed
if ! command -v wg &>/dev/null; then
  echo "Install WireGuard (e.g. apt install wireguard-tools)"
  exit 1
fi

# Generate server keys if no config
if [ ! -f "$CONFIG" ]; then
  mkdir -p "$WG_DIR"
  umask 077
  wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
  SERVER_PRIVATE=$(cat "$WG_DIR/server_private.key")
  SERVER_PUBLIC=$(cat "$WG_DIR/server_public.key")
  cat > "$CONFIG" << EOF
[Interface]
PrivateKey = $SERVER_PRIVATE
ListenPort = $PORT
Address = 10.0.113.1/24
PostUp = iptables -A FORWARD -i $WG_INTERFACE -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i $WG_INTERFACE -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
EOF
  echo "Created $CONFIG with ListenPort=$PORT"
  echo "Server public key: $SERVER_PUBLIC"
fi

# Apply isolation (optional; adjust interface name)
if [ -f "scripts/setup-wg-isolation.sh" ]; then
  chmod +x scripts/setup-wg-isolation.sh
  sudo WG_INTERFACE="$WG_INTERFACE" ./scripts/setup-wg-isolation.sh || true
fi

# Bring up WG
wg-quick up "$WG_INTERFACE" 2>/dev/null || true

# Export for config.yaml
echo "Use in config.yaml server section:"
echo "  public_key: $(cat "$WG_DIR/server_public.key" 2>/dev/null || echo '')"
echo "  endpoint: YOUR_SERVER_IP_OR_DOMAIN"
echo "  port: $PORT"
