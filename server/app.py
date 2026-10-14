"""Flask application factory and routes.

Loopback only. Every ``/api/`` route requires the bearer cookie; every
state-changing route also requires the CSRF header. The browser UI is a static
single page served from ``ui/``.
"""
from __future__ import annotations

import hmac
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_from_directory

import kws_paths
import server.ai as ai
import server.catalog as catalog
import server.commands as commands
import server.db as db
import server.report as report
import server.security as security
import server.tools as tools

UI_DIR = Path(kws_paths.resource("ui"))


def create_app(cfg, auth_token: str, csrf_token: str) -> Flask:
    app = Flask(__name__, static_folder=None)
    app.config["KWS_TOKEN"] = auth_token
    app.config["KWS_CSRF"] = csrf_token
    app.config["KWS_CFG"] = cfg
    security.install_headers(app)
    db.init_db()

    # --- UI ---------------------------------------------------------------
    @app.get("/")
    def index():
        resp = make_response(send_from_directory(UI_DIR, "index.html"))
        token = request.args.get("token", "")
        if token and hmac.compare_digest(token, auth_token):
            resp.set_cookie(security.AUTH_COOKIE, token, httponly=True,
                            samesite="Strict", path="/")
            resp.set_cookie(security.CSRF_COOKIE, csrf_token, httponly=False,
                            samesite="Strict", path="/")
        return resp

    @app.get("/static/<path:filename>")
    def static_files(filename: str):
        return send_from_directory(UI_DIR, filename)

    # --- health -----------------------------------------------------------
    @app.get("/api/healthz")
    @security.require_auth
    def healthz():
        return jsonify({"ok": True, "app": catalog.app_meta().get("name", ""),
                        "runtime": tools.technology_status(cfg)})

    # --- catalog ----------------------------------------------------------
    @app.get("/api/catalog")
    @security.require_auth
    def api_catalog():
        return jsonify({
            "app": catalog.app_meta(),
            "categories": catalog.categories(),
            "tools": catalog.tools(),
            "automated": commands.automated_ids(),
            "required": {tid: commands.required_for(tid)
                         for tid in commands.automated_ids()},
        })

    # --- run a tool -------------------------------------------------------
    @app.post("/api/tool/<tool_id>")
    @security.require_auth
    @security.require_csrf
    def api_tool_run(tool_id: str):
        payload = request.get_json(silent=True) or {}
        result, status = tools.run(cfg, tool_id, payload)
        db.audit("user", f"tool:{tool_id}", tools_target(payload),
                 "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

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
        db.audit("user", "tools:install", tool_id,
                 "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

    @app.post("/api/tools/<tool_id>/remove")
    @security.require_auth
    @security.require_csrf
    def api_tools_remove(tool_id: str):
        result, status = tools.remove(cfg, tool_id)
        db.audit("user", "tools:remove", tool_id,
                 "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

    # --- runtime ----------------------------------------------------------
    @app.get("/api/runtime")
    @security.require_auth
    def api_runtime_status():
        from app import runtime

        return jsonify(runtime.status(cfg))

    @app.post("/api/runtime/ensure")
    @security.require_auth
    @security.require_csrf
    def api_runtime_ensure():
        from app import runtime

        result = runtime.ensure(cfg)
        db.audit("user", "runtime:ensure", "", "ok" if result.get("ok") else "failed")
        return jsonify(result)

    # --- evidence ---------------------------------------------------------
    @app.get("/api/evidence")
    @security.require_auth
    def api_evidence():
        return jsonify({"path": str(kws_paths.evidence_dir()),
                        "files": tools.evidence_files()})

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
        fid = db.add_finding(
            str(data.get("tool", "")), str(data.get("target", "")),
            str(data.get("severity", "info")), str(data.get("title", "")),
            str(data.get("detail", "")),
        )
        db.audit("user", "finding:add", str(data.get("target", "")), f"id {fid}")
        return jsonify({"ok": True, "id": fid})

    @app.get("/api/audit")
    @security.require_auth
    def api_audit():
        return jsonify({"audit": db.audits()})

    @app.get("/api/report")
    @security.require_auth
    def api_report():
        fmt = (request.args.get("format") or "html").lower()
        rows = db.findings()
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
        ai.set_config(str(data.get("provider", "none")),
                      str(data.get("base_url", "")), str(data.get("model", "")))
        return jsonify(ai.get_config())

    @app.post("/api/ai/key")
    @security.require_auth
    @security.require_csrf
    def api_ai_key():
        import kws_secrets

        data = request.get_json(silent=True) or {}
        key = str(data.get("api_key", "")).strip()
        if key:
            kws_secrets.set_secret(ai.SECRET_KEY, key)
        else:
            kws_secrets.delete_secret(ai.SECRET_KEY)
        db.audit("user", "ai:key", "", "set" if key else "cleared")
        return jsonify(ai.get_config())

    @app.post("/api/ai/chat")
    @security.require_auth
    @security.require_csrf
    def api_ai_chat():
        data = request.get_json(silent=True) or {}
        messages = data.get("messages") or []
        clean = [{"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                 for m in messages if isinstance(m, dict)]
        return jsonify(ai.respond(clean))

    @app.post("/api/ai/explain")
    @security.require_auth
    @security.require_csrf
    def api_ai_explain():
        data = request.get_json(silent=True) or {}
        return jsonify(ai.explain(str(data.get("tool", "a tool")),
                                  str(data.get("output", ""))))

    return app


def tools_target(payload: dict) -> str:
    for key in ("target", "url", "name"):
        if payload.get(key):
            return str(payload[key])
    return ""
