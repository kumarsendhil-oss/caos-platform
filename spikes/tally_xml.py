"""
Sanitise Tally's XML before parsing.

FINDING (P0-02, 2026-09-15, run 2026-09-15T14-52-11-export-ledgers):
TallyPrime emits `&#4;` — the EOT control character — inside its XML
responses. XML 1.0 forbids character references to control characters
in the ranges #x0-#x8, #xB, #xC and #xE-#x1F, so a compliant parser
rejects the whole document. Python's ElementTree fails with:

    reference to invalid character number: line 80, column 27

The response is otherwise well-formed and the data is intact. Tally
appears to use `&#4;` as an internal separator — most visibly inside
fields that can hold multiple values.

Consequence for TallyAdapter (issue #1): every response must pass
through sanitise() before parsing. This is not optional defensive
coding; it is required for any parse to succeed at all.

Open question, deliberately not resolved here: because `&#4;` is a
separator rather than noise, a multi-value field may carry meaning in
how its parts are divided. This module replaces each occurrence with a
newline rather than deleting it, so the boundary survives and can be
split on later if a multi-value field turns out to matter. If a field
ever comes back looking concatenated, this is where to look.
"""

from __future__ import annotations

import re

# XML 1.0 (5th ed.) permits only #x9, #xA, #xD and #x20+ below #x7F.
# Everything else in the C0 range is illegal, whether it appears as a
# literal byte or as a numeric character reference.
_ILLEGAL_REFS = re.compile(
    r"&#(?:0*(?:[0-8]|1[1-2]|1[4-9]|2[0-9]|3[0-1])|[xX]0*(?:[0-8bBcC]|[eE]|1[0-9a-fA-F]));"
)

_ILLEGAL_LITERALS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

# What we substitute in. A newline is legal XML, survives round-tripping,
# and preserves the fact that a boundary existed — unlike deletion, which
# would silently concatenate whatever the separator was dividing.
_REPLACEMENT = "\n"


def sanitise(xml: str) -> str:
    """Make a Tally response parseable without discarding field boundaries."""
    xml = _ILLEGAL_REFS.sub(_REPLACEMENT, xml)
    return _ILLEGAL_LITERALS.sub(_REPLACEMENT, xml)


def count_illegal(xml: str) -> int:
    """How many illegal characters/references a response contained."""
    return len(_ILLEGAL_REFS.findall(xml)) + len(_ILLEGAL_LITERALS.findall(xml))
