"""Canonical intermediate envelope and JSONL helpers.

Shape mirrors transcript-bridge/agent-checkpoint so the three projects stay
conceptually aligned. This module only carries the fields transcript-to-test
needs; it does not implement the full loss model.
"""
import json
from datetime import datetime, timezone


def make_turn(role, content, *, tool_calls=None, tool_results=None,
              provider=None, model=None, ts=None):
    return {
        "role": role,
        "content": content,
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "provider": provider,
        "model": model,
        "ts": ts or datetime.now(timezone.utc).isoformat(),
    }


def read_jsonl(text):
    turns = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        turns.append(json.loads(line))
    return turns


def write_jsonl(turns):
    lines = []
    for turn in turns:
        lines.append(json.dumps(turn, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines) + "\n" if lines else ""
