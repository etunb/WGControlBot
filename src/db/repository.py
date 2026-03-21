"""Repository: users and peer configs CRUD."""
import json
import secrets
from pathlib import Path
from typing import Optional

import aiosqlite

from .database import get_db_path, init_db, DB_PATH
from .models import User, PeerConfig, DailyStats, SUBNET_COMMON, SUBNET_ISOLATED


async def ensure_db(path: Optional[str | Path] = None) -> None:
    await init_db(path or DB_PATH)


async def get_user_by_telegram_id(telegram_id: int, db_path: Optional[Path] = None) -> Optional[User]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, telegram_id, username, is_admin, is_active, isolated_subnet_index, created_at FROM users WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return User(id=row[0], telegram_id=row[1], username=row[2], is_admin=bool(row[3]), is_active=bool(row[4]), isolated_subnet_index=row[5], created_at=row[6] or "")


async def get_user_by_id(user_id: int, db_path: Optional[Path] = None) -> Optional[User]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, telegram_id, username, is_admin, is_active, isolated_subnet_index, created_at FROM users WHERE id = ?",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    return User(id=row[0], telegram_id=row[1], username=row[2], is_admin=bool(row[3]), is_active=bool(row[4]), isolated_subnet_index=row[5], created_at=row[6] or "")


async def add_user(telegram_id: int, username: Optional[str], is_admin: bool, db_path: Optional[Path] = None) -> User:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO users (telegram_id, username, is_admin, is_active) VALUES (?, ?, ?, 1)",
            (telegram_id, username, 1 if is_admin else 0),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            uid = (await cur.fetchone())[0]
    return await get_user_by_id(uid, db_path)  # type: ignore


async def set_user_active(telegram_id: int, active: bool, db_path: Optional[Path] = None) -> bool:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("UPDATE users SET is_active = ? WHERE telegram_id = ?", (1 if active else 0, telegram_id))
        await db.commit()
        return cur.rowcount > 0


async def delete_user(telegram_id: int, db_path: Optional[Path] = None) -> bool:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()
        return cur.rowcount > 0


async def set_user_isolated_subnet(user_id: int, subnet_index: int, db_path: Optional[Path] = None) -> None:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("UPDATE users SET isolated_subnet_index = ? WHERE id = ?", (subnet_index, user_id))
        await db.commit()


async def list_users(db_path: Optional[Path] = None) -> list[User]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, telegram_id, username, is_admin, is_active, isolated_subnet_index, created_at FROM users ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [
        User(id=r[0], telegram_id=r[1], username=r[2], is_admin=bool(r[3]), is_active=bool(r[4]), isolated_subnet_index=r[5], created_at=r[6] or "")
        for r in rows
    ]


def _row_to_peer(r: tuple) -> PeerConfig:
    return PeerConfig(
        id=r[0],
        user_id=r[1],
        name=r[2],
        subnet_type=r[3],
        subnet_index=r[4],
        address=r[5],
        private_key=r[6],
        public_key=r[7],
        is_enabled=bool(r[8]),
        created_at=r[9],
        last_handshake=r[10] if len(r) > 10 else None,
        rx_bytes=r[11] if len(r) > 11 else 0,
        tx_bytes=r[12] if len(r) > 12 else 0,
    )


async def get_peer_by_id(peer_id: int, db_path: Optional[Path] = None) -> Optional[PeerConfig]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, user_id, name, subnet_type, subnet_index, address, private_key, public_key, is_enabled, created_at, last_handshake, rx_bytes, tx_bytes FROM peer_configs WHERE id = ?",
            (peer_id,),
        ) as cur:
            row = await cur.fetchone()
    return _row_to_peer(row) if row else None


async def get_peer_by_public_key(public_key: str, db_path: Optional[Path] = None) -> Optional[PeerConfig]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, user_id, name, subnet_type, subnet_index, address, private_key, public_key, is_enabled, created_at, last_handshake, rx_bytes, tx_bytes FROM peer_configs WHERE public_key = ?",
            (public_key,),
        ) as cur:
            row = await cur.fetchone()
    return _row_to_peer(row) if row else None


async def list_peers_for_user(user_id: int, db_path: Optional[Path] = None) -> list[PeerConfig]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, user_id, name, subnet_type, subnet_index, address, private_key, public_key, is_enabled, created_at, last_handshake, rx_bytes, tx_bytes FROM peer_configs WHERE user_id = ? ORDER BY id",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_peer(r) for r in rows]


async def list_all_peers(db_path: Optional[Path] = None) -> list[PeerConfig]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT id, user_id, name, subnet_type, subnet_index, address, private_key, public_key, is_enabled, created_at, last_handshake, rx_bytes, tx_bytes FROM peer_configs ORDER BY id"
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_peer(r) for r in rows]


async def list_used_addresses(db_path: Optional[Path] = None) -> list[str]:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT address FROM peer_configs") as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


async def add_peer(
    user_id: int,
    name: str,
    subnet_type: str,
    subnet_index: Optional[int],
    address: str,
    private_key: str,
    public_key: str,
    db_path: Optional[Path] = None,
) -> PeerConfig:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO peer_configs (user_id, name, subnet_type, subnet_index, address, private_key, public_key, is_enabled) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (user_id, name, subnet_type, subnet_index, address, private_key, public_key),
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            pid = (await cur.fetchone())[0]
    return await get_peer_by_id(pid, db_path)  # type: ignore


async def set_peer_enabled(peer_id: int, enabled: bool, db_path: Optional[Path] = None) -> bool:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        cur = await db.execute("UPDATE peer_configs SET is_enabled = ? WHERE id = ?", (1 if enabled else 0, peer_id))
        await db.commit()
        return cur.rowcount > 0


async def delete_peer(peer_id: int, db_path: Optional[Path] = None) -> Optional[PeerConfig]:
    peer = await get_peer_by_id(peer_id, db_path)
    if not peer:
        return None
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM peer_configs WHERE id = ?", (peer_id,))
        await db.commit()
    return peer


async def get_next_isolated_subnet_index(db_path: Optional[Path] = None) -> int:
    """Return next free subnet index for isolated (1, 2, 3, ... excluding 113)."""
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT DISTINCT subnet_index FROM peer_configs WHERE subnet_type = ? AND subnet_index IS NOT NULL ORDER BY subnet_index", (SUBNET_ISOLATED,)) as cur:
            used = [r[0] for r in await cur.fetchall()]
    for i in range(1, 256):
        if i == 113:
            continue
        if i not in used:
            return i
    raise RuntimeError("No free isolated subnet index")


async def save_daily_stats(
    date: str,
    total_peers: int,
    enabled_peers: int,
    total_rx: int,
    total_tx: int,
    peers_by_subnet: dict,
    db_path: Optional[Path] = None,
) -> None:
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO daily_stats (date, total_peers, enabled_peers, total_rx_bytes, total_tx_bytes, peers_by_subnet) VALUES (?, ?, ?, ?, ?, ?)",
            (date, total_peers, enabled_peers, total_rx, total_tx, json.dumps(peers_by_subnet)),
        )
        await db.commit()


async def get_peers_for_stats(db_path: Optional[Path] = None) -> list[tuple[str, int, int, bool]]:
    """Returns list of (public_key, rx_bytes, tx_bytes, is_enabled)."""
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT public_key, rx_bytes, tx_bytes, is_enabled FROM peer_configs") as cur:
            return await cur.fetchall()


# --- Referral links (one-time) ---

async def create_referral_link(created_by_user_id: int, db_path: Optional[Path] = None) -> str:
    """Create one-time referral link. Returns token (e.g. ref_abc123)."""
    token = "ref_" + secrets.token_urlsafe(24)
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT INTO referral_links (token, created_by) VALUES (?, ?)",
            (token, created_by_user_id),
        )
        await db.commit()
    return token


async def get_referral_by_token(token: str, db_path: Optional[Path] = None) -> Optional[tuple[int, Optional[str], Optional[int]]]:
    """Return (created_by_user_id, used_at, used_by_telegram_id) or None."""
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT created_by, used_at, used_by_telegram_id FROM referral_links WHERE token = ?",
            (token,),
        ) as cur:
            row = await cur.fetchone()
    return tuple(row) if row else None


async def use_referral_link(
    token: str,
    telegram_id: int,
    username: Optional[str],
    db_path: Optional[Path] = None,
) -> bool:
    """Mark link as used and add user. Returns True if link was valid and unused."""
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT created_by, used_at FROM referral_links WHERE token = ?",
            (token,),
        ) as cur:
            row = await cur.fetchone()
        if not row or row[1] is not None:
            return False
        await db.execute(
            "UPDATE referral_links SET used_at = datetime('now'), used_by_telegram_id = ? WHERE token = ?",
            (telegram_id, token),
        )
        await db.execute(
            "INSERT OR IGNORE INTO users (telegram_id, username, is_admin, is_active) VALUES (?, ?, 0, 1)",
            (telegram_id, username),
        )
        await db.commit()
    return True
