"""Slides (one visit of one patient) and the images that belong to them."""

from typing import Optional

from sqlmodel import Field, SQLModel


class Slide(SQLModel, table=True):
    __tablename__ = "slides"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    patient_id: int = Field(foreign_key="patients.id", ondelete="CASCADE", index=True)
    uploaded_by: int = Field(foreign_key="users.id")
    note: Optional[str] = None
    created_at: str


class SlideImage(SQLModel, table=True):
    __tablename__ = "slide_images"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Optional[int] = Field(default=None, primary_key=True)
    slide_id: int = Field(foreign_key="slides.id", ondelete="CASCADE", index=True)
    position: int
    filename: str                               # the name the technician's file had
    stored_name: str                            # the name it is saved under on the server
    content_type: str
