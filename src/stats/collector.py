"""Daily stats collection: aggregate peer counts and traffic into SQLite."""
import subprocess
from collections import defaultdict
from datetime import date
from pathlib import Path

from src.db import get_db_path
from src.db.repository import (
    get_peers_for_stats,
    list_all_peers,
    save_daily_stats,
)


def _get_wg_stats(interface: str = "wg0") -> dict[str, dict]:
    """Parse `wg show <interface>` and return dict public_key -> {rx, tx, last_handshake}."""
    try:
        out = subprocess.run(
            ["wg", "show", interface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    result = {}
    current = None
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("peer:"):
            current = line.split(":", 1)[1].strip()
            result[current] = {"rx": 0, "tx": 0, "last_handshake": None}
        elif current and ":" in line:
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "transfer":
                # "1.23 MiB received, 4.56 MiB sent"
                parts = v.replace(",", "").split()
                rx_idx = next((i for i, p in enumerate(parts) if p == "received"), None)
                tx_idx = next((i for i, p in enumerate(parts) if p == "sent"), None)
                if rx_idx is not None and rx_idx >= 2:
                    try:
                        val = float(parts[rx_idx - 2])
                        unit = parts[rx_idx - 1] if rx_idx >= 1 else ""
                        result[current]["rx"] = int(val * (1024**2)) if unit == "MiB" else int(val)
                    except (ValueError, IndexError):
                        pass
                if tx_idx is not None and tx_idx >= 2:
                    try:
                        val = float(parts[tx_idx - 2])
                        unit = parts[tx_idx - 1] if tx_idx >= 1 else ""
                        result[current]["tx"] = int(val * (1024**2)) if unit == "MiB" else int(val)
                    except (ValueError, IndexError):
                        pass
            elif k == "latest handshake":
                result[current]["last_handshake"] = v if v else None
    return result


async def _update_peer_traffic(db_path: Path | None, wg_stats: dict[str, dict]) -> None:
    """Update rx_bytes/tx_bytes and last_handshake in DB from wg show."""
    import aiosqlite
    path = get_db_path(db_path)
    async with aiosqlite.connect(path) as db:
        for pubkey, data in wg_stats.items():
            await db.execute(
                "UPDATE peer_configs SET rx_bytes = ?, tx_bytes = ?, last_handshake = ? WHERE public_key = ?",
                (data["rx"], data["tx"], data["last_handshake"], pubkey),
            )
        await db.commit()


async def collect_daily_stats(interface: str = "wg0", db_path: Path | None = None) -> None:
    """
    Run once per day: refresh peer traffic from `wg show`, then write one row to daily_stats.
    """
    wg_stats = _get_wg_stats(interface)
    await _update_peer_traffic(db_path, wg_stats)

    peers = await list_all_peers(db_path)
    total = len(peers)
    enabled = sum(1 for p in peers if p.is_enabled)
    total_rx = sum(p.rx_bytes for p in peers)
    total_tx = sum(p.tx_bytes for p in peers)

    by_subnet: dict[str, int] = defaultdict(int)
    for p in peers:
        if p.subnet_type == "common":
            by_subnet["common"] += 1
        else:
            key = str(p.subnet_index) if p.subnet_index is not None else "?"
            by_subnet[key] += 1

    today = date.today().isoformat()
    await save_daily_stats(
        date=today,
        total_peers=total,
        enabled_peers=enabled,
        total_rx=total_rx,
        total_tx=total_tx,
        peers_by_subnet=dict(by_subnet),
        db_path=db_path,
    )
