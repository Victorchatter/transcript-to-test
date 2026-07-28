"""Unit tests for transcript format auto-detection."""
import json

import pytest

from transcript_to_test.detect import FORMATS, detect


def _L(o):
    return json.dumps(o)


def test_detect_agent_vcr_tape():
    text = "\n".join([
        _L({"kind": "model_request", "seq": 1, "provider": "anthropic",
            "body": _L({"model": "claude", "messages": [{"role": "user", "content": "hi"}]})}),
        _L({"kind": "model_response", "seq": 1, "provider": "anthropic",
            "body": _L({"content": [{"type": "text", "text": "hello"}]})}),
    ]) + "\n"
    name, module = detect(text)
    assert name == "agent_vcr_tape"
    turns = module.parse(text)
    assert any(t["role"] == "assistant" for t in turns)


def test_detect_claude_code_jsonl():
    text = "\n".join([
        _L({"type": "last-prompt"}),
        _L({"type": "user", "message": {"role": "user", "content": "hi"}}),
        _L({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hello"}]}}),
    ]) + "\n"
    name, module = detect(text)
    assert name == "claude_code_jsonl"
    turns = module.parse(text)
    assert any(t["role"] == "assistant" for t in turns)


def test_detect_openai_messages():
    text = json.dumps([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ])
    name, module = detect(text)
    assert name == "openai_messages"
    turns = module.parse(text)
    assert len(turns) == 2


def test_detect_codex_jsonl():
    text = "\n".join([
        _L({"type": "session_meta", "payload": {"base_instructions": {"text": "You are Codex."}}}),
        _L({"type": "response_item", "payload": {"type": "message", "role": "user",
           "content": [{"type": "input_text", "text": "hi"}]}}),
        _L({"type": "response_item", "payload": {"type": "message", "role": "assistant",
           "content": [{"type": "output_text", "text": "hello"}]}}),
    ]) + "\n"
    name, module = detect(text)
    assert name == "codex_jsonl"
    turns = module.parse(text)
    assert any(t["role"] == "assistant" for t in turns)


def test_detect_unrecognized():
    with pytest.raises(ValueError, match="unrecognized"):
        detect("not a transcript\n")


def test_formats_list_has_all_readers():
    names = {name for name, _ in FORMATS}
    assert names == {"agent_vcr_tape", "claude_code_jsonl", "openai_messages", "codex_jsonl"}
