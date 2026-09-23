"""
IS number normalization.

The same standard appears across sources as "IS 1554 (Part 1) : 1988",
"IS:1554-1", "IS 1554 Part 1", "IS1554/1". Every downstream join depends on
these collapsing to one canonical key, so this is the single most
correctness-critical function in the pipeline.

Canonical form:  "IS 1554-1"   (part appended with a hyphen, year stripped)
Year is carried separately because the same standard number persists across
revisions -- folding the year into the key would fragment the graph.
"""
import re
from typing import Optional, Tuple

# Matches the IS designator with optional part/section and optional year.
_IS_PATTERN = re.compile(
    r"""
    IS \s* [:\-/]? \s*
    (?P<number>\d{1,6})
    (?:
        # Explicit part: "(Part 1)", "Part 1", "-Part 1"
        \s* [\(\-/ ] \s* (?:Part|Pt\.?) \s* (?P<part>\d+) \s* \)?
      |
        # Bare hyphenated part: "-1". Bounded to 1-3 digits and guarded by a
        # negative lookahead so a 4-digit year ("IS 1554-1988") is never
        # mistaken for a part number.
        - (?P<bare_part>\d{1,3}) (?!\d)
    )?
    (?: \s* [\(\-/ ] \s* (?:Sec|Section) \s* (?P<section>\d+) \s* \)? )?
    (?: \s* [:\-] \s* (?P<year>(?:19|20)\d{2}) )?
    """,
    re.IGNORECASE | re.VERBOSE,
)


def normalize_is_number(raw: Optional[str]) -> Optional[str]:
    """Return the canonical IS key, or None if the input holds no IS designator."""
    if not raw:
        return None
    match = _IS_PATTERN.search(str(raw))
    if not match:
        return None

    key = f"IS {match.group('number')}"
    part = match.group("part") or match.group("bare_part")
    if part:
        key += f"-{part}"
    if match.group("section"):
        key += f"-{match.group('section')}"
    return key


def split_number_and_year(raw: Optional[str]) -> Tuple[Optional[str], Optional[int]]:
    """Return (canonical_key, year). Year is None when the source omits it."""
    if not raw:
        return None, None
    match = _IS_PATTERN.search(str(raw))
    if not match:
        return None, None
    year = int(match.group("year")) if match.group("year") else None
    return normalize_is_number(raw), year


def extract_all_is_references(text: Optional[str]) -> list[str]:
    """
    Pull every distinct IS reference out of a block of text.

    Used both for normative-reference extraction from standard PDFs and for
    the spec-validator feature, which scans a user's draft for cited standards.
    Order is preserved (first mention wins) because reference lists in IS
    documents are ordered by significance more often than alphabetically.
    """
    if not text:
        return []
    seen: list[str] = []
    for match in _IS_PATTERN.finditer(text):
        key = normalize_is_number(match.group(0))
        if key and key not in seen:
            seen.append(key)
    return seen
