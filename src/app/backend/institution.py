"""
Who is allowed in: only people with an email address at the institution.

CerviGrade is meant for one institution's staff and students, so an account name is an institutional
email address and anything else is turned away, both when an account is created and when someone signs in.

The allowed domain comes from CERVIGRADE_EMAIL_DOMAINS (comma separated, default "alustudent.com").
Set it to "*" to switch the rule off, for example in automated tests.

This checks the address, not the inbox. Nobody can sign up on their own: an administrator creates each
account and gives out the first password, so the rule decides which addresses an administrator may add.
"""

import os
import re

_EMAIL_RE = re.compile(r"^[a-z0-9._%+-]{1,64}@([a-z0-9-]+(?:\.[a-z0-9-]+)+)$")


def _read_domains(raw):
    return tuple(d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip())


DOMAINS = _read_domains(os.environ.get("CERVIGRADE_EMAIL_DOMAINS", "alustudent.com"))
OPEN_TO_ANY = "*" in DOMAINS or not DOMAINS


def normalise(email):
    return (email or "").strip().lower()


def is_institutional(email):
    """True when the text is a well-formed email address at an allowed domain."""
    match = _EMAIL_RE.match(normalise(email))
    if not match:
        return False
    return OPEN_TO_ANY or match.group(1) in DOMAINS


def describe_domains():
    return "any address" if OPEN_TO_ANY else " or ".join("@" + d for d in DOMAINS)


def rejection_message():
    return f"Only {describe_domains()} accounts can use CerviGrade. Enter your institution email address."


def default_admin_email():
    """The address the first administrator gets, unless CERVIGRADE_ADMIN_EMAIL says otherwise."""
    domain = "alustudent.com" if OPEN_TO_ANY else DOMAINS[0]
    return normalise(os.environ.get("CERVIGRADE_ADMIN_EMAIL")) or f"admin@{domain}"
