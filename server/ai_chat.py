"""Enhanced Chat Backend.

Provides chat completion with tool context, streaming support, conversation
persistence, and tool call handling.
"""
from __future__ import annotations

import json as _json
from collections.abc import Generator
from typing import Any

import server.ai_providers as providers
import server.db as db
from server.mcp_client import MCPClient

SYSTEM_PROMPT = (
    "You are the assistant inside 'Kali Linux Windows Substitute', a learning "
    "and authorised-testing toolkit. Be concise and practical. Explain commands "
    "in plain English and always remind the user to test only systems they own "
    "or are authorised to test.\n\n"
    "If - and only if - the user clearly asks you to run a tool, reply with a "
    'single JSON object and nothing else, of the form '
    '{"action":"run","tool":"<tool id>","payload":{...}} '
    "where payload matches that tool's form fields. Otherwise reply in prose."
)


def build_system_prompt(available_tools: list[str] | None = None) -> str:
    """Build the system prompt with available tools context."""
    base = SYSTEM_PROMPT
    if available_tools:
        tools_str = ", ".join(available_tools)
        base += f"\n\nAvailable tools: {tools_str}"
    return base


def _parse_action(text: str) -> dict[str, Any] | None:
    """Parse an AI response for a JSON action."""
    candidate = text.strip()
    if not candidate.startswith("{") or '"action"' not in candidate:
        return None
    if not candidate.endswith("}"):
        return None
    try:
        obj = _json.loads(candidate)
    except _json.JSONDecodeError:
        return None
    if obj.get("action") in ("run", "mcp_call"):
        return obj
    return None


def complete_with_context(
    messages: list[dict[str, str]],
    tools_context: list[str] | None = None,
    provider_type: str = "ollama",
    provider_config: dict[str, Any] | None = None,
    mcp_client: MCPClient | None = None,
    conversation_id: int | None = None,
) -> dict[str, Any]:
    """Complete a chat with tool context and optional tool call execution.
    
    Args:
        messages: List of {role, content} dicts
        tools_context: List of available tool IDs
        provider_type: Type of provider to use
        provider_config: Provider configuration dict
        mcp_client: Optional MCP client for tool calls
        conversation_id: Optional conversation ID for persistence
    
    Returns:
        dict with 'type' (message/action), 'text', and optional tool result
    """
    cfg = provider_config or {}
    provider = providers.get_provider(provider_type, cfg)
    
    # Build system prompt with tool context
    system_msg = {
        "role": "system",
        "content": build_system_prompt(tools_context),
    }
    
    # Prepend system message if not already present
    if not messages or messages[0].get("role") != "system":
        full_messages = [system_msg, *messages]
    else:
        full_messages = messages
    
    text = provider.complete(full_messages)
    
    # Check if the response contains an action to execute
    action = _parse_action(text)
    if action:
        if action["action"] == "run":
            tool_id = str(action.get("tool", ""))
            payload = action.get("payload", {})
            result = handle_tool_call({}, tool_id, payload)
            if conversation_id:
                save_message("assistant", text, tool_id=tool_id,
                             conversation_id=conversation_id)
            return {"type": "action", "text": text, "tool": tool_id,
                    "payload": payload, "result": result}
        if action["action"] == "mcp_call" and mcp_client:
            tool_name = str(action.get("tool", ""))
            arguments = action.get("arguments", {})
            result = mcp_client.call_tool(tool_name, arguments)
            if conversation_id:
                save_message("assistant", text, tool_id=tool_name,
                             conversation_id=conversation_id)
            return {"type": "action", "text": text, "tool": tool_name,
                    "payload": arguments, "result": result}
    
    if conversation_id:
        save_message("assistant", text, conversation_id=conversation_id)
    
    return {"type": "message", "text": text}


def stream_complete(
    messages: list[dict[str, str]],
    provider_type: str = "ollama",
    provider_config: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Stream a chat completion (generator yielding text chunks).
    
    Currently falls back to non-streaming since most providers don't support
    streaming through this interface. Future implementations will use
    proper streaming APIs.
    """
    cfg = provider_config or {}
    provider = providers.get_provider(provider_type, cfg)
    
    text = provider.complete(messages)
    # Yield in chunks to simulate streaming
    chunk_size = 32
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


def handle_tool_call(action: dict[str, Any], tool_id: str,
                   payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a tool call by routing to the runtime agent.
    
    Args:
        action: The action dict from the AI
        tool_id: Tool ID to run
        payload: Tool payload
    
    Returns:
        dict with result
    """
    import server.config as config
    import server.tools as tools
    
    cfg = config.load()
    
    # Build the tool request
    result, status = tools.run(cfg, tool_id, payload)
    return {
        "tool": tool_id,
        "payload": payload,
        "result": result,
        "status": status,
    }


def execute_skill(skill_name: str, params: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Execute a predefined skill by name."""
    from server.skills import execute_skill as _exec
    return _exec(skill_name, params)


def suggest_next_skill(tool_id: str, target: str) -> str | None:
    """Suggest the next skill to run after a tool completes."""
    from server.skills import suggest_skills
    suggestions = suggest_skills({"tool": tool_id, "target": target})
    if suggestions:
        return suggestions[0].get("name", "")
    return None


def save_message(
    role: str,
    content: str,
    tool_id: str = "",
    target: str = "",
    conversation_id: int | None = None,
) -> int:
    """Save a chat message to the conversations table.
    
    Args:
        role: Message role (user, assistant, system)
        content: Message content
        tool_id: Associated tool ID
        target: Associated target
        conversation_id: Conversation ID (None for new conversation)
    
    Returns:
        Message ID
    """
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (created, role, content, tool, target) "
            "VALUES (?,?,?,?,?)",
            (db._now(), role, content, tool_id or "", target or ""),
        )
        return int(cur.lastrowid or 0)


def load_conversation(id: int) -> list[dict[str, Any]]:
    """Load all messages for a conversation."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conversations WHERE id = ? ORDER BY id ASC",
            (id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_conversations(limit: int = 100) -> list[dict[str, Any]]:
    """List conversations with preview of last message."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT c.id, c.created, c.role, c.content, c.tool, c.target "
            "FROM conversations c "
            "INNER JOIN ("
            "    SELECT id, MAX(id) as max_id "
            "    FROM conversations "
            "    GROUP BY id "
            ") sub ON c.id = sub.id AND c.id = sub.max_id "
            "ORDER BY c.id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_conversation(id: int) -> bool:
    """Delete a conversation and all its messages."""
    with db.connect() as conn:
        cur = conn.execute("DELETE FROM conversations WHERE id = ?", (id,))
        return cur.rowcount > 0


def new_conversation() -> int:
    """Start a new conversation and return its ID."""
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO conversations (created, role, content, tool, target) "
            "VALUES (?,?,?,?,?)",
            (db._now(), "system", "New conversation", "", ""),
        )
        return int(cur.lastrowid or 0)
