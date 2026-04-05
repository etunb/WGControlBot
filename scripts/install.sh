#!/bin/sh
# One-line install: sh -c "$(curl -fsSL https://YOUR_HOST/install.sh)"
# Or: curl -fsSL https://YOUR_HOST/install.sh | sh
#
# Optional environment variables:
#   WIREGUARD_BOT_REPO - Git repository URL
#   WIREGUARD_BOT_DIR  - Installation directory (default: /opt/wireguard-bot)
#   WG_MAIN_IFACE      - External network interface for NAT (default: auto-detected)

set -e

# If we're in a project dir (has src/main.py), use it; else clone
PROJECT_DIR="${WIREGUARD_BOT_DIR:-/opt/wireguard-bot}"
if [ -f "src/main.py" ] && [ -f "requirements.txt" ]; then
  PROJECT_DIR="$(pwd)"
  echo "Using project directory: $PROJECT_DIR"
else
  REPO="${WIREGUARD_BOT_REPO:-}"
  if [ -z "$REPO" ]; then
    echo "WireGuard Telegram Bot — installation"
    echo "Run from project directory, or set WIREGUARD_BOT_REPO to git URL."
    printf "Git URL (e.g. https://github.com/user/wireguard-bot.git): "
    read -r REPO
    if [ -z "$REPO" ]; then
      echo "No URL provided. Exiting."
      echo "Usage: git clone <repo> $PROJECT_DIR && cd $PROJECT_DIR && sh scripts/install.sh"
      exit 1
    fi
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "Git is not installed. Please install git first."
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
echo "Select installation method:"
echo "  1) Docker (recommended)"
echo "  2) Native (systemd + WireGuard on host)"
printf "Choice [1]: "
read -r choice
choice="${choice:-1}"

# Common prompts
echo ""
printf "Telegram bot token (from @BotFather): "
read -r BOT_TOKEN
printf "Telegram admin ID(s), comma-separated: "
read -r ADMIN_IDS
printf "Server endpoint (hostname or IP for client configs): "
read -r ENDPOINT

if [ -z "$BOT_TOKEN" ] || [ -z "$ADMIN_IDS" ]; then
  echo "Error: Bot token and admin IDs are required."
  exit 1
fi

# Generate a random port for WireGuard within typical range
WG_PORT="${WG_PORT:-$(shuf -i 51820-51850 -n 1 2>/dev/null || echo 51820)}"
echo "Using WireGuard port: $WG_PORT"

case "$choice" in
  2)
    # --- Native installation ---
    if [ "$(id -u)" -ne 0 ]; then
      echo "Native installation requires root privileges. Please run with sudo or as root."
      exit 1
    fi

    # Check for supported package manager (Debian/Ubuntu)
    if ! command -v apt-get >/dev/null 2>&1; then
      echo "This installer currently supports Debian/Ubuntu for automatic dependency installation."
      echo "On other distributions, please install dependencies manually:"
      echo "  wireguard-tools, python3, python3-venv, python3-pip, iptables"
      exit 1
    fi

    # Install system dependencies
    apt-get update
    apt-get install -y --no-install-recommends wireguard-tools python3 python3-venv python3-pip iptables

    # Determine the main external network interface for NAT (outgoing internet)
    MAIN_IFACE="${WG_MAIN_IFACE:-}"
    if [ -z "$MAIN_IFACE" ]; then
      if command -v ip >/dev/null 2>&1; then
        MAIN_IFACE=$(ip route | grep default | awk '{print $5}' | head -n1)
      fi
      if [ -z "$MAIN_IFACE" ]; then
        # Try common interface names
        for iface in eth0 ens3 enp0s3; do
          if ip link show "$iface" >/dev/null 2>&1; then
            MAIN_IFACE="$iface"
            break
          fi
        done
      fi
      if [ -z "$MAIN_IFACE" ]; then
        MAIN_IFACE="eth0"
        echo "Warning: Could not auto-detect external interface. Defaulting to eth0."
        echo "         If incorrect, set WG_MAIN_IFACE environment variable to the correct interface."
      fi
    fi
    echo "External interface for NAT: $MAIN_IFACE"

    # WireGuard configuration
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
PostUp = iptables -A FORWARD -i $WG_IF -j ACCEPT; iptables -t nat -A POSTROUTING -o $MAIN_IFACE -j MASQUERADE
PostDown = iptables -D FORWARD -i $WG_IF -j ACCEPT; iptables -t nat -D POSTROUTING -o $MAIN_IFACE -j MASQUERADE
EOF
      echo "Created WireGuard config: $CONFIG"
    else
      SERVER_PRIVATE=""
      echo "WireGuard config already exists: $CONFIG"
    fi

    SERVER_PUBLIC="$(cat "$WG_DIR/server_public.key" 2>/dev/null || echo '')"

    # Apply isolation rules
    if [ -f "$PROJECT_DIR/scripts/setup-wg-isolation.sh" ]; then
      chmod +x "$PROJECT_DIR/scripts/setup-wg-isolation.sh"
      WG_INTERFACE="$WG_IF" "$PROJECT_DIR/scripts/setup-wg-isolation.sh" || true
    fi

    # Bring up the WireGuard interface
    wg-quick up "$WG_IF" 2>/dev/null || true

    # Create project data directory
    mkdir -p "$PROJECT_DIR/data"

    # Prepare admin IDs as a YAML list
    ADMIN_IDS_YAML="[$(echo "$ADMIN_IDS" | sed 's/,/, /g')]"

    # Create .env file
    cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
DATABASE_PATH=$PROJECT_DIR/data/bot.db
EOF

    # Create config.yaml
    cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: $ADMIN_IDS_YAML
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

    # Python virtual environment and dependencies
    python3 -m venv "$PROJECT_DIR/.venv"
    "$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"

    # Enable and start WireGuard via systemd (if available)
    if command -v systemctl >/dev/null 2>&1; then
      systemctl enable wg-quick@${WG_IF} 2>/dev/null || true
      systemctl start wg-quick@${WG_IF} 2>/dev/null || true
    fi

    # Create systemd service for the bot
    cat > /etc/systemd/system/wireguard-bot.service << EOF
[Unit]
Description=WireGuard Telegram Bot
After=network.target

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
    systemctl enable wireguard-bot
    systemctl start wireguard-bot

    echo "Native installation completed."
    echo "Check bot status: systemctl status wireguard-bot"
    echo "View logs: journalctl -u wireguard-bot -f"
    ;;
  *)
    # --- Docker installation ---
    if ! command -v docker >/dev/null 2>&1; then
      echo "Docker is not installed. Please install Docker first: https://docs.docker.com/engine/install/"
      exit 1
    fi

    # Detect docker compose command (v2 or v1)
    if docker compose version >/dev/null 2>&1; then
      COMPOSE_CMD="docker compose"
    elif command -v docker-compose >/dev/null 2>&1; then
      COMPOSE_CMD="docker-compose"
    else
      echo "Docker Compose not found. Please install Docker Compose."
      exit 1
    fi

    mkdir -p "$PROJECT_DIR/data"

    # Create .env file
    cat > "$PROJECT_DIR/.env" << EOF
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_ADMIN_IDS=$ADMIN_IDS
WG_SERVER_ENDPOINT=$ENDPOINT
CONFIG_PATH=/app/config.yaml
DATABASE_PATH=/data/bot.db
EOF

    # Prepare admin IDs as YAML list
    ADMIN_IDS_YAML="[$(echo "$ADMIN_IDS" | sed 's/,/, /g')]"

    # Try to get server public key if host WG config exists (optional)
    SERVER_PUBLIC=""
    if [ -f "/etc/wireguard/wg0.conf" ]; then
      SERVER_PUBLIC="$(wg show wg0 public-key 2>/dev/null 2>&1 || true)"
    fi

    # Create config.yaml
    cat > "$PROJECT_DIR/config.yaml" << EOF
bot:
  token: "$BOT_TOKEN"
  admin_ids: $ADMIN_IDS_YAML
wireguard:
  interface: wg0
  config_path: /etc/wireguard/wg0.conf
  port: $WG_PORT
  common_subnet: "10.0.113.0/24"
database:
  path: /data/bot.db
server:
  public_key: "$SERVER_PUBLIC"
  endpoint: "$ENDPOINT"
  port: $WG_PORT
EOF

    # Build and start containers
    (cd "$PROJECT_DIR" && $COMPOSE_CMD up -d --build)

    echo "Docker installation completed."
    echo "Check bot status: $COMPOSE_CMD -f $PROJECT_DIR/docker-compose.yml ps"
    echo "Note: If WireGuard runs on the host, mount /etc/wireguard into the container (docker-compose.yml)."
    ;;
esac

echo ""
echo "Installation finished. Start the bot in Telegram, generate a referral link to add users."
echo "Don't forget to open UDP port $WG_PORT on your firewall and router."
