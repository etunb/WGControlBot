"""SQLite async database and schema."""
import aiosqlite
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "bot.db"

SCHEMA = """
-- Users: telegram users allowed to use the bot
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    isolated_subnet_index INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Peer configs (WireGuard clients)
CREATE TABLE IF NOT EXISTS peer_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    subnet_type TEXT NOT NULL CHECK(subnet_type IN ('common', 'isolated')),
    subnet_index INTEGER,
    address TEXT NOT NULL UNIQUE,
    private_key TEXT NOT NULL,
    public_key TEXT NOT NULL UNIQUE,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_handshake TEXT,
    rx_bytes INTEGER DEFAULT 0,
    tx_bytes INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_peer_user ON peer_configs(user_id);
CREATE INDEX IF NOT EXISTS idx_peer_enabled ON peer_configs(is_enabled);
CREATE INDEX IF NOT EXISTS idx_peer_subnet ON peer_configs(subnet_type, subnet_index);

-- Daily stats (filled once per day)
CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    total_peers INTEGER NOT NULL,
    enabled_peers INTEGER NOT NULL,
    total_rx_bytes INTEGER NOT NULL,
    total_tx_bytes INTEGER NOT NULL,
    peers_by_subnet TEXT NOT NULL
);

-- One-time referral links (admin generates; first click adds user, link then invalid)
CREATE TABLE IF NOT EXISTS referral_links (
    token TEXT PRIMARY KEY,
    created_by INTEGER NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    used_at TEXT,
    used_by_telegram_id INTEGER
);
"""


async def init_db(path: str | Path | None = None) -> None:
    p = Path(path) if path else DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(p) as db:
        await db.executescript(SCHEMA)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN isolated_subnet_index INTEGER")
            await db.commit()
        except Exception:
            pass
        await db.commit()


def get_db_path(path: str | Path | None = None) -> Path:
    return Path(path) if path else DB_PATH


async def get_db(path: str | Path | None = None):
    """Async context manager for DB connection."""
    p = get_db_path(path)
    return aiosqlite.connect(p)
