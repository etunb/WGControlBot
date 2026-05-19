#!/bin/bash
# Interactive one-command installer for WGControlBot.
#
# Recommended:
#   curl -fsSL https://raw.githubusercontent.com/etunb/WGControlBot/master/scripts/install.sh | sudo bash
#
# Optional environment variables:
#   WIREGUARD_BOT_REPO - Git repository URL
#   WIREGUARD_BOT_DIR  - Installation directory (default: /opt/wgcontrolbot)
#   WG_INTERFACE       - WireGuard interface name (default: wg0)
#   WG_MAIN_IFACE      - External network interface for NAT (default: auto-detected)
#   WG_PORT            - WireGuard UDP port (default: random 51820-51850)

set -e

DEFAULT_REPO="https://github.com/etunb/WGControlBot.git"
DEFAULT_DIR="/opt/wgcontrolbot"

ask() {
  prompt="$1"
  default="$2"
  if [ -r /dev/tty ]; then
    input="/dev/tty"
    output="/dev/tty"
  else
    input="/dev/stdin"
    output="/dev/stderr"
  fi
  if [ -n "$default" ]; then
    printf "%s [%s]: " "$prompt" "$default" > "$output"
  else
    printf "%s: " "$prompt" > "$output"
  fi
  read -r value < "$input"
  if [ -z "$value" ]; then
    value="$default"
  fi
  printf "%s" "$value"
}

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root, for example:"
    echo "  curl -fsSL https://raw.githubusercontent.com/etunb/WGControlBot/master/scripts/install.sh | sudo bash"
    exit 1
  fi
}

detect_main_iface() {
  if [ -n "${WG_MAIN_IFACE:-}" ]; then
    echo "$WG_MAIN_IFACE"
    return
  fi
  if command -v ip >/dev/null 2>&1; then
    iface="$(ip route | awk '/default/ {print $5; exit}')"
    if [ -n "$iface" ]; then
      echo "$iface"
      return
    fi
  fi
  echo "eth0"
}

install_host_packages() {
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "Automatic package installation currently supports Debian/Ubuntu only."
    echo "Install manually: git wireguard-tools iptables python3 python3-venv python3-pip"
    exit 1
  fi
  apt-get update
  apt-get install -y --no-install-recommends \
    git wireguard-tools iptables iproute2 python3 python3-venv python3-pip ca-certificates curl
}

prepare_project() {
  if [ -f "src/main.py" ] && [ -f "requirements.txt" ]; then
    PROJECT_DIR="$(pwd)"
    echo "Using current project directory: $PROJECT_DIR"
    return
  fi

  REPO="${WIREGUARD_BOT_REPO:-$DEFAULT_REPO}"
  PROJECT_DIR="${WIREGUARD_BOT_DIR:-$(ask "Installation directory" "$DEFAULT_DIR")}"

  mkdir -p "$(dirname "$PROJECT_DIR")"
  if [ -d "$PROJECT_DIR/.git" ]; then
    echo "Updating $PROJECT_DIR"
    git -C "$PROJECT_DIR" pull --ff-only || true
  else
    echo "Cloning $REPO to $PROJECT_DIR"
    git clone "$REPO" "$PROJECT_DIR"
  fi
  cd "$PROJECT_DIR"
}

create_wireguard_config() {
  WG_IF="${WG_INTERFACE:-$(ask "WireGuard interface" "wg0")}"
  WG_DIR="/etc/wireguard"
  WG_CONFIG="$WG_DIR/${WG_IF}.conf"
  WG_PORT="${WG_PORT:-$(ask "WireGuard UDP port" "$(shuf -i 51820-51850 -n 1 2>/dev/null || echo 51820)")}"
  MAIN_IFACE="$(ask "External interface for NAT" "$(detect_main_iface)")"

  mkdir -p "$WG_DIR"
  chmod 700 "$WG_DIR"

  if [ ! -f "$WG_DIR/server_private.key" ]; then
    umask 077
    wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
  elif [ ! -f "$WG_DIR/server_public.key" ]; then
    wg pubkey < "$WG_DIR/server_private.key" > "$WG_DIR/server_public.key"
  fi

  SERVER_PRIVATE="$(cat "$WG_DIR/server_private.key")"
  SERVER_PUBLIC="$(cat "$WG_DIR/server_public.key")"

  chmod +x "$PROJECT_DIR/scripts/setup-wg-isolation.sh"

  if [ ! -f "$WG_CONFIG" ]; then
    cat > "$WG_CONFIG" << EOF
[Interface]
PrivateKey = $SERVER_PRIVATE
ListenPort = $WG_PORT
Address = 10.0.113.1/24
PostUp = WG_INTERFACE=$WG_IF $PROJECT_DIR/scripts/setup-wg-isolation.sh up; iptables -t nat -A POSTROUTING -o $MAIN_IFACE -j MASQUERADE
PostDown = WG_INTERFACE=$WG_IF $PROJECT_DIR/scripts/setup-wg-isolation.sh down; iptables -t nat -D POSTROUTING -o $MAIN_IFACE -j MASQUERADE
EOF
    echo "Created WireGuard config: $WG_CONFIG"
  else
    echo "WireGuard config already exists: $WG_CONFIG"
    if grep -q "^ListenPort" "$WG_CONFIG"; then
      WG_PORT="$(awk -F= '/^ListenPort/ {gsub(/[ \t]/, "", $2); print $2; exit}' "$WG_CONFIG")"
    fi
  fi

  sysctl -w net.ipv4.ip_forward=1 >/dev/null
  if [ -d /etc/sysctl.d ]; then
    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-wgcontrolbot.conf
  fi

  WG_INTERFACE="$WG_IF" "$PROJECT_DIR/scripts/setup-wg-isolation.sh" up || true
  wg-quick down "$WG_IF" 2>/dev/null || true
  wg-quick up "$WG_IF"
}

write_app_config() {
  mkdir -p "$PROJECT_DIR/data"
  ADMIN_IDS_YAML="[$(echo "$ADMIN_IDS" | sed 's/,/, /g')]"

  if [ "$INSTALL_MODE" = "docker" ]; then
    DB_PATH="/data/bot.db"
    CONFIG_PATH="/app/config.yaml"
  else
    DB_PATH="$PROJECT_DIR/data/bot.db"
    CONFIG_PATH="$PROJECT_DIR/config.yaml"
  fi

  cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
WG_SERVER_ENDPOINT=$ENDPOINT
CONFIG_PATH=$CONFIG_PATH
DATABASE_PATH=$DB_PATH
EOF

  cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: $ADMIN_IDS_YAML
wireguard:
  interface: $WG_IF
  config_path: $WG_CONFIG
  port: $WG_PORT
  common_subnet: "10.0.113.0/24"
  isolated_subnet_prefix: "10.0"
  isolated_subnet_mask: 24
database:
  path: $DB_PATH
server:
  public_key: "$SERVER_PUBLIC"
  endpoint: "$ENDPOINT"
  port: $WG_PORT
EOF
}

install_native_service() {
  python3 -m venv "$PROJECT_DIR/.venv"
  "$PROJECT_DIR/.venv/bin/pip" install --upgrade pip
  "$PROJECT_DIR/.venv/bin/pip" install -r "$PROJECT_DIR/requirements.txt"

  cat > /etc/systemd/system/wgcontrolbot.service << EOF
[Unit]
Description=WGControlBot Telegram Bot
After=network-online.target wg-quick@${WG_IF}.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/python -m src.main
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "wg-quick@${WG_IF}"
  systemctl restart "wg-quick@${WG_IF}"
  systemctl enable wgcontrolbot
  systemctl restart wgcontrolbot
}

install_docker_service() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is not installed. Install Docker first or choose native installation."
    exit 1
  fi

  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  else
    echo "Docker Compose is not installed."
    exit 1
  fi

  systemctl enable "wg-quick@${WG_IF}" 2>/dev/null || true
  systemctl restart "wg-quick@${WG_IF}" 2>/dev/null || true
  (cd "$PROJECT_DIR" && $COMPOSE_CMD up -d --build)
}

require_root

echo "WGControlBot installer"
echo ""
install_host_packages
prepare_project

echo ""
echo "Answer the setup questions."
BOT_TOKEN="$(ask "Telegram bot token from @BotFather" "")"
ADMIN_IDS="$(ask "Telegram admin ID(s), comma-separated" "")"
ENDPOINT="$(ask "Server public IP or domain for client configs" "")"
MODE_CHOICE="$(ask "Install mode: native or docker" "native")"

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_IDS" ] || [ -z "$ENDPOINT" ]; then
  echo "Bot token, admin IDs, and endpoint are required."
  exit 1
fi

case "$MODE_CHOICE" in
  docker|Docker|2) INSTALL_MODE="docker" ;;
  *) INSTALL_MODE="native" ;;
esac

create_wireguard_config
write_app_config

if [ "$INSTALL_MODE" = "docker" ]; then
  install_docker_service
  echo ""
  echo "Docker installation completed."
  echo "Status: cd $PROJECT_DIR && docker compose ps"
  echo "Logs:   cd $PROJECT_DIR && docker compose logs -f"
else
  install_native_service
  echo ""
  echo "Native installation completed."
  echo "Status: systemctl status wgcontrolbot"
  echo "Logs:   journalctl -u wgcontrolbot -f"
fi

echo ""
echo "WireGuard interface: $WG_IF"
echo "WireGuard UDP port: $WG_PORT"
echo "Open UDP port $WG_PORT on your firewall/router, then send /start to the bot in Telegram."
