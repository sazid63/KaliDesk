"""
Container Runtime Manager - Podman in WSL2.

Manages container images and containers for security testing. All podman
operations run inside the app's private WSL2 distribution. Flask routes live
in server/app.py under the '--- Containers ---' section.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import server.db as db

# --- Constants --------------------------------------------------------------

DEFAULT_TIMEOUT = 300


def _run_podman(cmd: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a podman command in the private WSL2 distribution."""
    try:
        result = subprocess.run(
            ["wsl", "-d", "KaliSubstitute", "podman"] + cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "rc": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "Command timed out", "rc": -1}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "stdout": "", "stderr": str(exc), "rc": -1}


# --- Podman operations ------------------------------------------------------

def is_podman_installed() -> bool:
    """Check whether podman is installed in the WSL2 distribution."""
    return _run_podman(["--version"], timeout=10)["ok"]


def install_podman() -> dict[str, Any]:
    """Install podman in the WSL2 distribution (apt)."""
    if is_podman_installed():
        return {"ok": True, "message": "Podman already installed"}
    result = _run_podman(["apt-get", "update"], timeout=120)
    if not result["ok"]:
        return {"ok": False, "error": "Failed to update apt", "detail": result["stderr"]}
    result = _run_podman(["apt-get", "install", "-y", "podman"], timeout=600)
    if result["ok"]:
        return {"ok": True, "message": "Podman installed successfully"}
    return {"ok": False, "error": "Failed to install podman", "detail": result["stderr"]}


def list_images() -> list[dict[str, Any]]:
    """List all container images."""
    result = _run_podman(["images", "--format", "json"], timeout=30)
    if not result["ok"]:
        return []
    images: list[dict[str, Any]] = []
    for line in result["stdout"].strip().splitlines():
        if not line.strip():
            continue
        try:
            img = json.loads(line)
        except json.JSONDecodeError:
            continue
        images.append({
            "id": str(img.get("Id", ""))[:12],
            "name": f'{img.get("Repository", "")}:{img.get("Tag", "")}',
            "size": int(img.get("Size") or 0),
            "created": str(img.get("CreatedAt", "")),
        })
    return images


def pull_image(name: str) -> dict[str, Any]:
    """Pull a container image."""
    result = _run_podman(["pull", name], timeout=900)
    if result["ok"]:
        return {"ok": True, "message": f"Image {name} pulled successfully"}
    return {"ok": False, "error": f"Failed to pull image {name}", "detail": result["stderr"]}


def list_containers(all: bool = False) -> list[dict[str, Any]]:
    """List containers (all=True includes stopped ones)."""
    cmd = ["ps", "-a"] if all else ["ps"]
    result = _run_podman(cmd + ["--format", "json"], timeout=30)
    if not result["ok"]:
        return []
    containers: list[dict[str, Any]] = []
    for line in result["stdout"].strip().splitlines():
        if not line.strip():
            continue
        try:
            cont = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append({
            "id": str(cont.get("Id", ""))[:12],
            "names": cont.get("Names") or [],
            "image": str(cont.get("Image", "")),
            "status": str(cont.get("Status", "")),
            "ports": str(cont.get("Ports", "")),
            "created": str(cont.get("CreatedAt", "")),
        })
    return containers


def start_container(container_id: str) -> dict[str, Any]:
    """Start a container."""
    result = _run_podman(["start", container_id], timeout=60)
    if result["ok"]:
        return {"ok": True, "message": f"Container {container_id} started"}
    return {"ok": False, "error": f"Failed to start {container_id}", "detail": result["stderr"]}


def stop_container(container_id: str, timeout: int = 10) -> dict[str, Any]:
    """Stop a container."""
    result = _run_podman(["stop", "--time", str(timeout), container_id], timeout=60)
    if result["ok"]:
        return {"ok": True, "message": f"Container {container_id} stopped"}
    return {"ok": False, "error": f"Failed to stop {container_id}", "detail": result["stderr"]}


def remove_container(container_id: str, force: bool = False) -> dict[str, Any]:
    """Remove a container."""
    cmd = ["rm"]
    if force:
        cmd.append("-f")
    cmd.append(container_id)
    result = _run_podman(cmd, timeout=60)
    if result["ok"]:
        return {"ok": True, "message": f"Container {container_id} removed"}
    return {"ok": False, "error": f"Failed to remove {container_id}", "detail": result["stderr"]}


def get_container_logs(container_id: str, tail: int = 100) -> dict[str, Any]:
    """Get container logs."""
    result = _run_podman(["logs", "--tail", str(tail), container_id], timeout=30)
    if result["ok"]:
        return {"ok": True, "logs": result["stdout"]}
    err = f"Failed to get logs for {container_id}"
    return {"ok": False, "error": err, "detail": result["stderr"]}


def exec_in_container(container_id: str, cmd: list[str]) -> dict[str, Any]:
    """Execute a command in a running container (argv list, no shell)."""
    result = _run_podman(["exec", container_id] + cmd, timeout=120)
    return {
        "ok": result["ok"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "rc": result["rc"],
    }


def run_container(
    image: str,
    name: str,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
) -> dict[str, Any]:
    """Run a new detached container.

    Never adds --privileged; the UI only exposes ports and volumes.
    """
    cmd = ["run", "-d", "--name", name]
    for port in ports or []:
        cmd.extend(["-p", str(port)])
    for vol in volumes or []:
        cmd.extend(["-v", str(vol)])
    cmd.append(image)

    result = _run_podman(cmd, timeout=120)
    if result["ok"]:
        container_id = result["stdout"].strip()
        return {
            "ok": True,
            "message": f"Container {name} started",
            "container_id": container_id[:12] if container_id else None,
        }
    return {"ok": False, "error": f"Failed to run container {name}", "detail": result["stderr"]}


# --- Audit helpers ----------------------------------------------------------

def audit_container_action(action: str, container_id: str, details: str = "") -> None:
    """Record a container action in the local audit log."""
    db.audit("user", f"container:{action}", container_id, details)
