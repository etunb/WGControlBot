# WireGuard Control Bot

Telegram bot for managing WireGuard VPN users and configurations with network isolation and daily statistics.

## Features

### For Users
- Create WireGuard configs in the **common network** (all devices see each other) or a **personal isolated network**
- Enable, disable, or delete their own configs
- Simple inline menu interface

### For Admins
- All user features, plus:
- Create configs in **any isolated subnet** (specify subnet number)
- User management: add, disable, delete users
- **One-time referral links** - share a link, first user who opens it becomes registered
- View daily statistics (peers, traffic by subnet)

## Architecture

- **WireGuard VPN** runs on the server (random port by default)
- **Telegram bot** (Python, aiogram) manages users and generates configs
- **SQLite** stores user data and daily statistics
- **Network isolation** via iptables rules:
  - `10.0.113.0/24` — common subnet (all devices can communicate)
  - `10.0.i.0/24` (i ≠ 113) — isolated subnets (devices only see others in same subnet)

## Requirements

- Linux server (Debian/Ubuntu recommended)
- Python 3.10+ (for native install) or Docker + Docker Compose
- Telegram bot token from [@BotFather](https://t.me/botfather)
- Server with a public IP address or domain
- UDP port open on firewall (random between 51820-51850 by default)

## Quick Install

### Option 1: One-Command Installer (Recommended)

From your terminal:

```bash
# Clone the repository
git clone https://github.com/etunb/WGControlBot.git
cd WGControlBot

# Run the interactive installer
sudo sh scripts/install.sh
```

The installer will:
1. Ask whether to use Docker or native/systemd
2. Prompt for Telegram bot token, admin IDs, and server endpoint
3. Set up WireGuard (generate keys, random port)
4. Configure and start the bot with autostart

For remote download (without cloning):
```bash
export WIREGUARD_BOT_REPO=https://github.com/youruser/wireguard-bot.git
sh -c "$(curl -fsSL https://YOUR_HOST/scripts/install.sh)"
```

### Option 2: Manual Docker Setup

```bash
git clone https://github.com/etunb/WGControlBot.git
cd WGControlBot

# Copy and edit configuration files
cp config.example.yaml config.yaml
cp .env.example .env
# Edit config.yaml and .env with your values (see Configuration section)

# Start services
docker compose up -d
```

### Option 3: Manual Native Setup

```bash
git clone https://github.com/etunb/WGControlBot.git
cd WGControlBot

# 1. Deploy WireGuard on the server (run once)
sudo sh scripts/deploy.sh
# Copy the output (public_key, port) to config.yaml

# 2. Create configuration files
cp config.example.yaml config.yaml
cp .env.example .env
# Fill in config.yaml and .env

# 3. Set up Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4. Run the bot (for testing)
python -m src.main

# 5. Set up systemd service (autostart)
sudo cp scripts/wireguard-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wireguard-bot
sudo systemctl start wireguard-bot
```

## Configuration

### `config.yaml`

```yaml
bot:
  token: "YOUR_BOT_TOKEN"
  admin_ids: [123456789, 987654321]  # Telegram user IDs

wireguard:
  interface: wg0
  config_path: /etc/wireguard/wg0.conf  # Path to WG server config
  port: 51820  # Optional: omit to use random port from deploy
  common_subnet: "10.0.113.0/24"

database:
  path: /data/bot.db  # Or ./data/bot.db for native

server:
  public_key: "SERVER_PUBLIC_KEY"  # From deploy.sh output
  endpoint: "your-server.com"      # Public IP or domain
  port: 51820                      # Same as wireguard.port
```

### `.env`

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_IDS=123456789,987654321
DATABASE_PATH=/data/bot.db
# Optional: WG_SERVER_ENDPOINT overrides server.endpoint
```

## Setup After Installation

1. **Start the bot** in Telegram by sending `/start` to it.
2. **Add initial admins**: The IDs in `config.yaml` are automatically added as admins on first `/start`. You can also use `/add_user <telegram_id> 1` in the bot.
3. **Generate a referral link**: As admin, tap "🔗 Пригласительная ссылка" and share it with new users. The first user to click becomes registered.
4. **Open firewall port**: Allow UDP on the WireGuard port (`$WG_PORT`) and set up port forwarding on your router if needed.

## Network Isolation

The bot supports:
- **Common network** (`10.0.113.0/24`): all devices can communicate with each other and with isolated networks.
- **Isolated networks** (`10.0.1.0/24`, `10.0.2.0/24`, ...): devices only see others in the same isolated subnet. They can still access the common network.

Isolation is enforced by `scripts/setup-wg-isolation.sh`, which applies iptables FORWARD rules. Run it manually or include it in WireGuard's PostUp if desired.

## Statistics

Daily statistics are collected automatically at 00:05. Data includes:
- Total peers and active peers
- Traffic (rx/tx)
- Distribution by subnet

View statistics via the bot's admin interface.

## Troubleshooting

**Bot doesn't start:**
- Check logs: `docker compose logs -f` or `journalctl -u wireguard-bot -f`
- Ensure config.yaml and .env exist and are correct
- Verify database path is writable

**WireGuard config not generating:**
- Run `sudo sh scripts/deploy.sh` manually
- Ensure ports are open: `sudo ufw allow 51820/udp`

**Clients can't connect:**
- Verify server endpoint is reachable from internet
- Check firewall allows UDP on the WireGuard port
- Confirm NAT rules exist: `sudo iptables -L FORWARD -v`

**Docker can't manage WireGuard:**
- The bot reads `/etc/wireguard/wg0.conf`. Mount it: in `docker-compose.yml` uncomment the volume.
- For full WG management, run the bot in privileged mode or on the host network (not recommended).

## Project Structure

```
WGControlBot/
├── config.example.yaml
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── scripts/
│   ├── install.sh          # Interactive installer
│   ├── deploy.sh           # Deploy WireGuard once
│   └── setup-wg-isolation.sh  # iptables rules
│   # systemd unit file is created by install.sh, not in repo
├── src/
│   ├── main.py             # Entry point, scheduler
│   ├── config.py
│   ├── bot/
│   │   ├── handlers.py     # Telegram command handlers
│   │   ├── filters.py
│   │   └── keyboards.py
│   ├── db/
│   │   ├── database.py
│   │   ├── models.py
│   │   └── repository.py
│   ├── wireguard/
│   │   └── manager.py      # WG config generation
│   └── stats/
│       └── collector.py    # Daily stats collection
└── data/                   # Created at runtime (not in repo)
    └── bot.db
```

## Security Notes

- Keep `config.yaml` and `.env` out of version control (they're in `.gitignore`).
- The bot requires root privileges only if managing WireGuard directly on the host (native install). In Docker, it needs access to `/etc/wireguard`.
- WireGuard private keys are stored in `/etc/wireguard/` with restrictive permissions (umask 077).
- Use HTTPS/Tor for additional privacy when distributing client configs (the endpoint is stored in plain text).

## License

MIT

## Support

Report issues: https://github.com/etunb/WGControlBot/issues
