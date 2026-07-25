---
id: "095374a0"
type: context
tags: []
created: "2026-07-25T13:28:15.837Z"
source: manual
---
transcript-to-test: turns one recorded agent run (Claude Code JSONL, OpenAI messages, or an agent-vcr tape) into a standalone pytest regression test. CLI entry point: transcript-to-test (transcript_to_test/cli.py). # ponytail: readers/claude_code.py deliberately duplicates transcript-bridge's Claude Code parser shape instead of sharing it (unify later); user text mixed with tool_result blocks is currently dropped in v1.
