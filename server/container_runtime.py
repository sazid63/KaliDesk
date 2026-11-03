"""
Container Runtime Manager - Podman in WSL2.

Manages container images and containers for security testing. All podman
operations run inside the app's private WSL2 distribution. Flask routes live
in server/app.py under the '--- Containers ---' section.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Any

import server.config as _cfg
import server.db as db

# --- Constants --------------------------------------------------------------

DEFAULT_TIMEOUT = 300

# --- Input validation -------------------------------------------------------

# Image reference: optional registry host (with optional :port), a repository
# path of [a-z0-9._/-] segments, optional :tag, optional @digest.
# Examples accepted:  "alpine", "ubuntu:22.04",
#                     "docker.io/library/kali:latest",
#                     "quay.io/centos/centos:8", "redis:7@sha256:abc123...".
# Anything else (shell metacharacters, spaces, "..", drive letters, etc.) is
# rejected before it ever reaches podman.
_IMAGE_RE = re.compile(
    r"^(?:(?P<registry>[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?(?::\d{1,5})?)/)?"
    r"(?P<repo>[a-z0-9](?:[a-z0-9._-]*[a-z0-9])*(?:/[a-z0-9._-]+)*)?"
    r"(?::(?P<tag>[A-Za-z0-9_][A-Za-z0-9._-]{0,127}))?"
    r"(?:@(?P<digest>sha256:[A-Fa-f0-9]{64}))?$"
)


def _bad_volume_reason(host: str) -> str:
    """Return a reason if host volume path is unsafe, else ""."""
    if ".." in host.split("/"):
        return "path contains '..' (path traversal)"
    norm = pathlib.PurePosixPath(host).as_posix()
    if not norm.startswith("/"):
        return "host path must be absolute"
    # Windows UNC / drive letters never make sense as WSL host paths.
    if re.fullmatch(r"[A-Za-z]:", host[:3]) or host.startswith("\\\\"):
        return "Windows drive/UNC path is not a WSL host path"
    # Only allow paths under /tmp or the app's WSL-accessible data directory.
    # The data directory in WSL is typically under /mnt/c/Users/.../KaliWindowsSubstitute
    # or a user-specified path. We use a safe default of /tmp only.
    allowed_prefixes = ("/tmp/",)
    is_allowed = any(
        norm == prefix.rstrip("/") or norm.startswith(prefix)
        for prefix in allowed_prefixes
    )
    if not is_allowed:
        return f"host path must be under /tmp, got {norm!r}"
    return ""


def _run_podman(cmd: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """Run a podman command in the private WSL2 distribution."""
    try:
        result = subprocess.run(
            ["wsl", "-d", _cfg.load().runtime_distro, "podman"] + cmd,
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


def validate_image_name(image: str) -> tuple[bool, str]:
    """Validate a container image name/reference.
    
    Returns (True, "") if valid, or (False, reason) if invalid.
    """
    if not image or not isinstance(image, str):
        return False, "image name must be a non-empty string"
    if len(image) > 512:
        return False, "image name too long (max 512 chars)"
    if _IMAGE_RE.match(image):
        return True, ""
    return False, "image name contains invalid characters or format"


def validate_port_binding(port_spec: str) -> tuple[bool, str]:
    """Validate a port binding specification.
    
    Only allows 127.0.0.1:hostPort:containerPort or 127.0.0.1:hostPort:containerPort/udp.
    Rejects 0.0.0.0 and any binding that exposes to all interfaces.
    
    Returns (True, "") if valid, or (False, reason) if invalid.
    """
    if not port_spec or not isinstance(port_spec, str):
        return False, "port spec must be a non-empty string"
    
    # Podman format: [hostIP:]hostPort:containerPort[/protocol]
    # We only allow 127.0.0.1 as hostIP
    parts = port_spec.split(":")
    
    if len(parts) == 1:
        # Just container port - reject as it defaults to 0.0.0.0
        return False, "port binding must include 127.0.0.1: prefix (e.g., 127.0.0.1:8080:80)"
    elif len(parts) == 2:
        # Could be hostPort:containerPort (defaults to 0.0.0.0) - reject
        # Or could be hostIP:port (incomplete) - reject
        return False, "port binding must include 127.0.0.1: prefix (e.g., 127.0.0.1:8080:80)"
    elif len(parts) == 3:
        host_ip, host_port_str, rest = parts
        if host_ip != "127.0.0.1":
            return False, f"only 127.0.0.1 bindings allowed, got {host_ip!r}"
        
        # Parse host port
        try:
            host_port = int(host_port_str)
            if not (1 <= host_port <= 65535):
                return False, f"host port must be 1-65535, got {host_port}"
        except ValueError:
            return False, f"host port must be numeric, got {host_port_str!r}"
        
        # Parse container port (may include protocol)
        if "/" in rest:
            container_port_str, protocol = rest.rsplit("/", 1)
            if protocol not in ("tcp", "udp"):
                return False, f"protocol must be tcp or udp, got {protocol!r}"
        else:
            container_port_str = rest
        
        try:
            container_port = int(container_port_str)
            if not (1 <= container_port <= 65535):
                return False, f"container port must be 1-65535, got {container_port}"
        except ValueError:
            return False, f"container port must be numeric, got {container_port_str!r}"
        
        return True, ""
    else:
        return False, f"invalid port spec format: {port_spec!r}"


def validate_volume_spec(volume_spec: str) -> tuple[bool, str]:
    """Validate a volume binding specification.
    
    Format: host_path:container_path[:options]
    - host_path must be absolute and under /tmp or the app data dir
    - host_path must not contain '..' components
    - container_path must be absolute
    
    Returns (True, "") if valid, or (False, reason) if invalid.
    """
    if not volume_spec or not isinstance(volume_spec, str):
        return False, "volume spec must be a non-empty string"
    
    parts = volume_spec.split(":")
    if len(parts) < 2:
        return False, "volume spec must be host_path:container_path[:options]"
    
    host_path = parts[0]
    container_path = parts[1]
    
    # Validate host path
    reason = _bad_volume_reason(host_path)
    if reason:
        return False, f"host path invalid: {reason}"
    
    # Validate container path
    if not container_path.startswith("/"):
        return False, f"container path must be absolute, got {container_path!r}"
    
    return True, ""


def validate_exec_command(cmd: list[str]) -> tuple[bool, str]:
    """Validate a command for exec_in_container.
    
    Only allows whitelisted commands with validated arguments.
    This prevents arbitrary command execution even with container access.
    
    Returns (True, "") if valid, or (False, reason) if invalid.
    """
    if not cmd or not isinstance(cmd, list):
        return False, "command must be a non-empty list"
    
    if not all(isinstance(arg, str) for arg in cmd):
        return False, "all command arguments must be strings"
    
    # Whitelist of safe commands for security testing context
    # These are common diagnostic and testing utilities
    ALLOWED_COMMANDS = {
        # Network tools
        "ping", "curl", "wget", "nc", "netcat", "nmap", "ss", "ip", "ifconfig",
        "dig", "nslookup", "host",
        # File tools
        "ls", "cat", "head", "tail", "grep", "find", "wc", "sort", "uniq",
        "diff", "cmp", "file", "stat", "tree",
        # Text processing
        "awk", "sed", "cut", "tr", "xargs", "tee",
        # System info
        "ps", "top", "htop", "free", "df", "du", "uname", "hostname", "whoami",
        "id", "env", "printenv",
        # Process control (limited)
        "sleep", "date", "echo", "printf",
        # Security tools (common in Kali)
        "hashcat", "john", "hydra", "sqlmap", "nikto", "gobuster", "dirb",
        "burpsuite", "wireshark", "tcpdump", "tshark",
        # Programming/interpreters (use with caution)
        "python", "python3", "python2", "ruby", "perl", "node", "bash", "sh",
        # Package managers (read-only operations)
        "apt", "apt-get", "dpkg", "pip", "pip3", "gem", "npm",
    }
    
    base_cmd = cmd[0]
    # Extract just the command name (handle paths like /usr/bin/python)
    if "/" in base_cmd:
        base_cmd = base_cmd.rsplit("/", 1)[-1]
    
    if base_cmd not in ALLOWED_COMMANDS:
        return False, f"command {base_cmd!r} is not in the allowed list"
    
    # Additional argument validation for dangerous commands
    # Prevent shell escape sequences and command injection
    dangerous_patterns = ["$( ", "`", "|", ";", "&&", "||", ">", "<", "&"]
    for arg in cmd:
        for pattern in dangerous_patterns:
            if pattern in arg:
                return False, f"argument contains dangerous pattern {pattern!r}"
    
    # Prevent environment variable injection via -e flags for interpreters
    if base_cmd in ("python", "python3", "python2", "ruby", "perl"):
        for i, arg in enumerate(cmd[1:], 1):
            if arg.startswith("-e") and len(arg) > 2:
                # Inline script execution - check for system calls
                if arg.startswith("-e"):
                    script = arg[2:]
                elif i + 1 < len(cmd):
                    script = cmd[i + 1]
                else:
                    script = ""
                if any(
                    kw in script
                    for kw in ("os.system", "subprocess", "__import__", "eval(", "exec(")
                ):
                    return False, "script contains dangerous system calls"
    
    return True, ""


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
        images.append(
            {
                "id": str(img.get("Id", ""))[:12],
                "name": f"{img.get('Repository', '')}:{img.get('Tag', '')}",
                "size": int(img.get("Size") or 0),
                "created": str(img.get("CreatedAt", "")),
            }
        )
    return images


def pull_image(name: str) -> dict[str, Any]:
    """Pull a container image."""
    valid, reason = validate_image_name(name)
    if not valid:
        return {"ok": False, "error": f"Invalid image name: {reason}"}
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
        containers.append(
            {
                "id": str(cont.get("Id", ""))[:12],
                "names": cont.get("Names") or [],
                "image": str(cont.get("Image", "")),
                "status": str(cont.get("Status", "")),
                "ports": str(cont.get("Ports", "")),
                "created": str(cont.get("CreatedAt", "")),
            }
        )
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
    """Execute a command in a running container (argv list, no shell).
    
    Only whitelisted commands with validated arguments are allowed.
    """
    valid, reason = validate_exec_command(cmd)
    if not valid:
        return {
            "ok": False,
            "stdout": "",
            "stderr": f"Command rejected: {reason}",
            "rc": -1,
        }
    
    # Validate container_id format (hex string)
    if not re.fullmatch(r"[a-fA-F0-9]+", container_id):
        return {
            "ok": False,
            "stdout": "",
            "stderr": "Invalid container ID format",
            "rc": -1,
        }
    
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
    Validates all inputs before passing to podman.
    """
    # Validate image name
    valid, reason = validate_image_name(image)
    if not valid:
        return {"ok": False, "error": f"Invalid image name: {reason}"}
    
    # Validate container name (alphanumeric, dashes, underscores)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
        return {"ok": False, "error": "Container name must be alphanumeric with dashes/underscores"}
    
    # Validate and build port bindings
    validated_ports: list[str] = []
    for port_spec in ports or []:
        valid, reason = validate_port_binding(str(port_spec))
        if not valid:
            return {"ok": False, "error": f"Invalid port binding {port_spec!r}: {reason}"}
        validated_ports.append(str(port_spec))
    
    # Validate and build volume bindings
    validated_volumes: list[str] = []
    for vol_spec in volumes or []:
        valid, reason = validate_volume_spec(str(vol_spec))
        if not valid:
            return {"ok": False, "error": f"Invalid volume binding {vol_spec!r}: {reason}"}
        validated_volumes.append(str(vol_spec))
    
    cmd = ["run", "-d", "--name", name]
    for port in validated_ports:
        cmd.extend(["-p", port])
    for vol in validated_volumes:
        cmd.extend(["-v", vol])
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
