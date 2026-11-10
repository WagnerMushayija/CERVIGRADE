"""What the user-management requests must contain, and how a user is shown to the outside."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

PUBLIC_USER_FIELDS = ("id", "username", "full_name", "role", "active", "created_at", "last_login")


def public_user(user):
    """A user without the password hash."""
    d = {k: getattr(user, k) for k in PUBLIC_USER_FIELDS}
    d["active"] = bool(d["active"])
    return d


class UserIn(BaseModel):
    username: str
    full_name: str = Field(min_length=2, max_length=80)
    role: Literal["technician", "clinician", "admin"]
    password: str = Field(min_length=8, max_length=128)


class UserPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    role: Optional[Literal["technician", "clinician", "admin"]] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
