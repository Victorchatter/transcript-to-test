# Changelog

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
