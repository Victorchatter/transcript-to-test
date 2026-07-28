"""Auto-detect transcript format.

# ponytail: detection is order-sensitive because several formats are JSONL.
We sniff with decreasing specificity:
1. agent-vcr tape (wire-level `kind` + `seq`)
2. Claude Code JSONL (`type` in Claude set + `message`)
3. OpenAI messages (top-level JSON array or `{messages: [...]}`)
4. Codex rollout JSONL (`type` in Codex set or `payload`)
If multiple sniffers match, we raise with a clear message asking for `--format`.
"""
from .readers import claude_code, codex, openai, tape


FORMATS = [
    ("agent_vcr_tape", tape),
    ("claude_code_jsonl", claude_code),
    ("openai_messages", openai),
    ("codex_jsonl", codex),
]


def detect(text):
    """Return (format_name, reader_module) for the supplied transcript text.

    Raises ValueError if the format cannot be determined or is ambiguous.
    """
    matches = []
    for name, module in FORMATS:
        if module.sniff(text):
            matches.append((name, module))

    if not matches:
        raise ValueError(
            "unrecognized transcript format (expected agent-vcr tape, "
            "Claude Code JSONL, OpenAI messages, or Codex rollout JSONL)"
        )

    if len(matches) > 1:
        names = ", ".join(name for name, _ in matches)
        raise ValueError(
            f"ambiguous transcript format; matched: {names}. "
            "Use --format to specify one explicitly."
        )

    return matches[0]
