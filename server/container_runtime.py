"""Container runtime manager: Podman inside the app's private WSL2 distribution.

Every podman call goes through ``app.runtime.in_distro`` (argv list, ``wsl -d
<our distro>``, no shell), so it shares the one wsl.exe wrapper that hides console
windows and decodes output correctly. Everything a user types is validated here
before it reaches podman.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import PurePosixPath
from typing import Any

import kws.paths as kws_paths
import server.config as _cfg

DEFAULT_TIMEOUT = 300

# --- Input validation -------------------------------------------------------

# [registry[:port]/]repo[/more][:tag][@sha256:digest]. Written without nested
# quantifiers so a hostile string cannot make the matcher take exponential time.
_NAME = r"[a-z0-9][a-z0-9._-]*"
_IMAGE_RE = re.compile(
    rf"^(?:{_NAME}(?::\d{{1,5}})?/)?{_NAME}(?:/{_NAME})*"
    r"(?::[A-Za-z0-9_][A-Za-z0-9._-]{0,127})?"
    r"(?:@sha256:[A-Fa-f0-9]{64})?$"
)
_CONTAINER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_image_name(image: str) -> tuple[bool, str]:
    """Return (True, "") for a plausible image reference, else (False, reason)."""
    if not image or not isinstance(image, str):
        return False, "image name must be a non-empty string"
    if len(image) > 256:
        return False, "image name too long (max 256 chars)"
    if _IMAGE_RE.match(image):
        return True, ""
    return False, "image name contains invalid characters or format"


def validate_container_ref(ref: str) -> tuple[bool, str]:
    """A container id (hex) or name. Never starts with '-', so it cannot be an option."""
    if not isinstance(ref, str) or not _CONTAINER_RE.match(ref):
        return False, "invalid container id or name"
    return True, ""


def normalize_port_binding(port_spec: str) -> tuple[str, str]:
    """Return (binding, error). ``8080:80`` and ``127.0.0.1:8080:80`` are both accepted and
    always bound to loopback only, so a container is never exposed to the network."""
    if not port_spec or not isinstance(port_spec, str):
        return "", "port spec must be a non-empty string"
    parts = port_spec.strip().split(":")
    if len(parts) == 2:
        parts = ["127.0.0.1", *parts]
    if len(parts) != 3:
        return "", "use hostPort:containerPort, e.g. 8080:80"
    host_ip, host_port, rest = parts
    if host_ip != "127.0.0.1":
        return "", f"only 127.0.0.1 bindings are allowed, got {host_ip!r}"
    container_port, _, protocol = rest.partition("/")
    if protocol and protocol not in ("tcp", "udp"):
        return "", f"protocol must be tcp or udp, got {protocol!r}"
    for label, value in (("host", host_port), ("container", container_port)):
        if not value.isdigit() or not 1 <= int(value) <= 65535:
            return "", f"{label} port must be a number from 1 to 65535"
    return f"127.0.0.1:{host_port}:{rest}", ""


def allowed_volume_roots() -> list[str]:
    """WSL paths a container may mount: /tmp and the app's own evidence/work folders."""
    return [
        "/tmp",
        kws_paths.to_wsl_path(kws_paths.evidence_dir()),
        kws_paths.to_wsl_path(kws_paths.work_dir()),
    ]


def validate_volume_spec(volume_spec: str) -> tuple[bool, str]:
    """``host_path:container_path[:ro|rw]`` with the host path inside an allowed root."""
    if not volume_spec or not isinstance(volume_spec, str):
        return False, "volume spec must be a non-empty string"
    parts = volume_spec.split(":")
    if len(parts) not in (2, 3):
        return False, "volume spec must be host_path:container_path[:ro]"
    host_path, container_path = parts[0], parts[1]
    if len(parts) == 3 and parts[2] not in ("ro", "rw"):
        return False, "volume option must be ro or rw"
    if ".." in host_path.split("/") or ".." in container_path.split("/"):
        return False, "paths may not contain '..'"
    if not host_path.startswith("/"):
        return False, "host path must be an absolute WSL path (e.g. /tmp/data)"
    norm = PurePosixPath(host_path).as_posix()
    roots = allowed_volume_roots()
    if not any(norm == root or norm.startswith(root.rstrip("/") + "/") for root in roots):
        return False, "host path must be under /tmp or the app's evidence or work folder"
    if not container_path.startswith("/"):
        return False, f"container path must be absolute, got {container_path!r}"
    return True, ""


# Diagnostic commands only. Shells, interpreters, and tools that can run other commands
# (find -exec, xargs, awk system(), env, package managers) are deliberately absent.
ALLOWED_EXEC = {
    "ping", "curl", "wget", "nc", "nmap", "ss", "ip", "dig", "nslookup", "host",
    "ls", "cat", "head", "tail", "grep", "wc", "sort", "uniq", "diff", "file", "stat",
    "ps", "df", "du", "uname", "hostname", "whoami", "id", "date", "echo", "sleep",
    "hashcat", "john", "hydra", "sqlmap", "nikto", "gobuster", "dirb", "tcpdump", "tshark",
}
_SHELL_CHARS = ("`", "$(", "|", ";", "&", ">", "<", "\n", "\r", "\x00")


def validate_exec_command(cmd: list[str]) -> tuple[bool, str]:
    if not cmd or not isinstance(cmd, list) or not all(isinstance(a, str) for a in cmd):
        return False, "command must be a non-empty list of strings"
    program = cmd[0].rsplit("/", 1)[-1]
    if program not in ALLOWED_EXEC:
        return False, f"command {program!r} is not in the allowed list"
    for arg in cmd:
        if any(ch in arg for ch in _SHELL_CHARS):
            return False, "argument contains a shell metacharacter"
    return True, ""


# --- Podman plumbing ----------------------------------------------------------


def _podman(args: list[str], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    from app import runtime

    cfg = _cfg.load()
    rc, out, err = runtime.in_distro(cfg, ["podman", *args], timeout=timeout)
    return {"ok": rc == 0, "stdout": out, "stderr": err, "rc": rc}


def _json_rows(text: str) -> list[dict[str, Any]]:
    """Podman prints one JSON array; some versions print one object per line."""
    text = text.strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        rows = data if isinstance(data, list) else [data]
    except json.JSONDecodeError:
        rows = []
        for line in text.splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return [row for row in rows if isinstance(row, dict)]


def is_podman_installed() -> bool:
    return _podman(["--version"], timeout=20)["ok"]


def install_podman() -> dict[str, Any]:
    """Install podman with apt inside the distro."""
    from app import runtime

    if is_podman_installed():
        return {"ok": True, "message": "Podman already installed"}
    cfg = _cfg.load()
    env = ["env", "DEBIAN_FRONTEND=noninteractive"]
    rc, out, err = runtime.in_distro(cfg, [*env, "apt-get", "update", "-qq"], timeout=300)
    if rc != 0:
        return {"ok": False, "error": "Failed to update apt", "detail": err or out}
    rc, out, err = runtime.in_distro(
        cfg, [*env, "apt-get", "install", "-y", "--no-install-recommends", "podman"], timeout=1200
    )
    if rc == 0:
        return {"ok": True, "message": "Podman installed successfully"}
    return {"ok": False, "error": "Failed to install podman", "detail": err or out}


def list_images() -> list[dict[str, Any]]:
    result = _podman(["images", "--format", "json"], timeout=30)
    if not result["ok"]:
        return []
    images = []
    for img in _json_rows(result["stdout"]):
        names = img.get("Names") or []
        name = names[0] if names else f"{img.get('Repository', '')}:{img.get('Tag', '')}"
        images.append({
            "id": str(img.get("Id", ""))[:12],
            "name": name,
            "size": int(img.get("Size") or 0),
            "created": str(img.get("CreatedAt") or img.get("Created") or ""),
        })
    return images


def list_containers(all: bool = False) -> list[dict[str, Any]]:  # noqa: A002
    args = ["ps", "-a"] if all else ["ps"]
    result = _podman([*args, "--format", "json"], timeout=30)
    if not result["ok"]:
        return []
    containers = []
    for cont in _json_rows(result["stdout"]):
        ports = cont.get("Ports") or ""
        if isinstance(ports, list):
            ports = ", ".join(
                f"{p.get('host_ip') or ''}:{p.get('host_port')}->{p.get('container_port')}"
                for p in ports if isinstance(p, dict)
            )
        containers.append({
            "id": str(cont.get("Id", ""))[:12],
            "names": cont.get("Names") or [],
            "image": str(cont.get("Image", "")),
            "status": str(cont.get("Status") or cont.get("State") or ""),
            "ports": str(ports),
            "created": str(cont.get("CreatedAt") or cont.get("Created") or ""),
        })
    return containers


def status() -> dict[str, Any]:
    """One call for the panel: skips the list calls when podman is not installed."""
    if not is_podman_installed():
        return {"podman_installed": False, "images": [], "containers": []}
    return {
        "podman_installed": True,
        "images": list_images(),
        "containers": list_containers(all=True),
    }


def pull_image(name: str) -> dict[str, Any]:
    valid, reason = validate_image_name(name)
    if not valid:
        return {"ok": False, "error": f"Invalid image name: {reason}"}
    result = _podman(["pull", name], timeout=900)
    if result["ok"]:
        return {"ok": True, "message": f"Image {name} pulled successfully"}
    return {"ok": False, "error": f"Failed to pull image {name}", "detail": result["stderr"]}


def _by_ref(verb: str, args: list[str], container_id: str, ok_msg: str, timeout: int = 60):
    valid, reason = validate_container_ref(container_id)
    if not valid:
        return {"ok": False, "error": reason}
    result = _podman([verb, *args, container_id], timeout=timeout)
    if result["ok"]:
        return {"ok": True, "message": ok_msg.format(id=container_id)}
    return {
        "ok": False,
        "error": f"Failed to {verb} {container_id}",
        "detail": result["stderr"],
    }


def start_container(container_id: str) -> dict[str, Any]:
    return _by_ref("start", [], container_id, "Container {id} started")


def stop_container(container_id: str, timeout: int = 10) -> dict[str, Any]:
    return _by_ref("stop", ["--time", str(int(timeout))], container_id, "Container {id} stopped")


def remove_container(container_id: str, force: bool = False) -> dict[str, Any]:
    return _by_ref("rm", ["-f"] if force else [], container_id, "Container {id} removed")


def get_container_logs(container_id: str, tail: int = 100) -> dict[str, Any]:
    valid, reason = validate_container_ref(container_id)
    if not valid:
        return {"ok": False, "error": reason}
    tail = max(1, min(int(tail), 2000))
    result = _podman(["logs", "--tail", str(tail), container_id], timeout=30)
    if result["ok"]:
        return {"ok": True, "logs": result["stdout"] + result["stderr"]}
    return {
        "ok": False,
        "error": f"Failed to get logs for {container_id}",
        "detail": result["stderr"],
    }


def exec_in_container(container_id: str, cmd: list[str]) -> dict[str, Any]:
    """Run an allow-listed diagnostic command inside a running container (argv, no shell)."""
    valid, reason = validate_container_ref(container_id)
    if not valid:
        return {"ok": False, "stdout": "", "stderr": reason, "rc": -1}
    valid, reason = validate_exec_command(cmd)
    if not valid:
        return {"ok": False, "stdout": "", "stderr": f"Command rejected: {reason}", "rc": -1}
    result = _podman(["exec", container_id, *cmd], timeout=120)
    return {k: result[k] for k in ("ok", "stdout", "stderr", "rc")}


MAX_COMMAND_ARGS = 32


def _container_state(container_id: str, wait: float = 1.5) -> tuple[str, int | None]:
    """The container's state and exit code, after a short wait so a quick exit is seen."""
    if not container_id:
        return "unknown", None
    deadline = time.monotonic() + wait
    state, code = "unknown", None
    while True:
        fmt = "{{.State.Status}} {{.State.ExitCode}}"
        result = _podman(["inspect", "--format", fmt, container_id], timeout=20)
        if result["ok"]:
            parts = result["stdout"].split()
            if parts:
                state = parts[0]
                code = int(parts[1]) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else None
        if state != "running" or time.monotonic() >= deadline:
            return state, code
        time.sleep(0.3)


def run_container(
    image: str,
    name: str,
    ports: list[str] | None = None,
    volumes: list[str] | None = None,
    command: list[str] | None = None,
) -> dict[str, Any]:
    """Run a detached container. Never privileged; ports bind to loopback only.

    ``command`` is passed to the container as argv (no shell). Without one, the image's own
    default command runs, which for many images exits at once.
    """
    valid, reason = validate_image_name(image)
    if not valid:
        return {"ok": False, "error": f"Invalid image name: {reason}"}
    if not isinstance(name, str) or not _CONTAINER_RE.match(name):
        return {"ok": False, "error": "Container name may use letters, digits, . _ - only"}

    args = ["run", "-d", "--name", name, "--security-opt", "no-new-privileges"]
    for spec in ports or []:
        binding, error = normalize_port_binding(str(spec))
        if error:
            return {"ok": False, "error": f"Invalid port binding {spec!r}: {error}"}
        args += ["-p", binding]
    for spec in volumes or []:
        valid, reason = validate_volume_spec(str(spec))
        if not valid:
            return {"ok": False, "error": f"Invalid volume {spec!r}: {reason}"}
        args += ["-v", str(spec)]
    if command:
        if len(command) > MAX_COMMAND_ARGS or not all(
            isinstance(a, str) and len(a) <= 1024 and "\x00" not in a for a in command
        ):
            return {"ok": False, "error": f"The command may have at most {MAX_COMMAND_ARGS} parts"}
    args.append(image)
    args.extend(command or [])

    result = _podman(args, timeout=300)
    if result["ok"]:
        container_id = result["stdout"].strip()
        state, exit_code = _container_state(container_id)
        if state == "exited" and exit_code == 0:
            message = f"Container {name} ran and exited with code 0"
        elif state == "exited":
            message = f"Container {name} exited with code {exit_code}. Use Logs to see why."
        else:
            message = f"Container {name} started"
        return {
            "ok": True,
            "message": message,
            "container_id": container_id[:12] if container_id else None,
            "state": state,
            "exit_code": exit_code,
        }
    return {"ok": False, "error": f"Failed to run container {name}", "detail": result["stderr"]}
