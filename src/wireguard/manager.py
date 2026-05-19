"""
WireGuard config management.
- Common subnet: 10.0.113.0/24 (all peers can reach each other).
- Isolated subnets: 10.0.1.0/24, 10.0.2.0/24, ... (only same subnet).
"""
import random
import subprocess
from pathlib import Path
from typing import Optional

from src.db.models import SUBNET_COMMON, SUBNET_ISOLATED

WG_BIN = "wg"
WG_QUICK_BIN = "wg-quick"

# Reserve .1 in each subnet for gateway if needed; use .2, .3, ...
MIN_HOST = 2
MAX_HOST = 254


def _run(*args: str, capture: bool = True) -> str:
    result = subprocess.run(
        args,
        capture_output=capture,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 and capture:
        raise RuntimeError(f"Command failed: {' '.join(args)}\n{result.stderr}")
    return (result.stdout or "").strip()


def generate_keypair() -> tuple[str, str]:
    """Generate WireGuard private and public key."""
    priv = _run("wg", "genkey")
    # wg pubkey reads from stdin
    proc = subprocess.run(
        ["wg", "pubkey"],
        input=priv,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if proc.returncode != 0:
        raise RuntimeError("Failed to generate public key")
    return priv, proc.stdout.strip()


def get_server_public_key(interface: str = "wg0") -> Optional[str]:
    """Read server public key from running interface."""
    try:
        out = _run(WG_BIN, "show", interface, "public-key")
        return out.strip() if out else None
    except (RuntimeError, FileNotFoundError):
        return None


def get_random_port(min_port: int = 51820, max_port: int = 51850) -> int:
    return random.randint(min_port, max_port)


class WireGuardManager:
    def __init__(
        self,
        interface: str = "wg0",
        config_path: str | Path = "/etc/wireguard/wg0.conf",
        common_subnet: str = "10.0.113.0/24",
        isolated_prefix: str = "10.0",
        isolated_mask: int = 24,
    ):
        self.interface = interface
        self.config_path = Path(config_path)
        self.common_subnet = common_subnet
        self.common_network = common_subnet.split("/")[0]  # 10.0.113.0
        self.isolated_prefix = isolated_prefix
        self.isolated_mask = isolated_mask

    def _parse_config(self) -> tuple[dict, list[dict]]:
        """Return (server_section, list of peer blocks)."""
        if not self.config_path.exists():
            return {}, []
        text = self.config_path.read_text()
        server = {}
        peers = []
        current = None
        current_block = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower() == "[interface]":
                current = "interface"
                current_block = {}
                continue
            if line.lower() == "[peer]":
                if current == "peer":
                    peers.append(current_block)
                current = "peer"
                current_block = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                current_block[k.strip()] = v.strip()
        if current == "peer":
            peers.append(current_block)
        if current == "interface":
            server = current_block
        return server, peers

    def _write_config(self, server: dict, peers: list[dict]) -> None:
        lines = ["[Interface]"]
        for k, v in sorted(server.items()):
            lines.append(f"{k} = {v}")
        for p in peers:
            lines.append("")
            lines.append("[Peer]")
            for k, v in sorted(p.items()):
                lines.append(f"{k} = {v}")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text("\n".join(lines) + "\n")

    def _next_free_address_common(self, used_addresses: set[str]) -> str:
        # 10.0.113.0 -> base 10.0.113, hosts 10.0.113.2, .3, ...
        base = self.common_network.rsplit(".", 1)[0]
        for i in range(MIN_HOST, MAX_HOST + 1):
            addr = f"{base}.{i}/32"
            if addr not in used_addresses:
                return addr
        raise RuntimeError("No free address in common subnet")

    def _next_free_address_isolated(self, subnet_index: int, used_addresses: set[str]) -> str:
        # 10.0.{subnet_index}.0/24 -> 10.0.subnet_index.2, .3, ...
        base = f"{self.isolated_prefix}.{subnet_index}"
        for i in range(MIN_HOST, MAX_HOST + 1):
            addr = f"{base}.{i}/32"
            if addr not in used_addresses:
                return addr
        raise RuntimeError(f"No free address in isolated subnet 10.0.{subnet_index}.0/24")

    def _collect_used_addresses(self, peers: list[dict]) -> set[str]:
        used = set()
        for p in peers:
            if "AllowedIPs" in p:
                # AllowedIPs might be "10.0.113.5/32"
                used.add(p["AllowedIPs"].strip())
        return used

    def add_peer(
        self,
        public_key: str,
        subnet_type: str,
        subnet_index: Optional[int] = None,
        existing_peers_addresses: Optional[list[str]] = None,
    ) -> str:
        """
        Add peer to WireGuard config. Returns assigned address (e.g. 10.0.113.5/32).
        """
        server, peers = self._parse_config()
        used = self._collect_used_addresses(peers)
        if existing_peers_addresses:
            used.update(existing_peers_addresses)

        if subnet_type == SUBNET_COMMON:
            address = self._next_free_address_common(used)
        elif subnet_type == SUBNET_ISOLATED and subnet_index is not None:
            address = self._next_free_address_isolated(subnet_index, used)
        else:
            raise ValueError("subnet_type must be common or isolated with subnet_index")

        peer_block = {
            "PublicKey": public_key,
            "AllowedIPs": address,
        }
        peers.append(peer_block)
        self._write_config(server, peers)
        return address

    def add_peer_with_address(self, public_key: str, address: str) -> None:
        """Add a peer with an address already stored in the database."""
        server, peers = self._parse_config()
        peers = [p for p in peers if p.get("PublicKey") != public_key]
        used = self._collect_used_addresses(peers)
        if address in used:
            raise RuntimeError(f"Address already in WireGuard config: {address}")
        peers.append({"PublicKey": public_key, "AllowedIPs": address})
        self._write_config(server, peers)

    def remove_peer(self, public_key: str) -> bool:
        server, peers = self._parse_config()
        new_peers = [p for p in peers if p.get("PublicKey") != public_key]
        if len(new_peers) == len(peers):
            return False
        self._write_config(server, new_peers)
        return True

    def enable_peer(self, public_key: str) -> bool:
        # In WireGuard, "disable" = remove from config; enable = add back.
        # So we don't have enable/disable in file — we add/remove. Caller stores state in DB.
        return True

    def disable_peer(self, public_key: str) -> bool:
        return self.remove_peer(public_key)

    def reload_wg(self) -> None:
        """Reload WireGuard (wg syncconf or restart interface)."""
        _run(WG_BIN, "syncconf", self.interface, str(self.config_path))

    def ensure_server_config(
        self,
        port: int,
        server_private_key_path: Optional[Path] = None,
    ) -> dict:
        """
        Ensure [Interface] has ListenPort and PrivateKey. Returns server section.
        """
        server, peers = self._parse_config()
        if "ListenPort" not in server:
            server["ListenPort"] = str(port)
        if "PrivateKey" not in server and server_private_key_path and server_private_key_path.exists():
            server["PrivateKey"] = server_private_key_path.read_text().strip()
        self._write_config(server, peers)
        return server
