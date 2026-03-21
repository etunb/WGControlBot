"""Load config from YAML and env."""
import os
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(os.getenv("CONFIG_PATH", "config.yaml"))


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config not found: {CONFIG_PATH}. Copy config.example.yaml to config.yaml")
    with open(CONFIG_PATH) as f:
        data = yaml.safe_load(f) or {}
    # Override from env
    if token := os.getenv("TELEGRAM_BOT_TOKEN"):
        data.setdefault("bot", {})["token"] = token
    if admin_ids := os.getenv("TELEGRAM_ADMIN_IDS"):
        data.setdefault("bot", {})["admin_ids"] = [int(x.strip()) for x in admin_ids.split(",") if x.strip()]
    if db_path := os.getenv("DATABASE_PATH"):
        data.setdefault("database", {})["path"] = db_path
    return data
