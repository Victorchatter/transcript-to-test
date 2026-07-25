# transcript-to-test — design spec

**Date:** 2026-07-25
**Status:** Retroactive — documents the shipped v0.1.0 design (~1,000 LOC), written after the fact because the project skipped the spec step during bootstrap.
**One-liner:** A local, zero-dependency CLI that reads a recorded agent transcript (Claude Code JSONL, OpenAI messages, or an agent-vcr tape) and emits a standalone pytest/unittest file that replays the recorded turns, stubs tool results by `(tool_name, args)`, and asserts the final answer — a regression test generated from one successful run.

## Goal

Agent runs are expensive and non-deterministic. When one finally produces the
right answer, there's no cheap way to lock that behavior in as a regression
test — re-running the agent live costs money and can silently diverge.
transcript-to-test converts a recorded transcript directly into a `test_*.py`
file that runs in milliseconds, offline, with zero dependency on
transcript-to-test itself once generated.

## Locked design decisions

| Decision | Shipped behavior | Why |
|---|---|---|
| Input formats | Claude Code JSONL, OpenAI messages JSON array, agent-vcr tape JSONL — sniffed automatically, no `--format` flag | These are the three transcript shapes the sibling local-agent-tooling projects (transcript-bridge, agent-checkpoint, agent-vcr) already produce or consume. Sniffing removes a flag the user would otherwise have to get right. |
| Sniff order | `openai_messages` → `claude_code_jsonl` → `agent_vcr_tape` (`readers/__init__.py`) | OpenAI input is a JSON array (`text.lstrip().startswith("[")`), which can never be valid JSONL, so it's checked first and short-circuits cheaply. The two JSONL formats are disambiguated by their first line's `type`/`kind` field. |
| Canonical envelope | One shared `make_turn()` dict per turn (`role`, `content`, `tool_calls`, `tool_results`, `provider`, `model`, `ts`) — shape mirrors transcript-bridge/agent-checkpoint | Keeps the three sibling projects conceptually aligned without sharing code (each stays pipx-installable standalone). Only the fields this tool actually consumes are carried; it does not implement the full loss model those siblings might need. |
| Tool-result normalization | Claude Code's `tool_result` blocks (which ride inside the *next user* message in that format) are split out into standalone synthetic `role: "tool"` turns at parse time | Makes the three input formats converge on one shape (`assistant` turn with `tool_calls`, followed by one or more `tool` turns) before they ever reach the generator, so `generator.py` and the replay loop only have to handle one shape. |
| Stub key | `(tool_name, canonical_json(args))` via `json.dumps(args, sort_keys=True, separators=(",", ":"))`, not tool name alone | If the recorded agent calls the same tool twice with different arguments, a name-only key would silently collapse them to one stub and hide a real mismatch. Keying on canonicalized args means a divergent call gets its own registry slot (or a `KeyError` if unseen), which is what a regression test is supposed to catch. |
| Generated test is standalone | The reference replay loop (`reference_loop.py`) is *inlined* into the rendered `test_<name>.py` via string template (`generator.py`), not imported from the installed package | A test file that imports transcript-to-test would break the moment the package changes shape or is uninstalled. Copying ~50 lines of loop code into every generated file trades a small duplication cost for tests that outlive the generator by design — "a generated test from today will still run in five years" (README). |
| Replay is deterministic, not a live re-run | `run_agent()` in the generated test never calls a model or a real tool. It walks the *recorded* `expected_turns` list, appends the recorded assistant text verbatim, and for each recorded tool call looks up `tool_registry[(name, args)]` — a dict built from that same recording — and asserts it equals the recorded expected result | This is the crux of the whole generator: nothing here regenerates content. `EXPECTED_TURNS`, `TOOL_REGISTRY`, and `EXPECTED_FINAL` all derive from one recorded transcript at generation time, then get frozen as literal Python data in the output file. The test only fails when a human (or a future codegen step) edits `TOOL_REGISTRY` to reflect changed tool behavior — that's the intended regression signal (see "Test tool migrations" in the README). |
| **`--assert` default is `exact`, not `contains`** | `cli.py` (`parser.add_argument("--assert", ..., default=["exact"])`, currently around line 28) | **See "Resolving the exact-vs-contains reversal" below — this is a deliberate keep, not an oversight.** |
| Assertion escape hatches | `contains` (`assert EXPECTED_FINAL in final`) and `regex PATTERN` (`assert re.search(PATTERN, final)`) are available via `--assert contains` / `--assert regex PATTERN` | For runs whose final answer is legitimately non-deterministic in formatting (e.g. it embeds a live timestamp the transcript author didn't `--scrub`), a full exact match on that one field would force the user to touch the generated file by hand. The escape hatches keep the net without forcing hand-edits, while leaving `exact` as the strict default for everything else. |
| `--scrub REGEX` | A regex applied to tool-result content and the final assistant text *before* they're embedded as literals in the generated file (`generator.apply_scrub`) | Timestamps, UUIDs, and similar per-run noise would otherwise get baked into `EXPECTED_TURNS`/`EXPECTED_FINAL` as literal strings, making even a legitimately-identical rerun's `exact` comparison meaningless. Scrubbing at generation time (once) is cheaper than asking every consumer of the generated test to normalize at assert time. |
| Framework choice | `pytest` (default) or `unittest`, `--framework` | Two near-identical templates (`_PYTEST_TEMPLATE` / `_UNITTEST_TEMPLATE` in `generator.py`) rather than one templating abstraction over both — ponytail: the templates are ~80 lines each and diverge only in decorator/assert syntax; a shared abstraction would cost more than it saves at this size. |
| Missing initial user turn | If a parsed transcript has no `role: "user"` turn (e.g. an agent-vcr tape that starts mid-run), `cli.py` inserts a synthetic empty-content user turn at position 0 | The generated test always needs *some* seed message for `messages = [{"role": "user", ...}]`; failing outright would block tapes that legitimately start after the first prompt. Documented in-code as a `# ponytail:` placeholder the user is expected to edit if it matters. |
| Output path | Explicit `-o/--output`, else `test_<transcript-stem>.py` in the current directory | Matches the one-line "turn last night's run into a test" README use case without forcing a flag on the common path; `-o` remains available for placing the file under `tests/`. |
| Dependencies | Zero runtime dependencies; `pytest` is a dev-only dependency needed solely to *run* generated pytest-style output and the self-check, never to *generate* it | Keeps `pipx install .` instant and keeps generated files free of any import beyond `json` (+`re`/`unittest` when relevant), matching the "standalone generated tests" decision above. |

### Resolving the exact-vs-contains reversal

`PROMPT.md` (the pre-brainstorm seed note) recommended flipping the default:
> "Exact-match default: too strict? (recommend: default `contains` for the
> final answer, `exact` opt-in — fewer false-negative regressions on first
> use.)"

The shipped code does the opposite — `--assert` defaults to `exact`
(`cli.py`, `default=["exact"]`) — and this was never written down anywhere
until now. Resolution: **the shipped default is correct, and the PROMPT.md
note is superseded, not just overridden.**

The PROMPT.md worry assumes a *live* re-run: if the reference loop actually
called a model again, wording could drift turn to turn even when the agent's
behavior is "the same," and `exact` would flake on cosmetic differences —
hence "fewer false-negative regressions on first use."

That assumption doesn't hold for what actually got built. Reread the
"Replay is deterministic, not a live re-run" row above: `run_agent()` in the
generated test never regenerates anything. `EXPECTED_FINAL` and the assistant
text `run_agent()` returns are *the same recorded string*, extracted from the
same transcript at generation time. On the run immediately after generation
there is no live model in the loop to introduce wording drift — `exact` can't
flake for the reason PROMPT.md worried about, because there is no
regeneration step for it to flake against.

What `exact` *does* correctly catch is the scenario the README's "Test tool
migrations" use case describes: someone edits `TOOL_REGISTRY` in the
generated file to point at a new tool implementation's real output. If that
new output changes the final answer by even one character, `exact` catches
it; `contains` (checking only that the old answer is a substring of the new
one) would miss a large class of legitimate regressions — reordered fields,
changed formatting, truncated results — while only formatting-only,
non-substantive differences (timestamps, casing, wording that doesn't shorten
the string) would falsely fail under `exact`, and `--scrub` plus the
`contains`/`regex` opt-outs already exist for exactly that case.

So: `exact` is the stricter, more useful default *because* the replay is
deterministic replay-of-recording rather than live regeneration; PROMPT.md's
false-negative concern was written for a design (live re-run) that isn't what
shipped. No code change. This paragraph is the missing justification.

## Architecture

```
Transcript file (Claude Code JSONL / OpenAI messages / agent-vcr tape)
        │
        ▼
  readers.detect(text)  ──sniff──▶  one of: readers/claude_code.py,
        │                                    readers/openai.py,
        │                                    readers/tape.py
        ▼
  reader.parse(text) → list[canonical turn]     (canonical.make_turn shape)
        │
        ▼
  cli.py: ensure a leading user turn, apply_scrub()
        │
        ▼
  generator.render(name, turns, assert_mode, framework, pattern)
        ├─ extract_tool_registry(turns)   → {(tool, canonical_args): result}
        ├─ filter_assistant_tool_turns()  → EXPECTED_TURNS
        ├─ initial_prompt() / final_answer()
        └─ render into _PYTEST_TEMPLATE or _UNITTEST_TEMPLATE
        │
        ▼
  test_<name>.py   (standalone: json [+ re/unittest], no transcript-to-test import)
        │
        ▼
  pytest / unittest  →  pass/fail against the frozen recorded data
```

`reference_loop.py` in the installed package is the source of truth for the
replay algorithm; `generator.py`'s two template strings duplicate it verbatim
(inlined) so the emitted file needs no import from this package. A change to
one must be mirrored in the other by hand — there's no test enforcing that
today (see Out of scope).

## Module map

```
transcript_to_test/
  __init__.py            # version string only
  cli.py                 # argparse entrypoint: read file, detect+parse,
                          # scrub, derive output path, call generator.render,
                          # write file
  canonical.py            # make_turn() envelope + read_jsonl/write_jsonl helpers
  readers/
    __init__.py           # FORMATS list + detect() sniff dispatcher
    claude_code.py         # Claude Code session JSONL -> canonical turns
    openai.py               # OpenAI `messages` JSON array -> canonical turns
    tape.py                  # agent-vcr wire-level tape -> canonical turns
  generator.py             # extract_tool_registry, final_answer, initial_prompt,
                            # scrub_value/apply_scrub, _PYTEST_TEMPLATE,
                            # _UNITTEST_TEMPLATE, render()
  reference_loop.py         # standalone copy of the replay algorithm, used only
                             # as the documented reference; the generated file's
                             # copy is the one that actually runs
selfcheck.py                # generate -> run -> mutate -> re-run -> assert fail
pyproject.toml               # pipx-installable, zero runtime deps
LICENSE                      # MIT
README.md
```

## Reader contract

Each `readers/*.py` module exports two functions:

- `sniff(text) -> bool` — cheap, look-at-the-first-line check. Must not raise
  on malformed input where reasonably avoidable (`claude_code.sniff` and
  `tape.sniff` catch `JSONDecodeError` and return `False` rather than
  propagating).
- `parse(text) -> list[canonical turn]` — full parse; can raise on genuinely
  malformed input, since by the time `parse` runs, `detect()` has already
  matched the sniffer.

Adding a new format means adding one reader module and one entry in
`readers/__init__.py`'s `FORMATS` list — no other file needs to change.

## Assertion styles (as shipped)

| Mode | Generated assertion (pytest) | Generated assertion (unittest) |
|---|---|---|
| `exact` *(default)* | `assert final == EXPECTED_FINAL` | `self.assertEqual(final, EXPECTED_FINAL)` |
| `contains` | `assert EXPECTED_FINAL in final` | `self.assertIn(EXPECTED_FINAL, final)` |
| `regex PATTERN` | `assert re.search(PATTERN, final), ...` | `self.assertIsNotNone(re.search(PATTERN, final), ...)` |

## selfcheck.py

No test framework for the shipped tool itself (plain `assert`), but the
self-check does shell out to `pytest` to exercise a *generated* file, since
that's the only way to prove the generated output is actually runnable:

1. Build a synthetic OpenAI-messages transcript (`user` → `assistant` with one
   `tool_calls` entry → `tool` result `"4"` → final `assistant` "The answer is
   4.").
2. Run the CLI (`cli.main`) to generate `test_synthetic.py` in a temp dir.
3. Run the generated file under `pytest -q`; assert exit code 0.
4. Regex-mutate the generated file's `TOOL_REGISTRY` entry for `calc` from
   `'4'` to `'5'` (`re.sub` against the literal `('calc', '{"expr":"2+2"}'): '4'`
   pattern) — this is the "someone changed the tool" scenario the exact-match
   default is designed to catch.
5. Re-run `pytest -q`; assert exit code is nonzero and the output mentions an
   assertion failure.

This directly proves the mechanism documented in the "Resolving the
exact-vs-contains reversal" section above: the test does not fail on its own
from re-running unchanged data; it only fails once the frozen stub is edited.

## Scope (v1, as shipped)

**In:**
- Claude Code JSONL, OpenAI messages, agent-vcr tape inputs (auto-sniffed).
- `pytest` and `unittest` output via `--framework`.
- `exact` (default), `contains`, `regex PATTERN` assertions via `--assert`.
- `--scrub REGEX` to normalize nondeterministic recorded values before they're
  embedded as literals.
- `-o/--output` path control; default derived from the input filename.
- Standalone generated tests with zero dependency on transcript-to-test.
- `pipx install .`, zero runtime dependencies.

**Out (deliberately not built):**
- Multi-run fuzzing across several recorded transcripts.
- Tool-call **ordering** assertions (a `--assert-tool-order` flag was
  considered in PROMPT.md as a possible cheap follow-up; not shipped).
- A web UI.
- Parameterized tests (one transcript → one test function, not a matrix).
- A shared library dependency between the generator and its generated
  output — the inlined-loop decision above is intentional, not an oversight.
- A test enforcing that `reference_loop.py` and the two inlined template
  copies stay in sync; today that's a manual invariant.
- Live tool re-invocation in the generated test (see the deterministic-replay
  decision above) — `TOOL_REGISTRY` is frozen data, not a call site into a
  real tool implementation. A future version wanting to test *live* tool
  migrations, not just frozen-stub divergence, would need to change this.

## License

MIT — see [LICENSE](../../../LICENSE).
