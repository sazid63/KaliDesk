"""Runtime configuration.

The app needs none of this to start. Every value has a safe default and can be
overridden with an environment variable for development or packaging.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# SINGLE SOURCE OF TRUTH for private network ranges
# Includes IPv4 RFC 1918, loopback, link-local, and IPv6 equivalents
PRIVATE_RANGES: tuple[str, ...] = (
    "127.0.0.0/8",      # IPv4 loopback
    "10.0.0.0/8",       # RFC 1918 private
    "172.16.0.0/12",    # RFC 1918 private
    "192.168.0.0/16",   # RFC 1918 private
    "169.254.0.0/16",   # IPv4 link-local (APIPA)
    "::1/128",          # IPv6 loopback
    "fc00::/7",         # IPv6 unique local (ULA)
    "fe80::/10",        # IPv6 link-local
)

@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8788
    agent_url: str = "http://127.0.0.1:5055"
    runtime_distro: str = "KaliSubstitute"
    rootfs_url: str = ""
    rootfs_sha256: str = ""
    private_ranges: tuple[str, ...] = PRIVATE_RANGES


def load() -> Config:
    return Config(
        port=int(os.environ.get("KWS_PORT", "8788")),
        agent_url=os.environ.get("KWS_AGENT_URL", "http://127.0.0.1:5055"),
        runtime_distro=os.environ.get("KWS_DISTRO", "KaliSubstitute"),
        rootfs_url=os.environ.get("KWS_ROOTFS_URL", ""),
        rootfs_sha256=os.environ.get("KWS_ROOTFS_SHA256", ""),
    )
