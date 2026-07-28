"""transcript-to-test CLI."""
import argparse
import os
import re
import sys
from pathlib import Path

from . import generator
from .canonical import make_turn
from .detect import FORMATS, detect
from .generator import apply_scrub


def _derive_output(input_path):
    stem = Path(input_path).stem
    # Strip a leading 'session-' or similar if the user points at a raw transcript.
    return f"test_{stem}.py"


def _derive_name(output_path):
    return Path(output_path).stem


def main(argv=None):
    parser = argparse.ArgumentParser(prog="transcript-to-test")
    format_names = [name for name, _ in FORMATS]
    parser.add_argument("transcript", help="path to transcript file (Claude Code JSONL, OpenAI messages, agent-vcr tape, or Codex rollout JSONL)")
    parser.add_argument("-o", "--output", help="output test file (default: test_<stem>.py)")
    parser.add_argument("--format", choices=format_names,
                        help="force input format (default: auto-detect)")
    parser.add_argument("--assert", dest="assert_args", nargs="+", default=["exact"],
                        metavar="MODE_OR_PATTERN",
                        help="assertion mode: exact (default), contains, or regex PATTERN")
    parser.add_argument("--framework", default="pytest", choices=["pytest", "unittest"],
                        help="test framework (default: pytest)")
    parser.add_argument("--scrub", default=None,
                        help="regex to scrub from recorded values before embedding")
    args = parser.parse_args(argv)

    assert_mode = args.assert_args[0]
    pattern = None
    if assert_mode not in ("exact", "contains", "regex"):
        parser.error("--assert first argument must be exact, contains, or regex")
    if assert_mode == "regex":
        if len(args.assert_args) < 2:
            parser.error("--assert regex requires a PATTERN argument")
        pattern = args.assert_args[1]

    scrub_regex = None
    if args.scrub is not None:
        try:
            scrub_regex = re.compile(args.scrub)
        except re.error as e:
            parser.error(f"invalid --scrub regex: {e}")

    try:
        with open(args.transcript, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError as e:
        raise SystemExit(f"transcript-to-test: cannot read {args.transcript!r}: {e}")

    try:
        if args.format:
            reader = next(module for name, module in FORMATS if name == args.format)
        else:
            _, reader = detect(text)
        turns = reader.parse(text)
    except ValueError as e:
        raise SystemExit(f"transcript-to-test: {e}")

    # Ensure there is at least one user turn so the generated test has an
    # initial prompt. If the input has none (e.g. a tape starting mid-run),
    # ponytail: synthesise a placeholder and let the user edit.
    if not any(t["role"] == "user" for t in turns):
        turns.insert(0, make_turn(role="user", content="",
                                  provider=turns[0].get("provider", "anthropic") if turns else "anthropic"))

    turns = apply_scrub(turns, scrub_regex)

    output_path = args.output or _derive_output(args.transcript)
    name = _derive_name(output_path)

    source = generator.render(name, turns, assert_mode=assert_mode,
                              framework=args.framework, pattern=pattern)

    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(source)

    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
