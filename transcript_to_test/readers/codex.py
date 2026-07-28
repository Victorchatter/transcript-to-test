"""Codex rollout JSONL reader.

# ponytail: Codex rollout transcripts are JSONL with `type` in
# {session_meta, response_item, event_msg}. We turn them into canonical turns
# by tracking messages, reasoning, function calls, and outputs.
"""
import json
from datetime import datetime, timezone

from ..canonical import make_turn


_CODEX_TYPES = {"session_meta", "response_item", "event_msg"}


def sniff(text):
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return False
        return (isinstance(record, dict)
                and (record.get("type") in _CODEX_TYPES
                     or "payload" in record and isinstance(record.get("payload"), dict)))
    return False


def _content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text", ""))
        return "\n".join(parts)
    return ""


def parse(text):
    turns = []
    pending_calls = {}  # call_id -> tool_name
    current_assistant = None
    now = datetime.now(timezone.utc).isoformat()

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = record.get("type")
        p = record.get("payload") if isinstance(record.get("payload"), dict) else {}

        if t == "session_meta":
            bi = p.get("base_instructions") or {}
            sys_text = bi.get("text", "")
            if sys_text:
                turns.append(make_turn(role="system", content=sys_text,
                                       provider="codex", ts=now))
            continue

        if t == "response_item":
            pt = p.get("type")
            if pt == "message":
                role = p.get("role")
                content_text = _content_text(p.get("content"))
                if role == "user":
                    turns.append(make_turn(role="user", content=content_text,
                                           provider="codex", ts=now))
                elif role == "assistant":
                    current_assistant = make_turn(role="assistant", content=content_text,
                                                  provider="codex", ts=now)
                    turns.append(current_assistant)
                elif role == "system" and content_text:
                    turns.append(make_turn(role="system", content=content_text,
                                           provider="codex", ts=now))
            elif pt == "reasoning":
                reasoning_text = " ".join(
                    s.get("text", "") for s in p.get("summary", []) if isinstance(s, dict)
                )
                if reasoning_text and current_assistant is not None:
                    current_assistant.setdefault("reasoning", "")
                    current_assistant["reasoning"] += reasoning_text
            elif pt == "function_call":
                name = p.get("name", "?")
                args = p.get("arguments", "")
                call_id = p.get("call_id")
                if current_assistant is None:
                    current_assistant = make_turn(role="assistant", content="",
                                                  provider="codex", ts=now)
                    turns.append(current_assistant)
                tc = {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                }
                current_assistant.setdefault("tool_calls", [])
                current_assistant["tool_calls"].append(tc)
                if call_id:
                    pending_calls[call_id] = name
            elif pt == "function_call_output":
                call_id = p.get("call_id")
                name = pending_calls.get(call_id, "?")
                output = p.get("output", "")
                turns.append(make_turn(
                    role="tool",
                    content=[{"type": "tool_result", "tool_use_id": call_id, "content": output}],
                    tool_results=[{"tool_use_id": call_id, "content": output}],
                    provider="codex",
                    ts=now,
                ))

    return turns
