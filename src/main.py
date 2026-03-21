"""Entry point: load config, init DB, start WireGuard (if needed), run bot and daily stats job."""
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot, Dispatcher

from src.config import load_config
from src.db.database import init_db, get_db_path
from src.db.repository import ensure_db
from src.wireguard.manager import WireGuardManager, get_random_port
from src.bot.handlers import create_router
from src.stats.collector import collect_daily_stats


def main():
    config = load_config()
    bot_cfg = config.get("bot", {})
    wg_cfg = config.get("wireguard", {})
    db_cfg = config.get("database", {})
    server_cfg = config.get("server", {})

    token = bot_cfg.get("token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN or bot.token required")

    admin_ids = bot_cfg.get("admin_ids") or []
    if not admin_ids and os.getenv("TELEGRAM_ADMIN_IDS"):
        admin_ids = [int(x) for x in os.getenv("TELEGRAM_ADMIN_IDS").split(",")]

    db_path = Path(db_cfg.get("path", "data/bot.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)

    interface = wg_cfg.get("interface", "wg0")
    config_path = Path(wg_cfg.get("config_path", "/etc/wireguard/wg0.conf"))
    common_subnet = wg_cfg.get("common_subnet", "10.0.113.0/24")
    isolated_prefix = wg_cfg.get("isolated_subnet_prefix", "10.0")
    isolated_mask = wg_cfg.get("isolated_subnet_mask", 24)

    port = wg_cfg.get("port")
    if port is None:
        port = get_random_port()
        print(f"WireGuard port (random): {port}")

    wg_manager = WireGuardManager(
        interface=interface,
        config_path=config_path,
        common_subnet=common_subnet,
        isolated_prefix=isolated_prefix,
        isolated_mask=isolated_mask,
    )
    # Ensure server has ListenPort
    try:
        wg_manager.ensure_server_config(port)
    except Exception as e:
        print(f"Warning: could not ensure WG server config: {e}")

    server_public_key = server_cfg.get("public_key", "")
    server_endpoint = server_cfg.get("endpoint", "") or os.getenv("WG_SERVER_ENDPOINT", "")
    if not server_endpoint:
        print("Warning: server.endpoint or WG_SERVER_ENDPOINT not set; client configs will have empty endpoint.")

    router = create_router(
        admin_ids=admin_ids,
        wg_manager=wg_manager,
        server_public_key=server_public_key,
        server_endpoint=server_endpoint,
        server_port=port,
        db_path=db_path,
    )

    async def run_bot():
        await ensure_db(db_path)
        scheduler = AsyncIOScheduler()
        scheduler.add_job(
            collect_daily_stats,
            "cron",
            hour=0,
            minute=5,
            id="daily_stats",
            kwargs={"interface": interface, "db_path": db_path},
        )
        scheduler.start()
        bot = Bot(token=token)
        dp = Dispatcher()
        dp.include_router(router)
        try:
            await dp.start_polling(bot)
        finally:
            scheduler.shutdown(wait=False)

    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
