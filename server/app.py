"""Flask application factory and routes.

Loopback only. Every ``/api/`` route requires the bearer cookie; every
state-changing route also requires the CSRF header. The browser UI is a static
single page served from ``ui/``.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, jsonify, make_response, redirect, request, send_from_directory
from werkzeug.exceptions import HTTPException

import kws.paths as kws_paths
import server.achievements as achievements
import server.ai as ai
import server.backup as backup
import server.catalog as catalog
import server.cheat_sheets as cheat_sheets
import server.commands as commands
import server.container_runtime as container_runtime
import server.db as db
import server.evidence as evidence
import server.history as history
import server.notebook as notebook
import server.onboarding as onboarding
import server.playground as playground
import server.recordings as recordings
import server.report as report
import server.security as security
import server.tools as tools

UI_DIR = Path(kws_paths.resource("ui"))
# The launch code works once and only for this long after the app starts.
LAUNCH_TTL = 600

_LAUNCH_NOTES = {
    "used": "This launch link was already used. Start the app again to open it.",
    "expired": "This launch link has expired. Start the app again to open it.",
}


SEVERITIES = ("critical", "high", "medium", "low", "info")
FINDING_LIMITS = {"tool": 100, "target": 300, "title": 200, "detail": 5000}


def _check_finding(data: dict) -> tuple[str, str, str, str, str] | str:
    """Validate a finding from the browser. Returns the cleaned fields, or an error message."""
    values = {}
    for key, limit in FINDING_LIMITS.items():
        raw = data.get(key, "")
        if not isinstance(raw, str):
            return f"{key} must be text"
        values[key] = raw.strip()
        if len(values[key]) > limit:
            return f"{key} can be at most {limit} characters"
    if not values["title"]:
        return "a title is required"
    severity = data.get("severity", "info")
    if severity not in SEVERITIES:
        return "severity must be one of: " + ", ".join(SEVERITIES)
    return values["tool"], values["target"], severity, values["title"], values["detail"]


def create_app(cfg, auth_token: str, csrf_token: str) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["KWS_TOKEN"] = auth_token
    app.config["KWS_CSRF"] = csrf_token
    app.config["KWS_CFG"] = cfg
    # Cookie names carry the port, so two copies on different ports do not clash.
    auth_cookie, csrf_cookie = security.cookie_names(cfg.port)
    app.config["KWS_AUTH_COOKIE"] = auth_cookie
    app.config["KWS_CSRF_COOKIE"] = csrf_cookie
    # One-time code the launcher puts in the first URL. It is spent on first use and expires.
    app.config["KWS_LAUNCH"] = security.new_token()
    app.config["KWS_LAUNCH_EXPIRES"] = time.time() + LAUNCH_TTL
    app.config["KWS_LAUNCH_NOTE"] = ""
    security.install_headers(app)
    db.init_db()
    tools.sweep_work_dirs()

    log = logging.getLogger("kws")
    launch_lock = threading.Lock()

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException):
        # The UI expects JSON from /api; Flask's default is an HTML page.
        if request.path.startswith("/api"):
            return jsonify({"error": exc.description or exc.name}), exc.code
        return exc

    @app.errorhandler(Exception)
    def _unexpected_error(exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "internal error", "detail": type(exc).__name__}), 500

    # --- UI ---------------------------------------------------------------
    def _spend_launch(launch: str):
        """Accept the launch code once, or explain why it cannot be used."""
        with launch_lock:
            code = app.config.get("KWS_LAUNCH", "")
            if code and time.time() >= app.config.get("KWS_LAUNCH_EXPIRES", 0):
                app.config["KWS_LAUNCH"] = ""
                app.config["KWS_LAUNCH_NOTE"] = "expired"
                code = ""
            accepted = bool(code) and hmac.compare_digest(
                launch.encode("utf-8"), code.encode("utf-8")
            )
            if accepted:
                app.config["KWS_LAUNCH"] = ""  # spent: a second use is refused
                app.config["KWS_LAUNCH_NOTE"] = "used"
            note = app.config.get("KWS_LAUNCH_NOTE", "")
        if not accepted:
            message = _LAUNCH_NOTES.get(note, "This launch link is not valid.")
            return make_response(message, 403, {"Content-Type": "text/plain; charset=utf-8"})
        resp = redirect("/")
        # The UI is served over plain http on loopback, so Secure would make
        # some webviews drop the cookies. The auth cookie is HttpOnly; the
        # CSRF cookie must be readable by the UI script (double-submit
        # pattern), so it is not.
        resp.set_cookie(
            auth_cookie, auth_token, httponly=True, samesite="Strict", path="/", secure=False
        )
        resp.set_cookie(
            csrf_cookie, csrf_token, httponly=False, samesite="Strict", path="/", secure=False
        )
        return resp

    @app.get("/")
    def index():
        # The launcher opens "/?launch=<one-time code>" so that the session secret never
        # appears in the address bar, history or a log. The code is spent on first use and
        # the browser is redirected to a clean "/". The session itself lives in cookies.
        launch = request.args.get("launch", "")
        if launch:
            return _spend_launch(launch)
        return send_from_directory(UI_DIR, "index.html")

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(UI_DIR, filename)

    # --- health -----------------------------------------------------------
    @app.get("/api/healthz")
    @security.require_auth
    def healthz():
        return jsonify(
            {
                "ok": True,
                "app": catalog.app_meta().get("name", ""),
                "runtime": tools.technology_status(cfg),
            }
        )

    # --- catalog ----------------------------------------------------------
    @app.get("/api/catalog")
    @security.require_auth
    def api_catalog():
        return jsonify(
            {
                "app": catalog.app_meta(),
                "categories": catalog.categories(),
                "tools": catalog.tools(),
                "automated": commands.automated_ids(),
                "terminal": commands.TERMINAL_COMMANDS,
                "required": {tid: commands.required_for(tid) for tid in commands.automated_ids()},
            }
        )

    # --- run a tool -------------------------------------------------------
    @app.post("/api/tool/<tool_id>")
    @security.require_auth
    @security.require_csrf
    def api_tool_run(tool_id: str):
        import time as _time

        payload = request.get_json(silent=True) or {}
        target = tools_target(payload)
        start = _time.time()
        result, status = tools.run(cfg, tool_id, payload, user_confirmed=True)
        duration_ms = round((_time.time() - start) * 1000, 1)
        # A refused request (bad input, out of scope, unknown tool) never ran: it is not a run.
        if status not in (400, 403, 404):
            # Success is the agent's verdict (its exit code), not just an HTTP 200.
            rc, ok, output_preview = tools.run_outcome(result, status)
            history.record_run(tool_id, target, payload, rc, duration_ms, output_preview, ok)
            db.audit("user", f"tool:{tool_id}", target,
                     "ok" if ok else f"status {status}, rc {rc}")
        return jsonify(result), status

    # --- jobs: streamed, cancellable runs and installs -------------------
    @app.post("/api/tool/<tool_id>/start")
    @security.require_auth
    @security.require_csrf
    def api_tool_start(tool_id: str):
        payload = request.get_json(silent=True) or {}
        result, status = tools.start_job(cfg, tool_id, payload, user_confirmed=True)
        if status not in (202, 400, 403, 404):  # refused requests are not runs
            db.audit("user", f"tool:{tool_id}", tools_target(payload), f"status {status}")
        return jsonify(result), status

    @app.post("/api/tools/<tool_id>/<action>-job")
    @security.require_auth
    @security.require_csrf
    def api_tools_manage_job(tool_id: str, action: str):
        if action not in ("install", "remove"):
            return jsonify({"error": "not found"}), 404
        result, status = tools.start_manage_job(cfg, tool_id, action)
        return jsonify(result), status

    @app.get("/api/jobs/<job_id>")
    @security.require_auth
    def api_job_status(job_id: str):
        if not tools.valid_job_id(job_id):
            return jsonify({"error": "unknown job"}), 404
        since = request.args.get("since", "0")
        since_n = int(since) if since.isascii() and since.isdigit() else 0
        result, status = tools.job_status(cfg, job_id, since_n)
        return jsonify(result), status

    @app.post("/api/jobs/<job_id>/cancel")
    @security.require_auth
    @security.require_csrf
    def api_job_cancel(job_id: str):
        result, status = tools.job_cancel(cfg, job_id)
        return jsonify(result), status

    # --- interactive tools: open a runtime terminal -----------------------
    @app.post("/api/tool/<tool_id>/terminal")
    @security.require_auth
    @security.require_csrf
    def api_tool_terminal(tool_id: str):
        from app import runtime

        command = commands.TERMINAL_COMMANDS.get(tool_id)
        if command is None:
            return jsonify({"error": "this tool does not open in a terminal"}), 404
        ok, message = runtime.open_terminal(cfg, command)
        db.audit("user", f"terminal:{tool_id}", "", "ok" if ok else "failed")
        return jsonify({"ok": ok, "message": message, "command": command}), 200 if ok else 500

    @app.post("/api/runtime/shell")
    @security.require_auth
    @security.require_csrf
    def api_runtime_shell():
        from app import runtime

        ok, message = runtime.open_terminal(cfg, None)
        db.audit("user", "terminal:shell", "", "ok" if ok else "failed")
        return jsonify({"ok": ok, "message": message}), 200 if ok else 500

    # --- tool management --------------------------------------------------
    @app.post("/api/tool/<tool_id>/preview")
    @security.require_auth
    @security.require_csrf
    def api_tool_preview(tool_id: str):
        payload = request.get_json(silent=True) or {}
        result, status = tools.preview(cfg, tool_id, payload)
        return jsonify(result), status

    @app.get("/api/tools/manage")
    @security.require_auth
    def api_tools_manage():
        return jsonify(tools.manage_list(cfg))

    @app.post("/api/tools/<tool_id>/install")
    @security.require_auth
    @security.require_csrf
    def api_tools_install(tool_id: str):
        result, status = tools.install(cfg, tool_id)
        db.audit("user", "tools:install", tool_id, "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

    @app.post("/api/tools/<tool_id>/remove")
    @security.require_auth
    @security.require_csrf
    def api_tools_remove(tool_id: str):
        result, status = tools.remove(cfg, tool_id)
        db.audit("user", "tools:remove", tool_id, "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

    # --- runtime ----------------------------------------------------------
    @app.get("/api/runtime")
    @security.require_auth
    def api_runtime_status():
        from app import runtime

        result = runtime.status(cfg)
        prov = runtime.provisioning_status(cfg)
        if prov:
            result["provisioning"] = prov
        return jsonify(result)

    @app.post("/api/runtime/ensure")
    @security.require_auth
    @security.require_csrf
    def api_runtime_ensure():
        from app import runtime

        result = runtime.ensure(cfg)
        db.audit("user", "runtime:ensure", "", "ok" if result.get("ok") else "failed")
        return jsonify(result)

    @app.post("/api/runtime/start")
    @security.require_auth
    @security.require_csrf
    def api_runtime_start():
        # Starting the agent is an action, so it is a POST. GET /api/runtime only reports.
        from app import runtime

        started = runtime.autostart(cfg)
        if started:  # only a real start is audited; a throttled or repeated call is not
            db.audit("user", "runtime:start", "", "started")
        return jsonify({"ok": True, "started": started})

    # --- evidence ---------------------------------------------------------
    @app.get("/api/evidence")
    @security.require_auth
    def api_evidence():
        return jsonify({"path": str(kws_paths.evidence_dir()), "files": tools.evidence_files()})

    @app.post("/api/evidence/upload")
    @security.require_auth
    @security.require_csrf
    def api_evidence_upload():
        # The raw file is the body; its name travels in a header, URL-encoded, so it
        # never lands in a URL or in the server log.
        raw = request.headers.get("X-KWS-Filename", "")
        try:
            saved = evidence.store(request.stream, unquote(raw), evidence.MAX_UPLOAD)
        except evidence.UploadError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        db.audit("user", "evidence:upload", saved, "ok")
        return jsonify({"ok": True, "name": saved, "files": tools.evidence_files()})

    # --- findings / audit / report ---------------------------------------
    @app.get("/api/findings")
    @security.require_auth
    def api_findings():
        return jsonify({"findings": db.findings()})

    @app.post("/api/findings")
    @security.require_auth
    @security.require_csrf
    def api_add_finding():
        data = request.get_json(silent=True) or {}
        checked = _check_finding(data)
        if isinstance(checked, str):
            return jsonify({"ok": False, "error": checked}), 400
        fid = db.add_finding(*checked)
        db.audit("user", "finding:add", checked[1], f"id {fid}")
        return jsonify({"ok": True, "id": fid})

    @app.delete("/api/findings/<int:finding_id>")
    @security.require_auth
    @security.require_csrf
    def api_delete_finding(finding_id: int):
        ok = db.delete_finding(finding_id)
        if ok:
            db.audit("user", "finding:delete", "", f"id {finding_id}")
        return jsonify({"ok": ok}), 200 if ok else 404

    @app.get("/api/audit")
    @security.require_auth
    def api_audit():
        return jsonify({"audit": db.audits()})

    @app.get("/api/report")
    @security.require_auth
    def api_report():
        fmt = (request.args.get("format") or "html").lower()
        rows = db.findings(limit=None)  # a report lists every finding, not the newest 200
        name = catalog.app_meta().get("name", "Report")
        if fmt == "json":
            body, mime, ext = report.to_json(rows, name), "application/json", "json"
        elif fmt == "csv":
            body, mime, ext = report.to_csv(rows), "text/csv", "csv"
        else:
            body, mime, ext = report.to_html(rows, name), "text/html", "html"
        resp = make_response(body)
        resp.headers["Content-Type"] = mime
        resp.headers["Content-Disposition"] = f"attachment; filename=report.{ext}"
        return resp

    # --- AI (optional) ----------------------------------------------------
    @app.get("/api/ai/config")
    @security.require_auth
    def api_ai_config_get():
        return jsonify(ai.get_config())

    @app.post("/api/ai/config")
    @security.require_auth
    @security.require_csrf
    def api_ai_config_set():
        data = request.get_json(silent=True) or {}
        try:
            ai.set_config(
                str(data.get("provider", "none")),
                str(data.get("base_url", "")),
                str(data.get("model", "")),
            )
        except (ValueError, ai.AIError) as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify(ai.get_config())

    @app.post("/api/ai/key")
    @security.require_auth
    @security.require_csrf
    def api_ai_key():
        data = request.get_json(silent=True) or {}
        key = str(data.get("api_key", "")).strip()
        provider = str(data.get("provider") or ai.get_config()["provider"])
        try:
            ai.set_key(provider, key)
        except (ValueError, OSError) as exc:
            return jsonify({"error": str(exc)}), 400
        db.audit("user", f"ai:key:{provider}", "", "set" if key else "cleared")
        return jsonify(ai.get_config())

    @app.post("/api/ai/explain")
    @security.require_auth
    @security.require_csrf
    def api_ai_explain():
        data = request.get_json(silent=True) or {}
        return jsonify(ai.explain(str(data.get("tool", "a tool")), str(data.get("output", ""))))

    # --- AI providers, models and chat -----------------------------------------
    @app.post("/api/ai/test")
    @security.require_auth
    @security.require_csrf
    def api_ai_test():
        data = request.get_json(silent=True) or {}
        return jsonify(
            ai.test(
                str(data.get("provider", "")),
                str(data.get("base_url", "")),
                str(data.get("model", "")),
                str(data.get("api_key", "")),
            )
        )

    @app.post("/api/ai/chat")
    @security.require_auth
    @security.require_csrf
    def api_ai_chat():
        data = request.get_json(silent=True) or {}
        messages = data.get("messages")
        if not isinstance(messages, list):
            return jsonify({"error": "messages must be a list"}), 400
        clean = [
            {"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
            for m in messages
            if isinstance(m, dict)
        ]
        return jsonify(ai.respond(clean))

    # --- Containers ----------------------------------------------------------

    @app.get("/api/containers/status")
    @security.require_auth
    def api_containers_status():
        return jsonify(container_runtime.status())

    @app.post("/api/containers/podman/install")
    @security.require_auth
    @security.require_csrf
    def api_install_podman():
        result = container_runtime.install_podman()
        db.audit(
            "user",
            "container:install",
            result.get("message", ""),
            "ok" if result["ok"] else "failed",
        )
        return jsonify(result), 200 if result["ok"] else 500

    @app.get("/api/containers/images")
    @security.require_auth
    def api_list_images():
        images = container_runtime.list_images()
        return jsonify({"images": images})

    @app.post("/api/containers/images/pull")
    @security.require_auth
    @security.require_csrf
    def api_pull_image():
        data = request.get_json(silent=True) or {}
        name = data.get("name")
        if not name:
            return jsonify({"error": "Image name required"}), 400
        result = container_runtime.pull_image(name)
        db.audit(
            "user",
            "container:pull",
            name,
            "ok" if result["ok"] else f"status {result.get('rc', '')}",
        )
        return jsonify(result), 200 if result["ok"] else 500

    @app.get("/api/containers")
    @security.require_auth
    def api_list_containers():
        containers = container_runtime.list_containers(all=True)
        return jsonify({"containers": containers})

    @app.post("/api/containers/run")
    @security.require_auth
    @security.require_csrf
    def api_run_container():
        data = request.get_json(silent=True) or {}
        image = data.get("image")
        name = data.get("name")
        ports = data.get("ports") or []
        volumes = data.get("volumes") or []
        command = data.get("command") or []

        if not isinstance(image, str) or not isinstance(name, str) or not image or not name:
            return jsonify({"error": "Image and name required"}), 400
        if not _is_text_list(ports) or not _is_text_list(volumes):
            return jsonify({"error": "ports and volumes must be lists of text"}), 400
        if not _is_text_list(command):
            return jsonify({"error": "command must be a list of text"}), 400

        result = container_runtime.run_container(image, name, ports, volumes, command)
        if result["ok"]:
            db.audit("user", "container:run", result.get("container_id", ""), f"image={image}")
        return jsonify(result), 200 if result["ok"] else 500

    @app.post("/api/containers/<container_id>/start")
    @security.require_auth
    @security.require_csrf
    def api_start_container(container_id):
        result = container_runtime.start_container(container_id)
        db.audit(
            "user",
            "container:start",
            container_id,
            "ok" if result["ok"] else result.get("message", ""),
        )
        return jsonify(result), 200 if result["ok"] else 500

    @app.post("/api/containers/<container_id>/stop")
    @security.require_auth
    @security.require_csrf
    def api_stop_container(container_id):
        result = container_runtime.stop_container(container_id)
        db.audit(
            "user",
            "container:stop",
            container_id,
            "ok" if result["ok"] else result.get("message", ""),
        )
        return jsonify(result), 200 if result["ok"] else 500

    @app.delete("/api/containers/<container_id>")
    @security.require_auth
    @security.require_csrf
    def api_remove_container(container_id):
        result = container_runtime.remove_container(container_id)
        db.audit(
            "user",
            "container:remove",
            container_id,
            "ok" if result["ok"] else result.get("message", ""),
        )
        return jsonify(result), 200 if result["ok"] else 500

    @app.get("/api/containers/<container_id>/logs")
    @security.require_auth
    def api_container_logs(container_id):
        tail = request.args.get("tail", 100, type=int)
        result = container_runtime.get_container_logs(container_id, tail)
        return jsonify(result), 200 if result["ok"] else 500

    @app.post("/api/containers/<container_id>/exec")
    @security.require_auth
    @security.require_csrf
    def api_exec_container(container_id):
        data = request.get_json(silent=True) or {}
        cmd = data.get("cmd", [])
        if not cmd or not isinstance(cmd, list) or not all(isinstance(a, str) for a in cmd):
            return jsonify({"error": "Command required (a list of strings)"}), 400
        result = container_runtime.exec_in_container(container_id, cmd)
        db.audit("user", "container:exec", container_id, " ".join(cmd))
        return jsonify(result), 200 if result["ok"] else 500

    # --- History ---
    @app.get("/api/history")
    @security.require_auth
    def api_history_list():
        limit = request.args.get("limit", "100")
        limit = min(int(limit), 1000) if limit.isdigit() else 100
        tool = request.args.get("tool") or None
        success = request.args.get("success")
        success_val = None
        if success is not None:
            success_val = success.lower() == "true"
        rows = history.list_history(limit=limit, tool=tool, success=success_val)
        return jsonify({"history": rows})

    @app.delete("/api/history/<int:run_id>")
    @security.require_auth
    @security.require_csrf
    def api_history_delete(run_id: int):
        ok = history.delete_history(run_id)
        return jsonify({"ok": ok})

    @app.post("/api/history/clear")
    @security.require_auth
    @security.require_csrf
    def api_history_clear():
        ok = history.clear_history()
        return jsonify({"ok": ok})

    # --- Playground ---
    @app.get("/api/playground/status")
    @security.require_auth
    def api_playground_status():
        return jsonify(playground.get_status())

    @app.post("/api/playground/start")
    @security.require_auth
    @security.require_csrf
    def api_playground_start():
        ok, message = playground.start_playground()
        db.audit("user", "playground:start", "", "ok" if ok else "failed")
        return jsonify({"ok": ok, "message": message})

    @app.post("/api/playground/stop")
    @security.require_auth
    @security.require_csrf
    def api_playground_stop():
        ok, message = playground.stop_playground()
        db.audit("user", "playground:stop", "", "ok" if ok else "failed")
        return jsonify({"ok": ok, "message": message})

    # --- Cheat Sheets ---
    @app.get("/api/cheatsheets")
    @security.require_auth
    def api_cheatsheets_list():
        return jsonify({"cheatsheets": cheat_sheets.list_cheatsheets()})

    @app.get("/api/cheatsheets/<tool_id>")
    @security.require_auth
    def api_cheatsheets_get(tool_id: str):
        sheet = cheat_sheets.get_cheatsheet(tool_id)
        if sheet is None:
            return jsonify({"error": "cheat sheet not found"}), 404
        return jsonify(sheet)

    # --- Achievements ---
    @app.get("/api/achievements")
    @security.require_auth
    def api_achievements_list():
        return jsonify({"achievements": achievements.list_achievements()})

    # --- Notebook ---
    @app.get("/api/notebook/entries")
    @security.require_auth
    def api_notebook_list():
        type_filter = request.args.get("type")
        tags_filter = request.args.get("tags")
        limit = request.args.get("limit", "100")
        limit = int(limit) if limit.isdigit() else 100
        tags_list = tags_filter.split(",") if tags_filter else None
        entries = notebook.list_entries(type=type_filter, tags=tags_list, limit=limit)
        return jsonify({"entries": entries})

    @app.post("/api/notebook/entries")
    @security.require_auth
    @security.require_csrf
    def api_notebook_add():
        data = request.get_json(silent=True) or {}
        entry_type = data.get("type", "note")
        content = data.get("content", "")
        tags = data.get("tags", [])
        if not isinstance(entry_type, str) or not isinstance(content, str):
            return jsonify({"error": "type and content must be text"}), 400
        if not content.strip():
            return jsonify({"error": "content required"}), 400
        try:
            eid = notebook.add_entry(entry_type, content, tags)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"id": eid, "ok": True})

    @app.delete("/api/notebook/entries/<int:eid>")
    @security.require_auth
    @security.require_csrf
    def api_notebook_delete(eid: int):
        ok = notebook.delete_entry(eid)
        return jsonify({"ok": ok})

    @app.get("/api/notebook/export")
    @security.require_auth
    def api_notebook_export():
        md = notebook.export_notebook()
        return jsonify({"markdown": md})

    @app.get("/api/notebook/search")
    @security.require_auth
    def api_notebook_search():
        query = request.args.get("q", "")
        entries = notebook.search_notebook(query)
        return jsonify({"entries": entries})

    # --- Run transcripts (recordings) ---
    @app.get("/api/recordings")
    @security.require_auth
    def api_recordings_list():
        limit = request.args.get("limit", "100")
        rows = recordings.list_recordings(limit=int(limit) if limit.isdigit() else 100)
        return jsonify({"recordings": rows})

    @app.get("/api/recordings/<rid>")
    @security.require_auth
    def api_recordings_load(rid: str):
        found = recordings.load_recording(rid)
        if found is None:
            return jsonify({"error": "no such recording"}), 404
        if request.args.get("download"):
            resp = make_response(found["text"])
            resp.headers["Content-Type"] = "text/plain; charset=utf-8"
            resp.headers["Content-Disposition"] = f"attachment; filename={rid}.txt"
            return resp
        return jsonify(found)

    @app.delete("/api/recordings/<rid>")
    @security.require_auth
    @security.require_csrf
    def api_recordings_delete(rid: str):
        return jsonify({"ok": recordings.delete_recording(rid)})

    # --- Backup and restore ---
    @app.get("/api/backup/export")
    @security.require_auth
    def api_backup_export():
        from datetime import datetime

        data = backup.export_zip()
        db.audit("user", "backup:export", "", f"{len(data)} bytes")
        resp = make_response(data)
        resp.headers["Content-Type"] = "application/zip"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        resp.headers["Content-Disposition"] = f"attachment; filename=kalidesk-backup-{stamp}.zip"
        return resp

    @app.post("/api/backup/import")
    @security.require_auth
    @security.require_csrf
    def api_backup_import():
        data = _read_capped(request.stream, backup.MAX_ZIP)
        if data is None:
            return jsonify({"ok": False, "message": "that file is too large"}), 413
        result = backup.import_zip(data)
        db.audit("user", "backup:import", "", "ok" if result["ok"] else result["message"][:80])
        return jsonify(result), 200 if result["ok"] else 400

    # --- Onboarding ---
    @app.get("/api/onboarding/status")
    @security.require_auth
    def api_onboarding_status():
        return jsonify({
            "needed": onboarding.is_onboarding_needed(),
            "skipped": onboarding.is_skipped(),
        })

    @app.post("/api/onboarding/finish")
    @security.require_auth
    @security.require_csrf
    def api_onboarding_finish():
        data = request.get_json(silent=True) or {}
        if not onboarding.finish_onboarding(data.get("accepted") is True):
            return jsonify({"error": "please confirm the acceptable-use statement first"}), 400
        db.audit("user", "onboarding:finish", "", "accepted acceptable use")
        return jsonify({"ok": True})

    @app.post("/api/onboarding/skip")
    @security.require_auth
    @security.require_csrf
    def api_onboarding_skip():
        onboarding.mark_skipped()
        return jsonify({"ok": True})

    return app


def tools_target(payload: dict) -> str:
    for key in ("target", "url", "name"):
        if payload.get(key):
            return str(payload[key])
    return ""


def _is_text_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _read_capped(stream, limit: int) -> bytes | None:
    """Read a request body up to ``limit`` bytes; None if it is larger.

    Content-Length is checked first, but it can be missing (chunked uploads), so the
    stream itself is what enforces the cap.
    """
    if (request.content_length or 0) > limit:
        return None
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            return None
        chunks.append(chunk)
    return b"".join(chunks)
