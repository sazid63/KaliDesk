"""Flask application factory and routes.

Loopback only. Every ``/api/`` route requires the bearer cookie; every
state-changing route also requires the CSRF header. The browser UI is a static
single page served from ``ui/``.
"""
from __future__ import annotations

import hmac
from pathlib import Path

from flask import Flask, jsonify, make_response, request, send_from_directory

import kws.paths as kws_paths
import server.achievements as achievements
import server.ai as ai
import server.ai_chat as ai_chat
import server.ai_providers as ai_providers
import server.catalog as catalog
import server.cheat_sheets as cheat_sheets
import server.commands as commands
import server.container_runtime as container_runtime
import server.db as db
import server.history as history
import server.local_ai as local_ai
import server.mcp_client as mcp_client
import server.notebook as notebook
import server.onboarding as onboarding
import server.playground as playground
import server.portable as portable
import server.recordings as recordings
import server.report as report
import server.security as security
import server.skills as skills
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
        import time as _time
        payload = request.get_json(silent=True) or {}
        target = tools_target(payload)
        start = _time.time()
        result, status = tools.run(cfg, tool_id, payload)
        duration_ms = round((_time.time() - start) * 1000, 1)
        rc = 0 if status == 200 else status
        output_preview = ""
        if isinstance(result, dict):
            output_preview = str(result.get("output", result.get("detail", "")))[:500]
        history.record_run(tool_id, target, payload, rc, duration_ms,
                           output_preview, status == 200)
        db.audit("user", f"tool:{tool_id}", target,
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
        import kws.secrets as kws_secrets

        data = request.get_json(silent=True) or {}
        key = str(data.get("api_key", "")).strip()
        if key:
            kws_secrets.set_secret(ai.SECRET_KEY, key)
        else:
            kws_secrets.delete_secret(ai.SECRET_KEY)
        db.audit("user", "ai:key", "", "set" if key else "cleared")
        return jsonify(ai.get_config())

    @app.post("/api/ai/explain")
    @security.require_auth
    @security.require_csrf
    def api_ai_explain():
        data = request.get_json(silent=True) or {}
        return jsonify(ai.explain(str(data.get("tool", "a tool")),
                                  str(data.get("output", ""))))

    # --- AI Providers -------------------------------------------------------
    @app.get("/api/ai/providers")
    @security.require_auth
    def api_ai_providers_list():
        return jsonify({"providers": ai_providers.list_configured_providers()})

    @app.post("/api/ai/providers")
    @security.require_auth
    @security.require_csrf
    def api_ai_providers_create():
        data = request.get_json(silent=True) or {}
        ptype = str(data.get("type", "")).strip()
        if not ptype:
            return jsonify({"error": "provider type is required"}), 400
        config = data.get("config", {})
        if not isinstance(config, dict):
            return jsonify({"error": "config must be an object"}), 400
        ai_providers.save_provider_config(ptype, config)
        return jsonify({"ok": True, "type": ptype})

    @app.delete("/api/ai/providers/<name>")
    @security.require_auth
    @security.require_csrf
    def api_ai_providers_delete(name: str):
        ai_providers.delete_provider_config(name)
        return jsonify({"ok": True})

    @app.post("/api/ai/test")
    @security.require_auth
    @security.require_csrf
    def api_ai_test():
        data = request.get_json(silent=True) or {}
        ptype = str(data.get("type", "")).strip()
        config = data.get("config", {})
        try:
            provider = ai_providers.get_provider(ptype, config)
            ok, msg = provider.test_connection()
            return jsonify({"ok": ok, "message": msg, "models": provider.list_models()})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"ok": False, "message": str(exc)}), 500

    # --- AI Chat (enhanced) --------------------------------------------------
    @app.post("/api/ai/chat")
    @security.require_auth
    @security.require_csrf
    def api_ai_chat():
        data = request.get_json(silent=True) or {}
        messages = data.get("messages") or []
        clean = [{"role": str(m.get("role", "user")), "content": str(m.get("content", ""))}
                 for m in messages if isinstance(m, dict)]
        provider_type = str(data.get("provider", "ollama"))
        provider_config = data.get("provider_config", {})
        tools_context = data.get("tools_context", [])
        conversation_id = data.get("conversation_id")

        # Save user message
        if conversation_id:
            ai_chat.save_message("user", clean[-1].get("content", "") if clean else "",
                                 conversation_id=conversation_id)

        # Validate provider type
        valid_providers = {"openai", "anthropic", "gemini", "ollama", "localai", "deepseek", "opencode", "dsh"}
        if provider_type not in valid_providers:
            return jsonify({"error": f"Unknown provider: {provider_type}"}), 400

        # Get completion with optional MCP client
        mcp = mcp_client.MCPClient.auto_discover() if data.get("use_mcp") else None
        try:
            result = ai_chat.complete_with_context(
                clean, tools_context, provider_type, provider_config, mcp, conversation_id)
        except Exception as exc:
            return jsonify({"error": f"AI completion failed: {exc}"}), 503
        finally:
            if mcp:
                mcp.close()

        return jsonify(result)

    # --- Local AI Models -----------------------------------------------------
    @app.get("/api/ai/models")
    @security.require_auth
    def api_ai_models():
        models = local_ai.scan_models()
        return jsonify({"models": models})

    @app.post("/api/ai/models/download")
    @security.require_auth
    @security.require_csrf
    def api_ai_models_download():
        data = request.get_json(silent=True) or {}
        hf_repo = str(data.get("repo", "")).strip()
        filename = str(data.get("filename", "")).strip()
        quantization = str(data.get("quantization", "Q4_K_M")).strip()
        if not hf_repo or not filename:
            return jsonify({"error": "repo and filename are required"}), 400
        result = local_ai.download_model(hf_repo, filename, quantization)
        return jsonify(result)

    @app.delete("/api/ai/models/<name>")
    @security.require_auth
    @security.require_csrf
    def api_ai_models_delete(name: str):
        ok = local_ai.delete_model(name)
        return jsonify({"ok": ok})

    # --- AI Conversations ----------------------------------------------------
    @app.get("/api/ai/conversations")
    @security.require_auth
    def api_ai_conversations_list():
        limit = int(request.args.get("limit", "100"))
        return jsonify({"conversations": ai_chat.list_conversations(limit)})

    @app.post("/api/ai/conversations")
    @security.require_auth
    @security.require_csrf
    def api_ai_conversations_create():
        conv_id = ai_chat.new_conversation()
        return jsonify({"id": conv_id})

    @app.get("/api/ai/conversations/<int:conv_id>")
    @security.require_auth
    def api_ai_conversations_load(conv_id: int):
        messages = ai_chat.load_conversation(conv_id)
        return jsonify({"id": conv_id, "messages": messages})

    @app.delete("/api/ai/conversations/<int:conv_id>")
    @security.require_auth
    @security.require_csrf
    def api_ai_conversations_delete(conv_id: int):
        ok = ai_chat.delete_conversation(conv_id)
        return jsonify({"ok": ok})

    # --- MCP Servers --------------------------------------------------------
    @app.get("/api/mcp/servers")
    @security.require_auth
    def api_mcp_servers_list():
        import json as _json
        servers = []
        for key in ["mcp_servers"]:
            val = db.get_setting(key, "")
            if val:
                try:
                    servers = _json.loads(val)
                except _json.JSONDecodeError:
                    servers = []
        return jsonify({"servers": servers})

    @app.post("/api/mcp/servers")
    @security.require_auth
    @security.require_csrf
    def api_mcp_servers_create():
        import json as _json
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", ""))
        stype = str(data.get("type", "stdio"))
        config_val = data.get("config", {})
        if not name:
            return jsonify({"error": "name is required"}), 400
        existing = []
        current = db.get_setting("mcp_servers", "")
        if current:
            try:
                existing = _json.loads(current)
            except _json.JSONDecodeError:
                existing = []
        existing = [s for s in existing if s.get("name") != name]
        existing.append({"name": name, "type": stype, "config": config_val})
        db.set_setting("mcp_servers", _json.dumps(existing))
        return jsonify({"ok": True})

    @app.delete("/api/mcp/servers/<name>")
    @security.require_auth
    @security.require_csrf
    def api_mcp_servers_delete(name: str):
        import json as _json
        existing = []
        current = db.get_setting("mcp_servers", "")
        if current:
            try:
                existing = _json.loads(current)
            except _json.JSONDecodeError:
                existing = []
        existing = [s for s in existing if s.get("name") != name]
        db.set_setting("mcp_servers", _json.dumps(existing))
        return jsonify({"ok": True})

    @app.post("/api/mcp/servers/<name>/connect")
    @security.require_auth
    @security.require_csrf
    def api_mcp_servers_connect(name: str):
        import json as _json
        current = db.get_setting("mcp_servers", "")
        servers = []
        if current:
            try:
                servers = _json.loads(current)
            except _json.JSONDecodeError:
                servers = []
        server_cfg = None
        for s in servers:
            if s.get("name") == name:
                server_cfg = s
                break
        if server_cfg is None:
            return jsonify({"ok": False, "message": "server not found"}), 404
        mcp = mcp_client.MCPClient()
        if server_cfg.get("type") == "http":
            ok = mcp.connect_http(str(server_cfg.get("config", {}).get("url", "")))
        else:
            cmd = server_cfg.get("config", {}).get("command", [])
            if isinstance(cmd, str):
                cmd = [cmd]
            ok = mcp.connect_stdio(cmd)
        if ok:
            tools_list = mcp.list_tools()
            mcp.close()
            return jsonify({"ok": True, "tools": tools_list})
        return jsonify({"ok": False, "message": "connection failed"}), 500

    # --- Skills ---------------------------------------------------------------
    @app.get("/api/skills")
    @security.require_auth
    def api_skills_list():
        all_skills = skills.load_skills()
        return jsonify({"skills": [s.to_dict() for s in all_skills]})

    @app.post("/api/skills")
    @security.require_auth
    @security.require_csrf
    def api_skills_create():
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", ""))
        if not name:
            return jsonify({"error": "name is required"}), 400
        skill = skills.Skill(
            name=name,
            description=str(data.get("description", "")),
            category=str(data.get("category", "general")),
            tool_id=str(data.get("tool_id", "")),
            args_template=data.get("args_template", {}),
        )
        ok = skills.save_skill(skill)
        return jsonify({"ok": ok})

    @app.delete("/api/skills/<name>")
    @security.require_auth
    @security.require_csrf
    def api_skills_delete(name: str):
        ok = skills.delete_skill(name)
        return jsonify({"ok": ok})

    @app.post("/api/skills/<name>/execute")
    @security.require_auth
    @security.require_csrf
    def api_skills_execute(name: str):
        data = request.get_json(silent=True) or {}
        params = data.get("params", {})
        if not isinstance(params, dict):
            return jsonify({"error": "params must be an object"}), 400
        result, status = skills.execute_skill(name, params)
        db.audit("user", f"skill:{name}", "",
                 "ok" if status == 200 else f"status {status}")
        return jsonify(result), status

    @app.get("/api/ai/skills/suggest")
    @security.require_auth
    def api_ai_skills_suggest():
        tool_id = str(request.args.get("tool", ""))
        target = str(request.args.get("target", ""))
        if tool_id and target:
            suggestion = ai_chat.suggest_next_skill(tool_id, target)
            if suggestion:
                skill = skills.get_skill(suggestion)
                if skill:
                    return jsonify({"suggestion": skill.to_dict()})
        all_skills = skills.load_skills()
        if all_skills:
            return jsonify({"suggestion": all_skills[0].to_dict()})
        return jsonify({"suggestion": None})



    # --- Containers ----------------------------------------------------------

    @app.get("/api/containers/status")
    @security.require_auth
    def api_containers_status():
        return jsonify({
            "podman_installed": container_runtime.is_podman_installed(),
            "images": container_runtime.list_images(),
            "containers": container_runtime.list_containers(all=True)
        })

    @app.post("/api/containers/podman/install")
    @security.require_auth
    @security.require_csrf
    def api_install_podman():
        result = container_runtime.install_podman()
        db.audit("user", "container:install", result.get("message", ""), "ok" if result["ok"] else "failed")
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
        db.audit("user", "container:pull", name, "ok" if result["ok"] else f"status {result.get('rc', '')}")
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
        ports = data.get("ports", [])
        volumes = data.get("volumes", [])
        
        if not image or not name:
            return jsonify({"error": "Image and name required"}), 400
        
        result = container_runtime.run_container(image, name, ports, volumes)
        if result["ok"]:
            db.audit("user", "container:run", result.get("container_id", ""), f"image={image}")
        return jsonify(result), 200 if result["ok"] else 500

    @app.post("/api/containers/<container_id>/start")
    @security.require_auth
    @security.require_csrf
    def api_start_container(container_id):
        result = container_runtime.start_container(container_id)
        db.audit("user", "container:start", container_id, "ok" if result["ok"] else result.get("message", ""))
        return jsonify(result), 200 if result["ok"] else 500

    @app.post("/api/containers/<container_id>/stop")
    @security.require_auth
    @security.require_csrf
    def api_stop_container(container_id):
        result = container_runtime.stop_container(container_id)
        db.audit("user", "container:stop", container_id, "ok" if result["ok"] else result.get("message", ""))
        return jsonify(result), 200 if result["ok"] else 500

    @app.delete("/api/containers/<container_id>")
    @security.require_auth
    @security.require_csrf
    def api_remove_container(container_id):
        result = container_runtime.remove_container(container_id)
        db.audit("user", "container:remove", container_id, "ok" if result["ok"] else result.get("message", ""))
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
        if not cmd:
            return jsonify({"error": "Command required"}), 400
        result = container_runtime.exec_in_container(container_id, cmd)
        db.audit("user", "container:exec", container_id, " ".join(cmd))
        return jsonify(result), 200 if result["ok"] else 500
    # --- History ---
    @app.get("/api/history")
    @security.require_auth
    def api_history_list():
        limit = int(request.args.get("limit", "100"))
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

    @app.post("/api/achievements/<key>/unlock")
    @security.require_auth
    @security.require_csrf
    def api_achievements_unlock(key: str):
        ok = achievements.unlock_achievement(key)
        return jsonify({"ok": ok, "unlocked": ok})

    # --- Notebook ---
    @app.get("/api/notebook/entries")
    @security.require_auth
    def api_notebook_list():
        type_filter = request.args.get("type")
        tags_filter = request.args.get("tags")
        limit = int(request.args.get("limit", "100"))
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
        if not content:
            return jsonify({"error": "content required"}), 400
        eid = notebook.add_entry(entry_type, content, tags)
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

    # --- Recordings ---
    @app.get("/api/recordings")
    @security.require_auth
    def api_recordings_list():
        return jsonify({"recordings": recordings.list_recordings()})

    @app.post("/api/recordings/start")
    @security.require_auth
    @security.require_csrf
    def api_recordings_start():
        data = request.get_json(silent=True) or {}
        tool = data.get("tool", "unknown")
        argv = data.get("argv", {})
        rid = recordings.start_recording(tool, argv)
        return jsonify({"recording_id": rid})

    @app.post("/api/recordings/stop")
    @security.require_auth
    @security.require_csrf
    def api_recordings_stop():
        data = request.get_json(silent=True) or {}
        rid = data.get("recording_id")
        if not rid:
            return jsonify({"error": "recording_id required"}), 400
        ok = recordings.stop_recording(rid)
        return jsonify({"ok": ok})

    @app.get("/api/recordings/<rid>")
    @security.require_auth
    def api_recordings_load(rid: str):
        lines = recordings.load_recording(rid)
        return jsonify({"lines": lines})

    @app.delete("/api/recordings/<rid>")
    @security.require_auth
    @security.require_csrf
    def api_recordings_delete(rid: str):
        ok = recordings.delete_recording(rid)
        return jsonify({"ok": ok})

    # --- Onboarding ---
    @app.get("/api/onboarding/status")
    @security.require_auth
    def api_onboarding_status():
        return jsonify({
            "needed": onboarding.is_onboarding_needed(),
            "steps": onboarding.onboarding_steps(),
        })

    @app.post("/api/onboarding/finish")
    @security.require_auth
    @security.require_csrf
    def api_onboarding_finish():
        ok = onboarding.finish_onboarding()
        return jsonify({"ok": ok})

    # --- Portable Mode ---
    app.register_blueprint(portable.portable_bp, url_prefix="/api/portable")

    return app

def tools_target(payload: dict) -> str:
    for key in ("target", "url", "name"):
        if payload.get(key):
            return str(payload[key])
    return ""