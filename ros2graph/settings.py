"""Startup parameters shared by the ROS entry point and HTTP server."""
from dataclasses import dataclass
import math
from pathlib import Path


DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8080,
    "refresh_s": 2.0,
    "watch_enabled": True,
    "watch_max_topics": 256,
    "watch_max_clients": 8,
    "watch_lease_s": 12.0,
    "watch_messages_per_window": 10000,
    "rpc_trace_socket": "",
    "token_file": "",
    "tls_cert": "",
    "tls_key": "",
}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8080
    refresh_s: float = 2.0
    watch_enabled: bool = True
    watch_max_topics: int = 256
    watch_max_clients: int = 8
    watch_lease_s: float = 12.0
    watch_messages_per_window: int = 10000
    rpc_trace_socket: str = ""
    token_file: str = ""
    tls_cert: str = ""
    tls_key: str = ""

    def __post_init__(self):
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("host must be a nonempty address")
        for key, low, high in (("port", 1, 65535), ("watch_max_topics", 1, 100000),
                               ("watch_max_clients", 1, 8),
                               ("watch_messages_per_window", 1, 50000)):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{key} must be an integer between {low} and {high}")
        for key, low, high in (("refresh_s", .2, 30.), ("watch_lease_s", 3., 30.)):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} must be between {low} and {high}")
        if not isinstance(self.watch_enabled, bool):
            raise ValueError("watch_enabled must be boolean")
        for key in ("rpc_trace_socket", "token_file", "tls_cert", "tls_key"):
            if not isinstance(getattr(self, key), str):
                raise ValueError(f"{key} must be a string path")
        if bool(self.tls_cert) != bool(self.tls_key):
            raise ValueError("tls_cert and tls_key must be supplied together")

    def observer_config(self):
        return {
            "refresh_s": self.refresh_s,
            "watch": {
                "enabled": self.watch_enabled,
                "max_topics": self.watch_max_topics,
                "max_clients": self.watch_max_clients,
                "lease_s": self.watch_lease_s,
                "max_messages_per_window": self.watch_messages_per_window,
            },
        }

    def read_token(self):
        if not self.token_file:
            return None
        token = Path(self.token_file).expanduser().read_text(encoding="utf-8").strip()
        if not token or len(token) > 4096 or any(c.isspace() for c in token):
            raise ValueError("token_file must contain one nonempty token, at most 4096 characters")
        return token
