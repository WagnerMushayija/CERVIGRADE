"""What a clinician sends when reviewing a grade."""

from typing import Literal, Optional

from pydantic import BaseModel


class FeedbackIn(BaseModel):
    action: Literal["confirmed", "corrected"]
    corrected_class: Optional[str] = None
