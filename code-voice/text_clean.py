"""Markdown -> spoken-text cleaning for Code Voice.

Pure stdlib so it can be imported by both the Stop hook (system python3)
and the warm server (brainrot-radio venv python3). The research flagged
regex markdown stripping as a universal failure point, so this is done
carefully in Python rather than with a one-line sed.
"""
import re

CODE_MARKER = " code block. "


def strip_markdown(text: str) -> str:
    """Turn a markdown response into clean prose suitable for TTS.

    Code blocks are replaced with a short spoken marker (we don't read
    code aloud). Links, headers, emphasis, lists, and tables are flattened.
    """
    if not text:
        return ""

    # Fenced code blocks -> spoken marker (do this first, before anything
    # inside them gets mangled).
    text = re.sub(r"```.*?```", CODE_MARKER, text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", CODE_MARKER, text, flags=re.DOTALL)
    # An unclosed trailing fence (truncated response): drop from the fence on.
    text = re.sub(r"```.*$", CODE_MARKER, text, flags=re.DOTALL)

    # Images ![alt](url) -> alt ; then links [text](url) -> text
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # Bare autolinks <http...>
    text = re.sub(r"<https?://[^>]+>", "", text)

    # Inline code: keep the inner text, drop the backticks.
    text = re.sub(r"`([^`]+)`", r"\1", text)

    cleaned_lines = []
    for line in text.split("\n"):
        # Table separator rows ( |---|:--:| ) -> drop entirely
        stripped = line.strip()
        if "|" in line and stripped and set(stripped) <= set("|:- "):
            continue
        # Horizontal rules
        if re.match(r"^\s*([-*_]\s*){3,}$", line):
            continue
        # Headers: strip leading #'s
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
        # Blockquote markers
        line = re.sub(r"^\s{0,3}>\s?", "", line)
        # List bullets / numbered list markers
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)]\s+", "", line)
        # Table cell pipes -> comma pauses
        if "|" in line:
            line = re.sub(r"\s*\|\s*", ", ", line).strip(", ")
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    # Emphasis markers (after structural work so list/hr detection saw them)
    text = re.sub(r"\*\*\*|\*\*|\*|___|__|~~", "", text)
    # Standalone underscores used for italics (avoid snake_case identifiers)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)

    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


# Roughly how many words count as "short enough to speak verbatim" —
# below this we skip the summarizer (summarizing a one-liner risks losing
# detail and wastes latency).
SHORT_WORD_THRESHOLD = 45


def is_short(text: str) -> bool:
    return len(text.split()) <= SHORT_WORD_THRESHOLD
