"""Claude Code JSONL reader.

# ponytail: duplicates the Claude Code parser shape from transcript-bridge. A
# shared helper could be extracted later; for v1 each tool keeps its own parser
# so it stays standalone.
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
                and record.get("type") in ("user", "assistant", "system", "tool")
                and "message" in record)
    return False


def _blocks_of_type(content, block_type):
    if not isinstance(content, list):
        return None
    blocks = [b for b in content if isinstance(b, dict) and b.get("type") == block_type]
    return blocks or None


def parse(text):
    turns = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("type") not in ("user", "assistant", "system", "tool"):
            continue
        message = record.get("message", {})
        content = message.get("content")
        role = message.get("role", record.get("type"))
        tool_use_blocks = _blocks_of_type(content, "tool_use")
        tool_calls = None
        if tool_use_blocks:
            tool_calls = [{
                "id": b.get("id"),
                "type": "function",
                "function": {
                    "name": b.get("name"),
                    "arguments": json.dumps(b.get("input", {}), ensure_ascii=False),
                },
            } for b in tool_use_blocks]
        tool_result_blocks = _blocks_of_type(content, "tool_result")

        if role in ("user", "tool") and tool_result_blocks:
            # In Claude Code JSONL, tool results ride inside the next user
            # message. Normalise them to standalone tool turns so the canonical
            # shape matches OpenAI messages.
            # ponytail: user text mixed with tool_result blocks is dropped; v1
            # assumes the user turn is only carrying the recorded results.
            for b in tool_result_blocks:
                turns.append(make_turn(
                    role="tool",
                    content=[{"type": "tool_result",
                              "tool_use_id": b.get("tool_use_id"),
                              "content": b.get("content")}],
                    tool_results=[{"tool_use_id": b.get("tool_use_id"),
                                   "content": b.get("content")}],
                    provider=record.get("provider", "anthropic"),
                    ts=record.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                ))
            continue

        turns.append(make_turn(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_results=None,
            provider=record.get("provider", "anthropic"),
            model=message.get("model") or record.get("model"),
            ts=record.get("timestamp") or datetime.now(timezone.utc).isoformat(),
        ))
    return turns
