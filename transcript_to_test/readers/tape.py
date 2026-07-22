"""agent-vcr tape reader.

# ponytail: agent-vcr is a wire-level format with model_request/response and
# tool_call/result envelopes. This reader covers the common Claude Code +
# Anthropic Messages shape and a basic OpenAI chat-completions shape. Tapes
# with exotic provider bodies may need format-specific expansion.
"""
import json
from datetime import datetime, timezone

from ..canonical import make_turn


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
                and record.get("kind") in ("model_request", "model_response",
                                           "tool_call", "tool_result"))
    return False


def parse(text):
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        events.append(json.loads(line))

    by_seq = {}
    for ev in events:
        seq = ev.get("seq")
        if seq is None:
            continue
        by_seq.setdefault(seq, []).append(ev)

    turns = []
    pending_tool_ids = []
    now = datetime.now(timezone.utc).isoformat()

    for seq in sorted(by_seq):
        group = by_seq[seq]
        model_response = next((e for e in group if e.get("kind") == "model_response"), None)
        tool_call = next((e for e in group if e.get("kind") == "tool_call"), None)
        tool_result = next((e for e in group if e.get("kind") == "tool_result"), None)

        if model_response:
            provider = model_response.get("provider", "anthropic")
            content, tool_calls = _parse_model_response(model_response)
            turns.append(make_turn(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
                provider=provider,
                ts=now,
            ))
            pending_tool_ids = [tc.get("id") for tc in (tool_calls or [])]

        if tool_call and tool_result:
            tool_use_id = pending_tool_ids.pop(0) if pending_tool_ids else None
            result = tool_result.get("result", {})
            content_text = _extract_result_text(result)
            turns.append(make_turn(
                role="tool",
                content=[{"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text}],
                tool_results=[{"tool_use_id": tool_use_id, "content": content_text}],
                provider=tool_call.get("server", "mcp"),
                ts=now,
            ))

    first_req = next((e for e in events if e.get("kind") == "model_request"), None)
    if first_req:
        user_content = _extract_initial_prompt(first_req)
        if user_content:
            turns.insert(0, make_turn(role="user", content=user_content,
                                       provider=first_req.get("provider", "anthropic"), ts=now))

    return turns


def _parse_model_response(ev):
    body = ev.get("body", {})
    provider = ev.get("provider", "anthropic")
    if provider == "openai" or "choices" in body:
        return _parse_openai_response(body)
    return _parse_anthropic_response(body)


def _parse_anthropic_response(body):
    content = body.get("content", [])
    tool_calls = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_calls.append({
                "id": block.get("id"),
                "type": "function",
                "function": {
                    "name": block.get("name"),
                    "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                },
            })
    return content, tool_calls or None


def _parse_openai_response(body):
    message = body.get("choices", [{}])[0].get("message", {})
    content = message.get("content")
    tool_calls = message.get("tool_calls")
    if tool_calls:
        blocks = []
        if content:
            blocks.append({"type": "text", "text": content})
        for tc in tool_calls:
            func = tc.get("function", {})
            blocks.append({
                "type": "tool_use",
                "id": tc.get("id"),
                "name": func.get("name"),
                "input": _parse_args(func.get("arguments")),
            })
        content = blocks
    return content, tool_calls


def _parse_args(args):
    if args is None:
        return {}
    if isinstance(args, str):
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {"_raw": args}
    return args


def _extract_result_text(result):
    if isinstance(result, str):
        return result
    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content
                 if isinstance(item, dict) and item.get("type") == "text"]
        return "".join(texts) if texts else json.dumps(result, ensure_ascii=False)
    if isinstance(content, str):
        return content
    return json.dumps(result, ensure_ascii=False)


def _extract_initial_prompt(req):
    body = req.get("body", {})
    messages = body.get("messages", [])
    if messages and isinstance(messages[0], dict):
        return messages[0].get("content")
    return body.get("prompt")
