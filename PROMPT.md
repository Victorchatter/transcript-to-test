# transcript-to-test — bootstrap session prompt

You are bootstrapping a new open-source project. Follow the full process: `superpowers:brainstorming` → lock design → write spec to `docs/superpowers/specs/YYYY-MM-DD-transcript-to-test-design.md` → commit → `superpowers:writing-plans` (approve) → implement via `superpowers:executing-plans`. Verify with `selfcheck.py` before done.

## Idea (one-liner)
Turn one recorded successful agent run into a regression test. Given a transcript (Claude Code JSONL / OpenAI messages — or an agent-vcr tape), extract the sequence of tool calls + their recorded results, and emit a pytest-style fixture/test that re-runs the agent with those tools *stubbed* to return the recorded results, then asserts on the final assistant answer. Pairs naturally with agent-vcr's tape format (read it directly when the input is a tape).

## Why it doesn't exist
Agent eval frameworks are heavy and pull in a runtime. This is one script that turns a real run into one regression test you can drop in `tests/`. No framework, no fixtures ceremony.

## Hard constraints
- Python, `pipx install .`. Fully local/offline, no telemetry.
- Input: a transcript file (Claude Code JSONL or OpenAI messages) or an agent-vcr tape (`.jsonl` with agent-vcr's event envelopes). Reuse transcript-bridge's parser shape where free; do not fork parsers if a shared helper can be extracted later — v1 can duplicate minimally with a `# ponytail: duplicates X parser, unify later` note.
- Output: a generated `test_<name>.py` that (a) builds a stubbed tool registry from the recorded `(tool, args) -> result` pairs, (b) re-runs a *reference agent loop* (the same minimal one used by agent-checkpoint — keep these consistent) with those stubs, (c) asserts the final assistant message equals (or contains) the recorded final answer.
- Assertion style: exact-match by default, with `--assert-contains` / `--assert-regex` for flaky-allowing variants. Document the tradeoff (exact is the regression net; contains is the smoke test).
- CLI: `transcript-to-test <transcript> -o tests/test_<name>.py [--assert contains|exact|regex PATTERN] [--framework pytest|unittest]`. Default `pytest`. The generated test has *no* dependency on transcript-to-test itself — it's a standalone file.
- Small and sharp. Ponytail: stdlib + (optionally) `pytest` as a dev dependency only, shortest working diff. `# ponytail:` comments on simplifications.
- One `selfcheck.py`: generate a test from a synthetic transcript, run it under pytest in a tmp dir, assert it passes; mutate one stubbed result, re-run, assert it fails (proving the test catches regressions).
- License MIT. README with a "turn last night's run into a test" example.

## Scope / YAGNI (v1)
Ship: Claude Code JSONL + OpenAI messages + agent-vcr tape inputs, pytest + unittest output, exact/contains/regex assertions, standalone generated tests. Out: multi-run fuzzing, coverage of tool-call *ordering* assertions (recommend as a flag `--assert-tool-order` if cheap, else follow-up), web UI, parameterized tests.

## Inputs to lock during brainstorming
- Reuse the agent-checkpoint reference loop here (recommend: yes — one loop, two uses), or duplicate (ponytail-allowed if it keeps each project standalone).
- How to handle nondeterministic recorded values (timestamps, random IDs) in the stubbed results — recommend a `--scrub <regex>` to normalize them before comparison, documented.
- Exact-match default: too strict? (recommend: default `contains` for the final answer, `exact` opt-in — fewer false-negative regressions on first use.)

One of 10 sibling local-first agent-tooling projects. Keep it small and ship it.