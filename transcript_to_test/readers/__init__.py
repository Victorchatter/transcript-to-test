"""Sniff and dispatch transcript formats."""
from . import claude_code, openai, tape

# Order matters: OpenAI messages start with '[', which is never valid JSONL.
FORMATS = [
    ("openai_messages", openai),
    ("claude_code_jsonl", claude_code),
    ("agent_vcr_tape", tape),
]


def detect(text):
    """Return (format_name, module) for the first reader whose sniffer matches."""
    for name, module in FORMATS:
        if module.sniff(text):
            return name, module
    raise ValueError("unrecognized transcript format")
