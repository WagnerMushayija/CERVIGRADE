"""The patients table. A patient is only a pseudonym code, never a name."""

from typing import Optional

from sqlmodel import Field, SQLModel


class Patient(SQLModel, table=True):
    __tablename__ = "patients"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    code: str = Field(unique=True)
    created_at: str
    created_by: Optional[int] = Field(default=None, foreign_key="users.id", ondelete="SET NULL")
