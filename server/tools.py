"""Run tools through the in-runtime agent, and manage installed tools.

The agent lives inside the app's private WSL2 distribution and is the only
component that actually executes a binary. This module builds the request,
applies the scope guard, and interprets the reply. It never runs a process on
Windows itself.
"""

from __future__ import annotations

import http.client
import json
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import kws.paths as kws_paths
import kws.secrets as kws_secrets
import server.catalog as catalog
import server.commands as commands
import server.evidence as evidence
import server.history as history
import server.security as security

AGENT_TOKEN_SECRET = "agent_token"
DEFAULT_TIMEOUT = 180
# Everything that can go wrong while talking to the agent. A dead or busy agent must produce
# a clean error (or a 503), never an unhandled exception.
AGENT_ERRORS = (OSError, ValueError, http.client.HTTPException)

# Work folders. Secret inputs (wordlists, hashes) are deleted when their run ends. The sweep
# catches what an interrupted run left behind. Output files stay until their folder ages out.
SECRET_INPUT_MAX_AGE = 3600  # seconds; the agent caps every run well below this
WORK_MAX_AGE = 7 * 24 * 3600

# Job bookkeeping. Finished jobs are forgotten after an hour, or sooner once JOB_KEEP is exceeded.
JOB_KEEP = 200
JOB_TTL = 3600
# A watcher thread records each job when it finishes, even if nobody polls it.
JOB_WATCH_INTERVAL = 5
JOB_WATCH_LIMIT = 2 * 3600

# Friendly names for the fields a one-click form must fill.
_FIELD_LABELS = {
    "target": "target",
    "url": "URL",
    "name": "domain",
    "query": "query",
    "user": "username",
    "users": "usernames",
    "passwords": "passwords",
    "hash": "hash",
    "hashes": "hashes",
    "module": "module",
    "file": "evidence file",
}


# --- agent transport ------------------------------------------------------


def _token() -> str:
    return kws_secrets.get_secret(AGENT_TOKEN_SECRET)


def _request(
    cfg, method: str, path: str, body: dict | None = None, timeout: int = 30
) -> dict[str, Any]:
    url = cfg.agent_url.rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    token = _token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def agent_get(cfg, path: str, timeout: int = 15) -> dict[str, Any]:
    return _request(cfg, "GET", path, None, timeout)


def agent_post(cfg, path: str, body: dict, timeout: int = DEFAULT_TIMEOUT) -> dict:
    return _request(cfg, "POST", path, body, timeout)


def agent_online(cfg) -> bool:
    try:
        return bool(agent_get(cfg, "/health", timeout=5).get("ok"))
    except AGENT_ERRORS:
        return False


# --- helpers --------------------------------------------------------------


def _targets_of(payload: dict[str, Any]) -> list[str]:
    # Every host-bearing field is scope-checked, not just the first one: a payload with a
    # private "target" and a public "url" must not pass. The "name" field is overloaded (a
    # search query for searchsploit, an evidence filename for file tools), so it is
    # deliberately excluded: it is never a host the user is scanning.
    return [str(payload[key]) for key in ("target", "url") if payload.get(key)]


def _target_of(payload: dict[str, Any]) -> str:
    """A display string for history and audit: all host fields, joined."""
    return ", ".join(_targets_of(payload))


def _new_work_dir() -> Path:
    # Every run gets its own subdirectory under the shared work dir. Several
    # tools (foremost, hcxtools, cewl) write output next to their input and
    # refuse to overwrite an existing directory, so a stable path breaks the
    # second run of the same tool. The path is not created here: a preview
    # must not touch the disk.
    return kws_paths.work_dir() / secrets.token_hex(8)


def _ctx(payload: dict[str, Any], tool_id: str, work: Path) -> dict[str, Any]:
    """The context a command builder sees. Reads the evidence folder; writes nothing."""
    file_paths = {
        name: kws_paths.to_wsl_path(work / name)
        for name in commands.files_for(tool_id, payload)
    }

    evidence: dict[str, str] = {}
    ev_dir = kws_paths.evidence_dir()
    for item in ev_dir.iterdir() if ev_dir.exists() else []:
        if item.is_symlink() or not item.is_file():
            continue
        evidence[item.name] = kws_paths.to_wsl_path(item)

    return {
        "work": kws_paths.to_wsl_path(work),
        "files": file_paths,
        "evidence": evidence,
    }


def _write_inputs(tool_id: str, payload: dict[str, Any], work: Path) -> list[Path]:
    """Create the run's work folder and write its secret input files.

    Only called after the command has validated, so a rejected request leaves no secrets on
    disk. On a write error, whatever was written is removed again.
    """
    written: list[Path] = []
    try:
        work.mkdir(parents=True, exist_ok=True)
        for name, content in commands.files_for(tool_id, payload).items():
            path = work / name
            path.write_text(content, encoding="utf-8")
            written.append(path)
    except OSError:
        _remove_inputs(written)
        raise
    return written


def _remove_inputs(paths) -> None:
    for item in paths:
        try:
            Path(item).unlink(missing_ok=True)
        except OSError:
            pass  # best effort; the sweep retries later


def sweep_work_dirs() -> None:
    """Remove secret inputs left by an interrupted run, and work folders that have aged out.

    Called at app startup and before every run.
    """
    now = time.time()
    try:
        folders = list(kws_paths.work_dir().iterdir())
    except OSError:
        return
    for folder in folders:
        if folder.is_symlink() or not folder.is_dir():
            continue
        try:
            age = now - folder.stat().st_mtime
        except OSError:
            continue
        if age > WORK_MAX_AGE:
            shutil.rmtree(folder, ignore_errors=True)
        elif age > SECRET_INPUT_MAX_AGE:
            _remove_inputs(folder / name for name in commands.SECRET_FILE_NAMES)


def _agent_error(exc: Exception):
    """Map a failed agent call to ``(body, status)``: the agent's refusal code, or 503."""
    if isinstance(exc, urllib.error.HTTPError):
        return {
            "error": f"the runtime refused the request ({exc.code})",
            "detail": exc.read().decode(errors="replace"),
        }, exc.code
    return {"error": "the runtime is not reachable", "detail": str(exc)}, 503


# --- public operations ----------------------------------------------------


def technology_status(cfg) -> dict[str, Any]:
    online = agent_online(cfg)
    return {"online": online, "distro": cfg.runtime_distro}


def _build(tool_id: str, payload: dict[str, Any], work: Path):
    """Return ``(argv, None)`` or ``(None, (error_body, status))``. Writes nothing to disk."""
    try:
        argv = commands.build(tool_id, payload, _ctx(payload, tool_id, work))
    except commands.BadInput as exc:
        return None, (
            {
                "error": str(exc) or "that value cannot be used here",
                "detail": "Fix that field and try again.",
            },
            400,
        )
    except commands.MissingInput as exc:
        key = str(exc.args[0]) if exc.args else "input"
        label = _FIELD_LABELS.get(key, key)
        return None, (
            {
                "error": f"the {label} field is required",
                "detail": "Fill in that field and try again.",
            },
            400,
        )
    if argv is None:
        return None, (
            {
                "error": "this tool has no one-click form yet",
                "detail": (
                    "The app knows this tool, but there is no safe one-click "
                    "form for it. Install it, then run it from the runtime "
                    "shell (or open its docs)."
                ),
            },
            501,
        )
    return argv, None


def _prepare_run(
    cfg, tool_id: str, payload: dict[str, Any], timeout: int, user_confirmed: bool = False
):
    """Scope-check and build a run request: ``(body, None)`` or ``(None, (error, status))``.

    ``confirm_external`` ("I am authorised to test this public target") is honoured only
    when ``user_confirmed`` is true, i.e. when the request came from the user's own click
    in the UI. A model, a skill or an MCP client can never grant it to itself.

    The returned body carries ``inputs``: the secret files written for this run. Callers
    must pop it (the agent never sees it) and delete those files when the run ends.
    """
    if catalog.get(tool_id) is None:
        return None, ({"error": "unknown tool"}, 404)

    targets = _targets_of(payload)
    # Only a real JSON true counts: a string "yes" or a number never grants the confirmation.
    confirmed = user_confirmed and payload.get("confirm_external") is True
    for target in targets or [""]:
        allowed, reason = security.scope_allows(target, confirmed, cfg.private_ranges)
        if not allowed:
            return None, ({"error": "target is out of scope", "detail": reason}, 403)

    sweep_work_dirs()
    work = _new_work_dir()
    argv, error = _build(tool_id, payload, work)
    if error is not None:
        return None, error
    try:
        inputs = _write_inputs(tool_id, payload, work)
    except OSError as exc:
        return None, (
            {
                "error": f"could not write a work file: {exc}",
                "detail": "Check disk space and permissions, then try again.",
            },
            400,
        )
    return {
        "tool": tool_id,
        "argv": argv,
        "target": _target_of(payload),
        "targets": targets,
        "confirm_external": confirmed,
        "timeout": commands.timeout_for(tool_id, timeout),
        "inputs": [str(path) for path in inputs],
    }, None


# --- jobs: streamed, cancellable runs --------------------------------------

_JOB_META: dict[str, dict[str, Any]] = {}
_JOB_LOCK = threading.Lock()


def _prune_job_meta() -> None:
    """Forget finished jobs: stale ones, and the oldest once there are more than JOB_KEEP.

    Caller holds _JOB_LOCK. Unfinished jobs are never pruned.
    """
    now = time.time()
    finished = sorted(
        (jid for jid, meta in _JOB_META.items() if meta["recorded"]),
        key=lambda jid: _JOB_META[jid]["started"],
    )
    excess = len(_JOB_META) - JOB_KEEP
    for jid in finished:
        stale = _JOB_META[jid]["started"] < now - JOB_TTL
        if excess <= 0 and not stale:
            break
        del _JOB_META[jid]
        excess -= 1


def _start_watcher(cfg, job_id: str) -> None:
    threading.Thread(target=_watch_job, args=(cfg, job_id), daemon=True).start()


def _watch_job(cfg, job_id: str) -> None:
    """Record a job when it finishes, even if no one polls it. Gives up after JOB_WATCH_LIMIT."""
    deadline = time.time() + JOB_WATCH_LIMIT
    while time.time() < deadline:
        time.sleep(JOB_WATCH_INTERVAL)
        try:
            snap = agent_get(cfg, f"/jobs/{job_id}?since=0", 20)
        except AGENT_ERRORS:
            continue  # the agent is busy or restarting: try again until the limit
        if snap.get("done"):
            _record_finished(cfg, snap)
            return
    # The agent never reported the job as done. Mark it finished so it can be pruned,
    # and remove its inputs.
    with _JOB_LOCK:
        meta = _JOB_META.get(job_id)
        inputs = []
        if meta is not None and not meta["recorded"]:
            meta["recorded"] = True
            inputs = meta.pop("inputs", [])
    _remove_inputs(inputs)


def start_job(
    cfg, tool_id: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT,
    user_confirmed: bool = False,
):
    """Start a run in the runtime and return immediately with a job id.

    The secret input files are deleted when the run ends. If the run never gets started (any
    failure below), they are deleted here, in the ``finally``.
    """
    body, error = _prepare_run(cfg, tool_id, payload, timeout, user_confirmed)
    if error is not None:
        return error
    inputs = body.pop("inputs", [])
    handed_off = False  # True once the watcher owns the inputs
    try:
        reply = agent_post(cfg, "/jobs", {**body, "kind": "run"}, 30)
        job_id = str(reply["job"])
        with _JOB_LOCK:
            _prune_job_meta()
            _JOB_META[job_id] = {
                "tool": tool_id, "target": body["target"],
                # Stored redacted: passwords and hashes never sit in memory as plain fields.
                "payload": history.redact(payload),
                "argv": body["argv"], "started": time.time(), "recorded": False,
                "kind": "run", "inputs": inputs,
            }
        handed_off = True
    except (*AGENT_ERRORS, KeyError) as exc:
        return _agent_error(exc)
    finally:
        if not handed_off:
            _remove_inputs(inputs)
    _start_watcher(cfg, job_id)
    return {"job": job_id, "argv": body["argv"]}, 202


def start_manage_job(cfg, tool_id: str, kind: str):
    """Start an install/remove in the runtime; output streams like a run."""
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    try:
        reply = agent_post(cfg, "/jobs", {"kind": kind, "tool": tool_id}, 30)
        job_id = str(reply["job"])
    except AGENT_ERRORS as exc:
        return _agent_error(exc)
    with _JOB_LOCK:
        _prune_job_meta()
        _JOB_META[job_id] = {
            "tool": tool_id, "target": "", "payload": {}, "started": time.time(),
            "recorded": False, "kind": kind, "inputs": [],
        }
    _start_watcher(cfg, job_id)
    return {"job": job_id}, 202


def valid_job_id(job_id: str) -> bool:
    """Job ids are ASCII letters and digits only (``str.isalnum`` alone accepts other scripts)."""
    return job_id.isascii() and job_id.isalnum()


def job_status(cfg, job_id: str, since: int = 0):
    """Poll a job. The first poll that sees it finished records it in history/audit."""
    if not valid_job_id(job_id):
        return {"error": "unknown job"}, 404
    try:
        snap = agent_get(cfg, f"/jobs/{job_id}?since={max(0, since)}", 20)
    except AGENT_ERRORS as exc:
        return _agent_error(exc)
    if snap.get("done"):
        unlocked = _record_finished(cfg, snap)
        if unlocked:
            snap["achievements"] = unlocked
    return snap, 200


def job_cancel(cfg, job_id: str):
    if not valid_job_id(job_id):
        return {"error": "unknown job"}, 404
    try:
        return agent_post(cfg, f"/jobs/{job_id}/cancel", {}, 20), 200
    except AGENT_ERRORS as exc:
        return _agent_error(exc)


def _record_finished(cfg, snap: dict[str, Any]) -> list[str]:
    """Record a finished job once. Returns the names of any achievements it unlocked."""
    import server.achievements as achievements
    import server.db as db
    import server.history as history

    with _JOB_LOCK:
        meta = _JOB_META.get(snap.get("id", ""))
        if meta is None or meta["recorded"]:
            return []
        meta["recorded"] = True
        inputs = meta.pop("inputs", [])
    _remove_inputs(inputs)  # the agent has finished with the secret files
    ok = snap.get("state") == "done"
    duration_ms = float(snap.get("elapsed") or 0) * 1000
    if meta["kind"] == "run":
        # The full output is saved as a transcript; History keeps the last 500 characters.
        text = snap.get("output") or ""
        try:
            text = agent_get(cfg, f"/jobs/{snap['id']}?since=0", 20).get("output", text)
        except AGENT_ERRORS:
            pass
        history.record_run(
            meta["tool"], meta["target"], meta["payload"], int(snap.get("rc") or 0),
            duration_ms, text[-500:], ok,
        )
        try:
            import server.recordings as recordings

            recordings.save_transcript(
                meta["tool"], meta["target"], meta.get("argv"), text, snap.get("rc"),
                str(snap.get("state")), float(snap.get("elapsed") or 0),
            )
        except OSError:
            pass  # a full disk must not break the run
    db.audit("user", f"tool:{meta['tool']}" if meta["kind"] == "run"
             else f"tools:{meta['kind']}", meta["target"] or meta["tool"],
             "ok" if ok else str(snap.get("state")))
    return achievements.evaluate() if meta["kind"] == "run" else []


def run_outcome(result: Any, status: int) -> tuple[int, bool, str]:
    """Interpret a synchronous run for history and audit: ``(rc, success, output tail)``.

    Success needs the agent to report ``ok`` with exit code 0. A non-zero exit is a failure
    even though the HTTP call itself returned 200.
    """
    if not isinstance(result, dict):
        return status, False, ""
    if status != 200:
        return status, False, str(result.get("detail") or result.get("error") or "")[-500:]
    rc = int(result.get("rc") or 0)
    text = str(result.get("stdout") or "") + str(result.get("stderr") or "")
    return rc, bool(result.get("ok")) and rc == 0, text[-500:]


def run(
    cfg, tool_id: str, payload: dict[str, Any], timeout: int = DEFAULT_TIMEOUT,
    user_confirmed: bool = False,
):
    body, error = _prepare_run(cfg, tool_id, payload, timeout, user_confirmed)
    if error is not None:
        return error
    inputs = body.pop("inputs", [])
    try:
        result = agent_post(cfg, "/run", body, timeout + 15)
    except AGENT_ERRORS as exc:  # URLError, TimeoutError, RemoteDisconnected, HTTPException...
        return _agent_error(exc)
    finally:
        _remove_inputs(inputs)
    return result, 200


def preview(cfg, tool_id: str, payload: dict[str, Any]):
    """Return the argv that would run, without running it or writing anything."""
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    argv, error = _build(tool_id, payload, _new_work_dir())
    if error is not None:
        return error
    return {"argv": argv}, 200


def install(cfg, tool_id: str, timeout: int = 1800):
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    try:
        return agent_post(cfg, "/tools/install", {"tool": tool_id}, timeout), 200
    except AGENT_ERRORS as exc:
        return _agent_error(exc)


def remove(cfg, tool_id: str, timeout: int = 1800):
    if catalog.get(tool_id) is None:
        return {"error": "unknown tool"}, 404
    try:
        return agent_post(cfg, "/tools/remove", {"tool": tool_id}, timeout), 200
    except AGENT_ERRORS as exc:
        return _agent_error(exc)


def manage_list(cfg) -> dict[str, Any]:
    rows = []
    present: dict[str, bool] = {}
    online = False
    try:
        status = agent_get(cfg, "/tools")
        present = {t.get("id"): bool(t.get("present")) for t in status.get("tools", [])}
        online = True
    except AGENT_ERRORS:
        online = False

    for tool in catalog.tools():
        tool_id = tool.get("id")
        if not tool.get("packages"):
            continue
        rows.append(
            {
                "id": tool_id,
                "name": tool.get("name") or tool_id,
                "category": tool.get("category") or "other",
                "summary": tool.get("summary") or "",
                "packages": list(tool.get("packages") or []),
                "baseline": bool(tool.get("baseline")),
                "prerequisites": list(tool.get("prerequisites") or []),
                "present": present.get(tool_id, None) if online else None,
            }
        )
    return {"online": online, "tools": rows}


def evidence_files() -> list[str]:
    ev = kws_paths.evidence_dir()
    if not ev.exists():
        return []
    return sorted(p.name for p in ev.iterdir() if evidence.is_listed(p))
