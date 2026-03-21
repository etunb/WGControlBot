"""SQLite models: users, peer configs, daily stats."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Subnet types
SUBNET_COMMON = "common"   # 10.0.113.0/24
SUBNET_ISOLATED = "isolated"  # 10.0.i.0/24


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    is_admin: bool
    is_active: bool
    isolated_subnet_index: Optional[int] = None
    created_at: str = ""


@dataclass
class PeerConfig:
    id: int
    user_id: int
    name: str
    subnet_type: str   # common | isolated
    subnet_index: Optional[int]  # for isolated: 1, 2, 3, ...
    address: str       # e.g. 10.0.113.5/32 or 10.0.2.3/32
    private_key: str
    public_key: str
    is_enabled: bool
    created_at: str
    last_handshake: Optional[str] = None
    rx_bytes: int = 0
    tx_bytes: int = 0


@dataclass
class DailyStats:
    id: int
    date: str  # YYYY-MM-DD
    total_peers: int
    enabled_peers: int
    total_rx_bytes: int
    total_tx_bytes: int
    peers_by_subnet: str  # JSON: {"common": N, "1": N, "2": N, ...}
