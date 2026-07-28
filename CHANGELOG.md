# Changelog

## 0.3.0

### Added
- Tier-2 assertion templates: `json-path`, `no-error`, and `structured-match`.
  - `--assert-template` preset flag with `--assert-value` and `--assert-pattern` options.
  - Existing `--assert MODE [PATTERN]` syntax continues to work and maps internally to templates.
- Generated tests now include `import json` only when required (tool calls or JSON assertions).

## 0.2.0

### Added
- Auto-detect transcript format from content; no explicit `--format` required.
  - Detection order: agent-vcr tape → Claude Code JSONL → OpenAI messages → Codex rollout JSONL.
  - Optional `--format` override for ambiguous cases.
- New Codex rollout JSONL reader (`transcript_to_test.readers.codex`).
- New `transcript_to_test.detect` module with unit tests in `tests/test_detect.py`.

## 0.1.0

### Added
- Initial release: convert Claude Code JSONL, OpenAI messages, or agent-vcr tapes
  into standalone pytest/unittest regression tests.
