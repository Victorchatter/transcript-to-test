"""Minimal deterministic reference agent loop.

# ponytail: duplicates the reference-loop shape needed by agent-checkpoint. Both
# projects could share one module later; for v1 the loop is inlined into the
# generated test so the output file stays standalone.
"""
import json


def _text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [item.get("text", "") for item in content
                 if isinstance(item, dict) and item.get("type") == "text"]
        return "".join(texts)
    return str(content) if content is not None else ""


def _assistant_message(turn):
    """Convert a canonical assistant turn into an OpenAI-style message."""
    msg = {"role": "assistant", "content": _text_of(turn.get("content"))}
    if turn.get("tool_calls"):
        msg["tool_calls"] = turn["tool_calls"]
    return msg


def run_agent(messages, tool_registry, expected_turns):
    """Replay assistant/tool turns using stubbed tools.

    - messages: list seeded with the initial user prompt.
    - tool_registry: dict mapping (tool_name, canonical_json(args)) -> result.
    - expected_turns: assistant and tool turns from the transcript, in order.

    Returns the final assistant text. Raises AssertionError if a stubbed result
    diverges from the recorded result.
    """
    i = 0
    while i < len(expected_turns):
        turn = expected_turns[i]
        if turn["role"] != "assistant":
            i += 1
            continue

        messages.append(_assistant_message(turn))
        tool_calls = turn.get("tool_calls") or []

        for tc in tool_calls:
            i += 1
            tool_turn = expected_turns[i]
            assert tool_turn["role"] == "tool", f"expected tool turn, got {tool_turn['role']}"
            expected_result = tool_turn["tool_results"][0]["content"]

            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            key = (name, json.dumps(args, sort_keys=True, separators=(",", ":")))
            actual_result = tool_registry[key]

            assert actual_result == expected_result, (
                f"Tool {name}({args!r}) returned {actual_result!r}, "
                f"expected recorded result {expected_result!r}"
            )

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": actual_result,
            })

        if not tool_calls:
            return _text_of(turn.get("content"))

        i += 1

    raise RuntimeError("no final assistant turn found in expected_turns")
