"""What the patient requests must contain."""

from pydantic import BaseModel


class PatientPatch(BaseModel):
    code: str
