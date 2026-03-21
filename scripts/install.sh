#!/bin/sh
# One-line install: sh -c "$(curl -fsSL https://YOUR_HOST/install.sh)"
# Or: curl -fsSL https://YOUR_HOST/install.sh | sh
#
# Set before run (optional):
#   WIREGUARD_BOT_REPO=https://github.com/youruser/wireguard-bot.git
#   WIREGUARD_BOT_DIR=/opt/wireguard-bot

set -e

# If we're in a project dir (has src/main.py), use it; else clone
PROJECT_DIR="${WIREGUARD_BOT_DIR:-/opt/wireguard-bot}"
if [ -f "src/main.py" ] && [ -f "requirements.txt" ]; then
  PROJECT_DIR="$(pwd)"
  echo "Using project directory: $PROJECT_DIR"
else
  REPO="${WIREGUARD_BOT_REPO:-}"
  if [ -z "$REPO" ]; then
    echo "WireGuard + Telegram Bot — install"
    echo "Run from project directory, or set WIREGUARD_BOT_REPO to git URL."
    printf "Git URL (e.g. https://github.com/user/wireguard-bot.git): "
    read -r REPO
    if [ -z "$REPO" ]; then
      echo "No URL. Run: git clone <repo> $PROJECT_DIR && cd $PROJECT_DIR && sh scripts/install.sh"
      exit 1
    fi
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "Install git first."
    exit 1
  fi
  mkdir -p "$(dirname "$PROJECT_DIR")"
  if [ -d "$PROJECT_DIR/.git" ]; then
    echo "Directory $PROJECT_DIR exists, updating..."
    (cd "$PROJECT_DIR" && git pull || true)
  else
    git clone "$REPO" "$PROJECT_DIR"
  fi
  cd "$PROJECT_DIR"
fi

# Docker or native?
echo ""
echo "How to install?"
echo "  1) Docker (recommended)"
echo "  2) Native (systemd, WireGuard + Python on host)"
printf "Choice [1]: "
read -r choice
choice="${choice:-1}"

# Common prompts
echo ""
printf "Telegram bot token: "
read -r BOT_TOKEN
printf "Telegram admin ID(s), comma-separated: "
read -r ADMIN_IDS
printf "Server endpoint (host or IP for client configs): "
read -r ENDPOINT

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_IDS" ]; then
  echo "Token and admin IDs are required."
  exit 1
fi

# WireGuard port
WG_PORT="${WG_PORT:-$(shuf -i 51820-51850 -n 1 2>/dev/null || echo 51820)}"
echo "WireGuard port: $WG_PORT"

case "$choice" in
  2)
    # --- Native ---
    if [ "$(id -u)" -ne 0 ]; then
      echo "Run as root for native install (or use Docker)."
      exit 1
    fi
    # Install deps (Debian/Ubuntu)
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update
      apt-get install -y wireguard-tools python3 python3-venv python3-pip iptables
    fi
    # Install WireGuard config if missing
    WG_IF="${WG_INTERFACE:-wg0}"
    WG_DIR="${WG_DIR:-/etc/wireguard}"
    CONFIG="$WG_DIR/${WG_IF}.conf"
    if [ ! -f "$CONFIG" ]; then
      mkdir -p "$WG_DIR"
      umask 077
      wg genkey | tee "$WG_DIR/server_private.key" | wg pubkey > "$WG_DIR/server_public.key"
      SERVER_PRIVATE="$(cat "$WG_DIR/server_private.key")"
      cat > "$CONFIG" << EOF
[Interface]
PrivateKey = $SERVER_PRIVATE
ListenPort = $WG_PORT
Address = 10.0.113.1/24
# Replace eth0 with your internet-facing interface (e.g. ens3) if needed
PostUp = iptables -A FORWARD -i $WG_IF -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i $WG_IF -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
EOF
      echo "Created $CONFIG (edit eth0 in PostUp/PostDown if your main interface is different)"
    fi
    SERVER_PUBLIC="$(cat "$WG_DIR/server_public.key" 2>/dev/null || echo '')"
    # Isolation script
    if [ -f "$PROJECT_DIR/scripts/setup-wg-isolation.sh" ]; then
      chmod +x "$PROJECT_DIR/scripts/setup-wg-isolation.sh"
      WG_INTERFACE="$WG_IF" sh "$PROJECT_DIR/scripts/setup-wg-isolation.sh" || true
    fi
    wg-quick up "$WG_IF" 2>/dev/null || true
    # Config and env
    mkdir -p "$PROJECT_DIR/data"
    cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
DATABASE_PATH=$PROJECT_DIR/data/bot.db
EOF
    cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: []
wireguard:
  interface: $WG_IF
  config_path: $CONFIG
  port: $WG_PORT
  common_subnet: "10.0.113.0/24"
database:
  path: $PROJECT_DIR/data/bot.db
server:
  public_key: "$SERVER_PUBLIC"
  endpoint: "$ENDPOINT"
  port: $WG_PORT
EOF
    # Python venv and deps
    python3 -m venv "$PROJECT_DIR/.venv"
    "$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
    # Systemd: WireGuard
    if command -v systemctl >/dev/null 2>&1; then
      systemctl enable wg-quick@${WG_IF} 2>/dev/null || true
      systemctl start wg-quick@${WG_IF} 2>/dev/null || true
    fi
    # Systemd: bot
    cat > /etc/systemd/system/wireguard-bot.service << EOF
[Unit]
Description=WireGuard Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/python -m src.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable wireguard-bot
    systemctl start wireguard-bot
    echo "Native install done. Bot: systemctl status wireguard-bot"
    ;;
  *)
    # --- Docker ---
    if ! command -v docker >/dev/null 2>&1; then
      echo "Install Docker first: https://docs.docker.com/engine/install/"
      exit 1
    fi
    mkdir -p "$PROJECT_DIR/data"
    cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
WG_SERVER_ENDPOINT=$ENDPOINT
CONFIG_PATH=/app/config.yaml
DATABASE_PATH=/data/bot.db
EOF
    SERVER_PUBLIC=""
    if [ -f "/etc/wireguard/wg0.conf" ]; then
      SERVER_PUBLIC="$(wg show wg0 public-key 2>/dev/null || true)"
    fi
    cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: []
wireguard:
  interface: wg0
  config_path: /etc/wireguard/wg0.conf
  port: $WG_PORT
database:
  path: /data/bot.db
server:
  public_key: "$SERVER_PUBLIC"
  endpoint: "$ENDPOINT"
  port: $WG_PORT
EOF
    (cd "$PROJECT_DIR" && docker compose up -d --build)
    echo "Docker install done. Bot: docker compose -f $PROJECT_DIR/docker-compose.yml ps"
    echo "Mount host /etc/wireguard if the bot must manage WG configs."
    ;;
esac

echo ""
echo "Done. Add admins in config; use the bot to generate one-time referral links for new users."
