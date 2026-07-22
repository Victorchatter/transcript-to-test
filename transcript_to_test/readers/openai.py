"""OpenAI messages reader.

# ponytail: duplicates the OpenAI parser shape from transcript-bridge. A shared
# helper could live in one of the three sibling projects later; for v1 each tool
# keeps its own parser so it stays standalone.
"""
import json
from datetime import datetime, timezone

from ..canonical import make_turn


def sniff(text):
    return text.lstrip().startswith("[")


def parse(text):
    messages = json.loads(text)
    if not isinstance(messages, list):
        raise ValueError("OpenAI messages input must be a JSON array")
    now = datetime.now(timezone.utc).isoformat()
    turns = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        tool_calls = None
        tool_results = None
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
        elif role == "tool":
            tool_results = [{
                "tool_use_id": msg.get("tool_call_id"),
                "content": content,
            }]
            # Normalise to Anthropic-style block for internal consistency.
            content = [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id"), "content": content}]
        turns.append(make_turn(
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            provider="openai",
            ts=now,
        ))
    return turns
