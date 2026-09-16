"""
Shared argv helpers for spike scripts.

Spike scripts take a handful of `--flag VALUE` arguments and are run by
hand against a live TallyPrime instance, so the guards here are not
cosmetic. `--company --send` with a naive `argv[index + 1]` lookup
targets a company literally named "--send" and — because "--send" is
still in argv — posts live while doing it. The value-shaped check is
what stops that.

Usage from a spike script:

    from _args import company_from_argv, flag_value

    company = company_from_argv(sys.argv, COMPANY)
    baseline = flag_value(sys.argv, "--baseline", "a run dir or response.xml")

Extracted from post_voucher.py, no_inventory_test.py and
remoteid_stability_probe.py, which each carried a copy
(STUB_ISSUES PENDING:011).
"""

from __future__ import annotations

import sys


def flag_value(argv: list[str], flag: str, what: str) -> str | None:
    """VALUE for `flag`, or None if the flag is absent.

    Two guards, both of which exist because of a real failure mode:
    exits with a message rather than raising IndexError when the flag is
    last with no value, and rejects a following flag as the value.

    `what` names the expected value in both error messages ("a company
    name", "a run dir or response.xml") so the caller controls the
    wording without restating the guards.
    """
    if flag not in argv:
        return None
    i = argv.index(flag) + 1
    if i >= len(argv):
        sys.exit(f"error: {flag} requires {what}")
    value = argv[i]
    if value.startswith("--"):
        sys.exit(f"error: {flag} requires {what}, got the flag {value!r}")
    return value


def company_from_argv(argv: list[str], default: str) -> str:
    """--company VALUE, falling back to `default`.

    `default` is required rather than defaulting to some company name:
    spike scripts target different companies ('Coastal Test Traders' vs
    'Coastal Services Ltd'), and a script silently inheriting another's
    target would post to the wrong books.
    """
    return flag_value(argv, "--company", "a company name") or default
