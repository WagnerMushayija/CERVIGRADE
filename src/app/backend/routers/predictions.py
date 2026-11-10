"""One graded photo: the heat map that explains a grade, and the clinician's review of it."""

import json
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import delete
from sqlmodel import select

from db import database as db
from dependencies import can_see, current_user, require
from models import FeedbackEntry, Prediction, Slide, SlideImage
from repositories import records
from schemas.predictions import FeedbackIn
from services.grading import CLASS_NAMES
from services.pipeline import PIPELINE

router = APIRouter()


@router.get("/predictions/{prediction_id}/cam", tags=["explain"])
async def prediction_cam(prediction_id: int, cell: int = 0, overlay: bool = True, user=Depends(current_user), session=Depends(db.get_session)):
    """
    Grad-CAM for one cell of a photo: the cell crop with a heat overlay showing where the model looked for the grade it gave.
    cell is the box number from the photo's detections (0 for a photo graded as a single cell). overlay=false gives the plain crop.
    """
    row = session.exec(select(Prediction, SlideImage, Slide.uploaded_by)
                       .join(SlideImage, SlideImage.id == Prediction.slide_image_id)
                       .join(Slide, Slide.id == SlideImage.slide_id)
                       .where(Prediction.id == prediction_id)).first()
    if row is None or not can_see(user, row[2]) or row[0].error:
        raise HTTPException(404, "No such prediction.")
    pred, image = row[0], row[1]
    if not PIPELINE.classifier.is_real:
        raise HTTPException(409, "The explanation needs the real model, and only the placeholder is running.")
    path = os.path.join(db.uploads_for(image.slide_id), image.stored_name)
    if not os.path.exists(path):
        raise HTTPException(404, "The image file is missing.")
    if pred.detections:
        cells = json.loads(pred.detections)["cells"]
        if not 0 <= cell < len(cells):
            raise HTTPException(404, "No such cell.")
        box, grade = cells[cell]["box"], cells[cell]["cls"]
    else:
        if cell != 0:
            raise HTTPException(404, "No such cell.")
        box, grade = None, pred.predicted_class
    png = await run_in_threadpool(PIPELINE.explain, path, box, CLASS_NAMES.index(grade), overlay)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


def _prediction_slide(session, prediction_id):
    """The prediction and the id of the slide it belongs to, or None."""
    return session.exec(select(Prediction, SlideImage.slide_id).join(SlideImage, SlideImage.id == Prediction.slide_image_id)
                        .where(Prediction.id == prediction_id)).first()


@router.put("/predictions/{prediction_id}/feedback", tags=["feedback"])
def give_feedback(prediction_id: int, body: FeedbackIn, clinician=Depends(require("clinician")), session=Depends(db.get_session)):
    """A clinician confirms the model's grade or corrects it. One entry per prediction; sending again replaces it."""
    found = _prediction_slide(session, prediction_id)
    if found is None or found[0].error:
        raise HTTPException(404, "No such grade to review.")
    pred, slide_id = found
    corrected = None
    if body.action == "corrected":
        if not body.corrected_class or not records.valid_class(body.corrected_class):
            raise HTTPException(422, f"Choose one of: {', '.join(CLASS_NAMES)}.")
        if body.corrected_class == pred.predicted_class:
            raise HTTPException(422, "That is the grade the model already gave. Use 'confirmed' instead.")
        corrected = body.corrected_class
    now = db.now()
    entry = session.exec(select(FeedbackEntry).where(FeedbackEntry.prediction_id == prediction_id)).first()
    if entry is None:
        session.add(FeedbackEntry(prediction_id=prediction_id, clinician_id=clinician.id, action=body.action,
                                  corrected_class=corrected, created_at=now, updated_at=now))
    else:
        entry.clinician_id, entry.action, entry.corrected_class, entry.updated_at = clinician.id, body.action, corrected, now
    session.commit()
    return records.slide_detail(session, slide_id)


@router.delete("/predictions/{prediction_id}/feedback", tags=["feedback"])
def undo_feedback(prediction_id: int, clinician=Depends(require("clinician")), session=Depends(db.get_session)):
    found = _prediction_slide(session, prediction_id)
    if found is None:
        raise HTTPException(404, "No such grade.")
    session.execute(delete(FeedbackEntry).where(FeedbackEntry.prediction_id == prediction_id))
    session.commit()
    return records.slide_detail(session, found[1])
