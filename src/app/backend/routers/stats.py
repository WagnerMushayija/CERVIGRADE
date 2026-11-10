"""How often the clinicians agreed with the tool, for administrators."""

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlmodel import select

from db import database as db
from dependencies import require
from models import FeedbackEntry, Prediction
from services.grading import tier_of_class

router = APIRouter()


@router.get("/stats/review", tags=["stats"])
def review_stats(admin=Depends(require("admin")), session=Depends(db.get_session)):
    """
    How often the clinicians agreed with the tool. Counts photos (one prediction each), not single cells.
    This is agreement with a reviewer, not accuracy: it only covers photos a clinician has opened.
    """
    real = (Prediction.error.is_(None), Prediction.mock == False)           # noqa: E712  (graded for real, not by the placeholder)

    def count_where(condition):
        return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)

    totals = session.exec(
        select(func.count(Prediction.id).label("graded"),
               count_where(FeedbackEntry.id.is_not(None)).label("reviewed"),
               count_where(FeedbackEntry.action == "confirmed").label("confirmed"),
               count_where(FeedbackEntry.action == "corrected").label("corrected"))
        .select_from(Prediction).outerjoin(FeedbackEntry, FeedbackEntry.prediction_id == Prediction.id)
        .where(*real)).one()
    fixes = session.exec(
        select(Prediction.predicted_class.label("model"), FeedbackEntry.corrected_class.label("clinician"), func.count().label("n"))
        .join(FeedbackEntry, FeedbackEntry.prediction_id == Prediction.id)
        .where(FeedbackEntry.action == "corrected", *real)
        .group_by(Prediction.predicted_class, FeedbackEntry.corrected_class)
        .order_by(func.count().desc(), Prediction.predicted_class, FeedbackEntry.corrected_class)).all()
    corrections = [dict(r._mapping) for r in fixes]
    group_changed = sum(c["n"] for c in corrections if tier_of_class(c["model"]) != tier_of_class(c["clinician"]))
    out = dict(totals._mapping)
    out["waiting"] = out["graded"] - out["reviewed"]
    out["group_changed"] = group_changed
    out["corrections"] = corrections[:5]
    return out
