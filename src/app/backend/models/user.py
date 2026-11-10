"""The users table: one row per account."""

from typing import Optional

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('technician', 'clinician', 'admin')", name="ck_users_role"), {"sqlite_autoincrement": True})

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)          # the institution email address
    full_name: str
    role: str                                   # technician, clinician or admin
    password_hash: str
    active: bool = True
    created_at: str
    last_login: Optional[str] = None
