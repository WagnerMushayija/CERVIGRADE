"""What the model said about an image, and what a clinician decided about it."""

from typing import Optional

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class Prediction(SQLModel, table=True):
    __tablename__ = "predictions"
    __table_args__ = {"sqlite_autoincrement": True}
    model_config = {"protected_namespaces": ()}          # the fields model_name and model_version are ours

    id: Optional[int] = Field(default=None, primary_key=True)
    slide_image_id: int = Field(foreign_key="slide_images.id", ondelete="CASCADE", unique=True)
    error: Optional[str] = None
    predicted_class: Optional[str] = None
    confidence: Optional[float] = None
    tier: Optional[str] = None
    tier_confidence: Optional[float] = None
    low_confidence: Optional[bool] = None
    probabilities: Optional[str] = None         # JSON, six numbers
    mode: Optional[str] = None                  # 'field' (detector + CNN), 'cell' (one cell) or 'whole'
    detections: Optional[str] = None            # JSON: boxes, per-box grade, which counted (field mode only)
    model_name: str
    model_version: str
    mock: bool = False                          # True when the grade came from the placeholder
    created_at: str


class FeedbackEntry(SQLModel, table=True):
    __tablename__ = "feedback_entries"
    __table_args__ = (CheckConstraint("action IN ('confirmed', 'corrected')", name="ck_feedback_action"), {"sqlite_autoincrement": True})

    id: Optional[int] = Field(default=None, primary_key=True)
    prediction_id: int = Field(foreign_key="predictions.id", ondelete="CASCADE", unique=True)   # at most one per prediction
    clinician_id: int = Field(foreign_key="users.id")
    action: str                                 # confirmed or corrected
    corrected_class: Optional[str] = None
    created_at: str
    updated_at: str
