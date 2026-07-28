#!/usr/bin/env python3
"""Self-check for transcript-to-test.

1. Build a synthetic OpenAI messages transcript.
2. Generate a pytest regression test.
3. Run the generated test under pytest; assert it passes.
4. Mutate one stubbed tool result in the generated test.
5. Re-run pytest; assert it fails.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Make the local package importable without installing it.
sys.path.insert(0, os.path.dirname(__file__))

from transcript_to_test.cli import main as cli_main


TRANSCRIPT = [
    {"role": "user", "content": "What is 2+2?"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "calc", "arguments": '{"expr":"2+2"}'}},
    ]},
    {"role": "tool", "tool_call_id": "call_1", "content": "4"},
    {"role": "assistant", "content": "The answer is 4."},
]


JSON_TRANSCRIPT = [
    {"role": "user", "content": "Return JSON for 2+2"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "calc", "arguments": '{"expr":"2+2"}'}},
    ]},
    {"role": "tool", "tool_call_id": "call_1", "content": "4"},
    {"role": "assistant", "content": '{"result": 4, "status": "ok"}'},
]


def _run_pytest(test_path):
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "-q"],
        capture_output=True,
        text=True,
    )


def _check_template(tmp, transcript, template, value=None, pattern=None, framework="pytest"):
    """Generate a test with the given template and assert it passes."""
    transcript_path = tmp / f"t_{template}.json"
    test_path = tmp / f"test_{template}.py"
    transcript_path.write_text(json.dumps(transcript), encoding="utf-8")

    args = [
        str(transcript_path),
        "-o", str(test_path),
        "--framework", framework,
        "--assert-template", template,
    ]
    if value is not None:
        args.extend(["--assert-value", value])
    if pattern is not None:
        args.extend(["--assert-pattern", pattern])

    rc = cli_main(args)
    assert rc == 0, f"CLI exited {rc} for template {template}"
    assert test_path.exists(), f"generated test file missing for template {template}"

    result = _run_pytest(test_path)
    assert result.returncode == 0, (
        f"generated test failed unexpectedly for template {template}:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return test_path


def check_detect():
    """Auto-detection covers all supported formats."""
    from transcript_to_test.detect import detect
    from transcript_to_test.readers import codex

    def L(o):
        return json.dumps(o)

    codex_text = "\n".join([
        L({"type": "session_meta", "payload": {"base_instructions": {"text": "You are Codex."}}}),
        L({"type": "response_item", "payload": {"type": "message", "role": "user",
           "content": [{"type": "input_text", "text": "hi"}]}}),
        L({"type": "response_item", "payload": {"type": "message", "role": "assistant",
           "content": [{"type": "output_text", "text": "hello"}]}}),
    ]) + "\n"
    name, module = detect(codex_text)
    assert name == "codex_jsonl", name
    assert module is codex, module
    turns = module.parse(codex_text)
    assert any(t["role"] == "assistant" for t in turns), turns


def check_tape():
    """agent-vcr tape -> canonical turns.

    The fixture uses a body that is a JSON **string**, because that is what
    agent-vcr actually writes — it records the raw wire text. The reader
    previously assumed a dict and raised AttributeError on every real tape;
    nothing caught it because there was no tape coverage here at all.
    """
    from transcript_to_test.readers import tape

    def L(o):
        return json.dumps(o)

    req = L({"system": "You are careful.",
             "messages": [{"role": "user", "content": "audit this repo"}]})
    text = "\n".join([
        L({"kind": "model_request", "seq": 1, "provider": "anthropic", "body": req}),
        L({"kind": "tool_call", "seq": 2, "server": "fs", "tool": "read",
           "args": {"p": "/a.py"}, "args_hash": "h1"}),
        L({"kind": "tool_result", "seq": 3, "server": "fs", "tool": "read",
           "args_hash": "h1", "result": {"text": "x = 1"}}),
        L({"kind": "model_response", "seq": 4, "provider": "anthropic",
           "body": L({"content": [{"type": "text", "text": "Found it."}]})}),
    ]) + "\n"

    turns = tape.parse(text)
    assert turns, "tape reader returned no turns"
    roles = [t["role"] for t in turns]
    assert roles[0] == "user", f"first turn should be the initial prompt, got {roles}"
    assert "assistant" in roles, f"expected an assistant turn, got {roles}"
    joined = json.dumps(turns, default=str)
    assert "Found it." in joined, "assistant text lost when body was a JSON string"
    assert "audit this repo" in joined, "initial prompt lost when body was a JSON string"


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        transcript_path = tmp / "synthetic.json"
        test_path = tmp / "test_synthetic.py"
        transcript_path.write_text(json.dumps(TRANSCRIPT), encoding="utf-8")

        # 1. Generate the test.
        rc = cli_main([
            str(transcript_path),
            "-o", str(test_path),
            "--framework", "pytest",
        ])
        assert rc == 0, f"CLI exited {rc}"
        assert test_path.exists(), "generated test file missing"

        # 2. Run generated test; it must pass.
        result = _run_pytest(test_path)
        assert result.returncode == 0, (
            f"generated test failed unexpectedly:\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

        # 3. Mutate the stubbed tool result.
        source = test_path.read_text(encoding="utf-8")
        mutated = re.sub(
            r"(\('calc',\s*'\{\"expr\":\"2\+2\"\}'\)\s*:\s*)'4'",
            r"\1'5'",
            source,
        )
        assert mutated != source, "mutation did not change the generated test"
        test_path.write_text(mutated, encoding="utf-8")

        # 4. Re-run; it must now fail because the recorded result is still 4.
        result = _run_pytest(test_path)
        assert result.returncode != 0, (
            "mutated test should have failed but passed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        assert "returned" in (result.stdout + result.stderr).lower() or "assert" in (
            result.stdout + result.stderr).lower(), (
            f"expected an assertion failure, got:\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

        # Tier-2 template checks.
        _check_template(tmp, JSON_TRANSCRIPT, "json-path", value="$.result", pattern="4")
        _check_template(tmp, TRANSCRIPT, "no-error")
        _check_template(tmp, JSON_TRANSCRIPT, "structured-match", pattern='{"result": 4}')
        # Verify no-error still catches a mutated tool result.
        no_error_path = _check_template(tmp, TRANSCRIPT, "no-error")
        source = no_error_path.read_text(encoding="utf-8")
        mutated = re.sub(
            r"(\('calc',\s*'\{\"expr\":\"2\+2\"\}'\)\s*:\s*)'4'",
            r"\1'5'",
            source,
        )
        assert mutated != source, "mutation did not change the no-error generated test"
        no_error_path.write_text(mutated, encoding="utf-8")
        result = _run_pytest(no_error_path)
        assert result.returncode != 0, (
            "mutated no-error test should have failed but passed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    check_tape()
    check_detect()

    print("selfcheck OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
