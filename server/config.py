"""Runtime configuration.

The app needs none of this to start. Every value has a safe default and can be
overridden with an environment variable for development or packaging.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    host: str = "127.0.0.1"
    port: int = 8788
    agent_url: str = "http://127.0.0.1:5055"
    runtime_distro: str = "KaliSubstitute"
    rootfs_url: str = ""
    rootfs_sha256: str = ""
    # Ranges that are treated as "authorised by default". Everything else
    # requires an explicit, logged confirmation from the user.
    private_ranges: tuple[str, ...] = (
        "127.0.0.0/8",
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",
    )


def load() -> Config:
    return Config(
        port=int(os.environ.get("KWS_PORT", "8788")),
        agent_url=os.environ.get("KWS_AGENT_URL", "http://127.0.0.1:5055"),
        runtime_distro=os.environ.get("KWS_DISTRO", "KaliSubstitute"),
        rootfs_url=os.environ.get("KWS_ROOTFS_URL", ""),
        rootfs_sha256=os.environ.get("KWS_ROOTFS_SHA256", ""),
    )
