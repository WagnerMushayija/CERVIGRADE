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
DEFAULT_DOMAIN = "alustudent.com"


class InstitutionPolicy:
    """The rule itself: which email domains may have accounts."""

    def __init__(self, domains):
        self.domains = tuple(d.strip().lower().lstrip("@") for d in domains if d.strip())
        self.open_to_any = "*" in self.domains or not self.domains

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("CERVIGRADE_EMAIL_DOMAINS", DEFAULT_DOMAIN).split(","))

    @staticmethod
    def normalise(email):
        return (email or "").strip().lower()

    @property
    def primary_domain(self):
        """The domain new accounts get when they are created for someone without one."""
        return DEFAULT_DOMAIN if self.open_to_any else self.domains[0]

    def is_institutional(self, email):
        """True when the text is a well-formed email address at an allowed domain."""
        match = _EMAIL_RE.match(self.normalise(email))
        if not match:
            return False
        return self.open_to_any or match.group(1) in self.domains

    def describe(self):
        return "any address" if self.open_to_any else " or ".join("@" + d for d in self.domains)

    def rejection_message(self):
        return f"Only {self.describe()} accounts can use CerviGrade. Enter your institution email address."

    def default_admin_email(self):
        """The address the first administrator gets, unless CERVIGRADE_ADMIN_EMAIL says otherwise."""
        return self.normalise(os.environ.get("CERVIGRADE_ADMIN_EMAIL")) or f"admin@{self.primary_domain}"


# The rule the running server uses, built once from the environment. The module-level names below
# keep the rest of the code short: institution.is_institutional(...), institution.DOMAINS, and so on.
POLICY = InstitutionPolicy.from_environment()
DOMAINS = POLICY.domains
OPEN_TO_ANY = POLICY.open_to_any
normalise = POLICY.normalise
is_institutional = POLICY.is_institutional
describe_domains = POLICY.describe
rejection_message = POLICY.rejection_message
default_admin_email = POLICY.default_admin_email
