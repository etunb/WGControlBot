#!/bin/bash
# Interactive Docker-only installer for WGControlBot.
#
# Recommended:
#   curl -fsSL https://raw.githubusercontent.com/etunb/WGControlBot/master/scripts/install.sh | sudo bash
#
# Optional environment variables:
#   WIREGUARD_BOT_REPO - Git repository URL
#   WIREGUARD_BOT_DIR  - Installation directory (default: /opt/wgcontrolbot)
#   WG_INTERFACE       - WireGuard interface name inside Docker (default: wg0)
#   WG_MAIN_IFACE      - External network interface for Docker NAT (default: auto-detected)
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

apt_update() {
  apt-get \
    -o Acquire::AllowReleaseInfoChange=true \
    -o Acquire::AllowReleaseInfoChange::Label=true \
    update --allow-releaseinfo-change
}

apt_install() {
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
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
    echo "Automatic installation currently supports Debian/Ubuntu only."
    echo "Install manually: git docker docker-compose iproute2"
    exit 1
  fi

  apt_update
  apt_install git iproute2 ca-certificates curl

  if ! command -v docker >/dev/null 2>&1; then
    apt_install docker.io
  fi

  if ! docker compose version >/dev/null 2>&1; then
    apt_install docker-compose-plugin || apt_install docker-compose
  fi

  systemctl enable docker 2>/dev/null || true
  systemctl start docker 2>/dev/null || true
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
  WG_DIR="$PROJECT_DIR/wireguard"
  WG_CONFIG="$WG_DIR/${WG_IF}.conf"
  CONTAINER_WG_CONFIG="/etc/wireguard/${WG_IF}.conf"
  WG_PORT="${WG_PORT:-$(ask "WireGuard UDP port" "$(shuf -i 51820-51850 -n 1 2>/dev/null || echo 51820)")}"
  MAIN_IFACE="$(ask "External interface for NAT" "$(detect_main_iface)")"

  mkdir -p "$WG_DIR"
  chmod 700 "$WG_DIR"

  cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
WG_SERVER_ENDPOINT=$ENDPOINT
WG_INTERFACE=$WG_IF
WG_CONFIG_PATH=$CONTAINER_WG_CONFIG
CONFIG_PATH=/app/config.yaml
DATABASE_PATH=/data/bot.db
EOF

  touch "$PROJECT_DIR/config.yaml"
  COMPOSE_CMD="$(compose_cmd)"
  (cd "$PROJECT_DIR" && $COMPOSE_CMD build bot)
  (cd "$PROJECT_DIR" && $COMPOSE_CMD run --rm --no-deps --entrypoint sh bot -c \
    'umask 077; mkdir -p /etc/wireguard; if [ ! -f /etc/wireguard/server_private.key ]; then wg genkey | tee /etc/wireguard/server_private.key | wg pubkey > /etc/wireguard/server_public.key; elif [ ! -f /etc/wireguard/server_public.key ]; then wg pubkey < /etc/wireguard/server_private.key > /etc/wireguard/server_public.key; fi')

  SERVER_PRIVATE="$(cat "$WG_DIR/server_private.key")"
  SERVER_PUBLIC="$(cat "$WG_DIR/server_public.key")"

  chmod +x "$PROJECT_DIR/scripts/setup-wg-isolation.sh"

  if [ ! -f "$WG_CONFIG" ]; then
    cat > "$WG_CONFIG" << EOF
[Interface]
PrivateKey = $SERVER_PRIVATE
ListenPort = $WG_PORT
Address = 10.0.113.1/24
PostUp = WG_INTERFACE=$WG_IF /app/scripts/setup-wg-isolation.sh up; iptables -t nat -A POSTROUTING -o $MAIN_IFACE -j MASQUERADE
PostDown = WG_INTERFACE=$WG_IF /app/scripts/setup-wg-isolation.sh down; iptables -t nat -D POSTROUTING -o $MAIN_IFACE -j MASQUERADE
EOF
    echo "Created WireGuard config: $WG_CONFIG"
  else
    echo "WireGuard config already exists: $WG_CONFIG"
    if grep -q "^ListenPort" "$WG_CONFIG"; then
      WG_PORT="$(awk -F= '/^ListenPort/ {gsub(/[ \t]/, "", $2); print $2; exit}' "$WG_CONFIG")"
    fi
  fi

  sysctl -w net.ipv4.ip_forward=1 >/dev/null || true
}

write_app_config() {
  mkdir -p "$PROJECT_DIR/data"
  ADMIN_IDS_YAML="[$(echo "$ADMIN_IDS" | sed 's/,/, /g')]"

  cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
WG_SERVER_ENDPOINT=$ENDPOINT
WG_INTERFACE=$WG_IF
WG_CONFIG_PATH=$CONTAINER_WG_CONFIG
CONFIG_PATH=/app/config.yaml
DATABASE_PATH=/data/bot.db
EOF

  cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: $ADMIN_IDS_YAML
wireguard:
  interface: $WG_IF
  config_path: $CONTAINER_WG_CONFIG
  port: $WG_PORT
  common_subnet: "10.0.113.0/24"
  isolated_subnet_prefix: "10.0"
  isolated_subnet_mask: 24
database:
  path: /data/bot.db
server:
  public_key: "$SERVER_PUBLIC"
  endpoint: "$ENDPOINT"
  port: $WG_PORT
EOF
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo "Docker Compose is not installed." >&2
    exit 1
  fi
}

start_bot() {
  COMPOSE_CMD="$(compose_cmd)"
  (cd "$PROJECT_DIR" && $COMPOSE_CMD up -d --build)
}

require_root

echo "WGControlBot Docker installer"
echo ""
install_host_packages
prepare_project

echo ""
echo "Answer the setup questions."
BOT_TOKEN="$(ask "Telegram bot token from @BotFather" "")"
ADMIN_IDS="$(ask "Telegram admin ID(s), comma-separated" "")"
ENDPOINT="$(ask "Server public IP or domain for client configs" "")"

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_IDS" ] || [ -z "$ENDPOINT" ]; then
  echo "Bot token, admin IDs, and endpoint are required."
  exit 1
fi

create_wireguard_config
write_app_config
start_bot

echo ""
echo "Docker installation completed."
echo "Project directory: $PROJECT_DIR"
echo "WireGuard interface: $WG_IF"
echo "WireGuard UDP port: $WG_PORT"
echo "Status: cd $PROJECT_DIR && $(compose_cmd) ps"
echo "Logs:   cd $PROJECT_DIR && $(compose_cmd) logs -f"
echo "Open UDP port $WG_PORT on your firewall/router, then send /start to the bot in Telegram."
