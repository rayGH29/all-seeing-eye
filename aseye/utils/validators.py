"""Target classification helpers."""

from __future__ import annotations

import re

from aseye.models import Target

# Deliberately permissive email check — good enough to distinguish an email
# from a bare handle, without trying to be a full RFC 5322 validator.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def classify_target(value: str) -> Target:
    """Classify a raw input string as a username or an email address.

    Anything containing a plausible ``local@domain.tld`` shape is treated as an
    email; everything else is treated as a username.
    """
    cleaned = value.strip()
    if _EMAIL_RE.match(cleaned):
        kind = "email"
    elif cleaned:
        kind = "username"
    else:
        kind = "unknown"
    return Target(value=cleaned, kind=kind)
