# WGControlBot

Telegram bot for managing WireGuard VPN users and client configs.

The bot can create client configs in a common VPN subnet or in isolated per-user subnets, manage users through Telegram, generate one-time invite links, and collect daily peer statistics.

## Features

- Interactive Telegram menu for users and admins
- WireGuard client config generation
- Common subnet: `10.0.113.0/24`
- Isolated subnets: `10.0.i.0/24`, excluding `10.0.113.0/24`
- User enable/disable/delete actions
- Config enable/disable/delete actions
- One-time referral links for registration
- SQLite storage
- Daily stats collection

## Requirements

- Debian/Ubuntu server with root access
- Public IP address or domain name
- Telegram bot token from [@BotFather](https://t.me/botfather)
- Your Telegram numeric user ID for admin access
- Open UDP port for WireGuard, random `51820-51850` by default

The installer sets up Docker, WireGuard inside the Docker container, iptables rules, configs, and starts everything with Docker Compose.

## One-Command Install

Run this on the server:

```bash
curl -fsSL https://raw.githubusercontent.com/etunb/WGControlBot/master/scripts/install.sh | sudo bash
```

The installer asks all required questions in the terminal:

- Telegram bot token
- Telegram admin ID(s), comma-separated
- Public server IP/domain for client configs
- WireGuard interface, default `wg0`
- WireGuard UDP port, default random `51820-51850`
- External network interface for NAT, auto-detected by default

When run through the one-command installer, it also asks for the installation directory, default `/opt/wgcontrolbot`.

The bot and WireGuard tools run in the same privileged Docker container. The container uses host networking so the WireGuard UDP port is opened directly on the server. WireGuard config files live in the project `wireguard/` directory and are mounted into the container as `/etc/wireguard`.

After installation:

```bash
cd /opt/wgcontrolbot
docker compose ps
docker compose logs -f
```

WireGuard status from the container:

```bash
cd /opt/wgcontrolbot
docker compose exec bot wg show
```

## Non-Interactive Defaults

You can predefine installation paths and WireGuard settings:

```bash
export WIREGUARD_BOT_DIR=/opt/wgcontrolbot
export WIREGUARD_BOT_REPO=https://github.com/etunb/WGControlBot.git
export WG_INTERFACE=wg0
export WG_PORT=51820
export WG_MAIN_IFACE=eth0
curl -fsSL https://raw.githubusercontent.com/etunb/WGControlBot/master/scripts/install.sh | sudo -E bash
```

The bot token, admin IDs, and endpoint are still asked interactively.

## Manual Install From Clone

```bash
git clone https://github.com/etunb/WGControlBot.git
cd WGControlBot
sudo bash scripts/install.sh
```

If the installer is run from a cloned project directory, it uses the current directory instead of cloning into `/opt/wgcontrolbot`.

## Configuration Files

The installer creates:

- `.env`
- `config.yaml`
- `wireguard/wg0.conf`, or another interface if selected
- `data/bot.db`

Example `config.yaml`:

```yaml
bot:
  token: "YOUR_BOT_TOKEN"
  admin_ids: [123456789]
wireguard:
  interface: wg0
  config_path: /etc/wireguard/wg0.conf
  port: 51820
  common_subnet: "10.0.113.0/24"
  isolated_subnet_prefix: "10.0"
  isolated_subnet_mask: 24
database:
  path: /data/bot.db
server:
  public_key: "SERVER_PUBLIC_KEY"
  endpoint: "vpn.example.com"
  port: 51820
```

Keep `.env` and `config.yaml` private. They are ignored by git.

## Telegram Usage

1. Send `/start` to the bot.
2. The admin IDs entered during install get admin access.
3. Use "Пригласительная ссылка" to create a one-time invite link.
4. Users open the invite link and then manage their VPN configs from the menu.

Admins can also run:

```text
/add_user <telegram_id> [admin: 0|1]
```

## Network Isolation

The installer enables IP forwarding and applies iptables rules through:

```bash
scripts/setup-wg-isolation.sh
```

Rules allow:

- `10.0.113.2` through `10.0.113.100` to reach all VPN subnets
- `10.0.113.101` through `10.0.113.254` to communicate only inside `10.0.113.0/24`
- Other VPN subnets to reach only `10.0.113.2` through `10.0.113.100` in the common subnet
- Isolated subnet peers to reach peers in the same isolated subnet
- Other WireGuard-to-WireGuard traffic to be dropped

The WireGuard config calls the script from `PostUp` and `PostDown` inside the container, so rules are restored when the container restarts.

## Troubleshooting

Bot logs:

```bash
cd /opt/wgcontrolbot
docker compose logs -f
```

WireGuard status:

```bash
cd /opt/wgcontrolbot
docker compose exec bot wg show
```

Firewall checks:

```bash
iptables -L FORWARD -v -n
iptables -t nat -L POSTROUTING -v -n
```

Common issues:

- Open the selected UDP port on the server firewall and router/cloud security group.
- Make sure the endpoint entered during install is reachable from client devices.
- The container needs host networking, privileged mode, `NET_ADMIN`, and `/lib/modules` mounted. These are already set in `docker-compose.yml`.

## Project Structure

```text
WGControlBot/
├── config.example.yaml
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── docker-entrypoint.sh
├── requirements.txt
├── scripts/
│   ├── install.sh
│   ├── deploy.sh
│   └── setup-wg-isolation.sh
├── wireguard/
│   └── wg0.conf
├── src/
│   ├── main.py
│   ├── bot/
│   ├── db/
│   ├── wireguard/
│   └── stats/
└── data/
    └── bot.db
```
