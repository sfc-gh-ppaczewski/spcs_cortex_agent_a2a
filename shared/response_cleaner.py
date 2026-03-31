"""
Shared utility for cleaning Snowflake Cortex Agent responses.

Removes chain-of-thought preamble and duplicate content that Cortex
sometimes includes in its output.
"""
import re

_COT_PREFIXES = (
    "The user ",
    "I should ",
    "Based on my ",
    "Based on ",
    "I need to",
    "Let me ",
    "I have access to",
    "I can see that ",
    "I found ",
    "I have the ",
    "According to ",
    "This is a ",
    "This requires ",
    "This falls under ",
    "This shows ",
    "This has:",
    "This has\n",
    "Perfect!",
    "Great!",
    "Now I should ",
    "Now I need to ",
    "Now let me ",
    "The data is ",
    "The other ",
    "The reviews ",
    "Looking at ",
    "Please find the ",
    "The chart ",
    "The SQL result ",
    "Since this ",
    "Here's a visual comparison",
    "This would ",
    "The data shows",
    "As you can see",
)

_COT_PATTERN = re.compile(
    r"^("
    r"\d+\.\s+(?:A\s+Cortex|Query\s|Order\s|Show\s|Search\s|Get\s|Find\s"
    r"|Since\s|Limit\s|Filter\s|Check\s|Include\s|Potentially\s|Create\s"
    r"|Sort\s|Return\s|Use\s|Call\s|Look\s|Provide\s|Display\s|Fetch\s)"
    r"|"
    r"- .*(?:suitable for comparison|visualization-ready|good for visualization"
    r"|perfect for a|clean column|ranking.comparison|rows of data)[^\n]*"
    r")",
)


def clean_response(text: str) -> str:
    """Remove duplicated content and chain-of-thought from agent responses."""
    if not text:
        return text

    # --- Phase 1: Remove duplicate paragraphs ---------------------------
    # Cortex often emits the same block of text two or more times. Split on
    # double-newlines, deduplicate while preserving order, then reassemble.
    paragraphs = re.split(r"\n{2,}", text.strip())
    seen: set[str] = set()
    unique: list[str] = []
    for para in paragraphs:
        normalised = para.strip()
        if not normalised:
            continue
        if normalised in seen:
            continue
        seen.add(normalised)
        unique.append(normalised)
    text = "\n\n".join(unique)

    # --- Phase 2: Strip leading chain-of-thought lines ------------------
    lines = text.split("\n")
    first_content = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _COT_PATTERN.match(stripped):
            first_content = i + 1
            continue
        if any(stripped.startswith(p) for p in _COT_PREFIXES):
            first_content = i + 1
            continue
        break

    if first_content > 0:
        while first_content < len(lines) and not lines[first_content].strip():
            first_content += 1
        cleaned = "\n".join(lines[first_content:]).strip()
        if cleaned:
            text = cleaned

    # --- Phase 3: Remove interior CoT paragraphs -------------------------
    # After dedup and leading strip, there may still be CoT blocks
    # sandwiched between real content. Drop any paragraph whose every
    # non-blank line looks like CoT.
    paragraphs = re.split(r"\n{2,}", text.strip())
    kept: list[str] = []
    for para in paragraphs:
        lines_in = [ln for ln in para.split("\n") if ln.strip()]
        if not lines_in:
            continue
        all_cot = True
        for ln in lines_in:
            s = ln.strip()
            if _COT_PATTERN.match(s):
                continue
            if any(s.startswith(p) for p in _COT_PREFIXES):
                continue
            if re.match(r"^Step\s+\d+:", s):
                continue
            all_cot = False
            break
        if not all_cot:
            kept.append(para)
    text = "\n\n".join(kept) if kept else text

    # --- Phase 4: Strip trailing chain-of-thought lines ------------------
    lines = text.rstrip().split("\n")
    while lines:
        last = lines[-1].strip()
        if not last:
            lines.pop()
            continue
        if _COT_PATTERN.match(last):
            lines.pop()
            continue
        if any(last.startswith(p) for p in _COT_PREFIXES):
            lines.pop()
            continue
        break
    text = "\n".join(lines).rstrip()

    return text
