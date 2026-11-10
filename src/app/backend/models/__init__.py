"""
The database tables, written as Python classes (SQLModel). One class is one table, and one object is one row.
Importing this package registers every table, so db.database can create them.
"""

from models.patient import Patient
from models.prediction import FeedbackEntry, Prediction
from models.slide import Slide, SlideImage
from models.user import User

__all__ = ["User", "Patient", "Slide", "SlideImage", "Prediction", "FeedbackEntry"]
