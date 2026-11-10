"""Slides: a technician uploads a patient's images, everyone signed in can look at what they are allowed to see."""

import json
import os
import shutil
import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from core.config import CODE_RE, EXTENSIONS, MAX_BYTES, MAX_IMAGES
from db import database as db
from dependencies import can_see, current_user, require
from models import Patient, Prediction, Slide, SlideImage
from repositories import records
from services.grading import SEVERITY_RANK, TIER_RANK
from services.pipeline import PIPELINE

router = APIRouter()


@router.post("/slides", status_code=201, tags=["slides"])
async def upload_slide(patient_code: str = Form(...), note: Optional[str] = Form(None), files: list[UploadFile] = File(...),
                       user=Depends(require("technician")), session=Depends(db.get_session)):
    """A technician registers a slide for a patient code and uploads its images. Each image is graded and everything is saved."""
    code = patient_code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(422, "Use the patient's code, 3 to 32 letters, numbers, dashes or underscores, with no spaces. Never a name.")
    if not files:
        raise HTTPException(400, "Please add at least one image.")
    if len(files) > MAX_IMAGES:
        raise HTTPException(400, f"Please add at most {MAX_IMAGES} images to one slide.")
    blobs, names, types = [], [], []
    for f in files:
        if not f.content_type or not f.content_type.startswith("image/"):
            raise HTTPException(400, f"'{f.filename}' is not an image file.")
        data = await f.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, f"'{f.filename}' is larger than {MAX_BYTES // (1024 * 1024)} MB.")
        blobs.append(data); names.append((f.filename or "image")[:120]); types.append(f.content_type)

    results = await run_in_threadpool(PIPELINE.analyze_many, blobs)
    model_name, model_version = PIPELINE.classifier.identity()
    if PIPELINE.detector.ready:
        model_name = f"{PIPELINE.detector.identity} + {model_name}"

    slide_id = None
    try:
        patient = session.exec(select(Patient).where(Patient.code == code)).first()
        if patient is None:
            patient = Patient(code=code, created_at=db.now(), created_by=user.id)
            session.add(patient)
            try:
                session.flush()
            except IntegrityError:                      # another upload just created the same code
                session.rollback()
                patient = session.exec(select(Patient).where(Patient.code == code)).one()
        slide = Slide(patient_id=patient.id, uploaded_by=user.id, note=(note or "").strip()[:500] or None, created_at=db.now())
        session.add(slide)
        session.flush()
        slide_id = slide.id
        folder = db.uploads_for(slide_id)
        os.makedirs(folder, exist_ok=True)
        for pos, (data, name, ctype, res) in enumerate(zip(blobs, names, types, results), start=1):
            stored = uuid.uuid4().hex + EXTENSIONS.get(ctype, ".img")
            with open(os.path.join(folder, stored), "wb") as out:
                out.write(data)
            image = SlideImage(slide_id=slide_id, position=pos, filename=name, stored_name=stored, content_type=ctype)
            session.add(image)
            session.flush()
            if "error" in res:
                session.add(Prediction(slide_image_id=image.id, error=res["error"], model_name=model_name, model_version=model_version,
                                       mock=False, created_at=db.now()))
            else:
                session.add(Prediction(slide_image_id=image.id, predicted_class=res["predicted_class"], confidence=res["confidence"],
                                       tier=res["tier"], tier_confidence=res["tier_confidence"], low_confidence=bool(res["low_confidence"]),
                                       probabilities=json.dumps(res["probabilities"]), mode=res.get("mode"),
                                       detections=json.dumps(res["detections"]) if res.get("detections") else None,
                                       model_name=model_name, model_version=model_version, mock=bool(res["mock"]), created_at=db.now()))
        session.commit()
    except Exception:
        session.rollback()
        if slide_id:
            shutil.rmtree(db.uploads_for(slide_id), ignore_errors=True)
        raise
    return records.slide_detail(session, slide_id)


@router.get("/slides", tags=["slides"])
def list_slides(q: str = "", status: Literal["all", "needs_review", "reviewed"] = "all",
                sort: Literal["newest", "severity"] = "newest", limit: int = 200,
                user=Depends(current_user), session=Depends(db.get_session)):
    """Technicians see their own slides. Clinicians and admins see all of them."""
    stmt = records.slide_query()
    if user.role == "technician":
        stmt = stmt.where(Slide.uploaded_by == user.id)
    if q.strip():
        stmt = stmt.where(Patient.code.like(f"%{q.strip()}%"))
    rows = session.exec(stmt.order_by(Slide.created_at.desc(), Slide.id.desc())).all()
    images = records.images_for_slides(session, [row[0].id for row in rows])
    out = [records.slide_summary(row, images[row[0].id]) for row in rows]
    if status == "needs_review":
        out = [s for s in out if s["overall"]["images_read"] and not s["overall"]["fully_reviewed"]]
    elif status == "reviewed":
        out = [s for s in out if s["overall"]["fully_reviewed"]]
    if sort == "severity":
        out.sort(key=lambda s: (-(TIER_RANK[s["overall"]["tier"]] if s["overall"]["tier"] else -1),
                                -(SEVERITY_RANK[s["overall"]["class"]] if s["overall"]["class"] else 0), s["created_at"]))
    return out[:max(1, min(limit, 500))]


@router.get("/slides/{slide_id}", tags=["slides"])
def get_slide(slide_id: int, user=Depends(current_user), session=Depends(db.get_session)):
    slide = session.get(Slide, slide_id)
    if slide is None or not can_see(user, slide.uploaded_by):
        raise HTTPException(404, "No such slide.")
    return records.slide_detail(session, slide_id)


@router.get("/slides/{slide_id}/images/{image_id}", tags=["slides"])
def get_image(slide_id: int, image_id: int, user=Depends(current_user), session=Depends(db.get_session)):
    row = session.exec(select(SlideImage, Slide.uploaded_by).join(Slide, Slide.id == SlideImage.slide_id)
                       .where(SlideImage.id == image_id, SlideImage.slide_id == slide_id)).first()
    if row is None or not can_see(user, row[1]):
        raise HTTPException(404, "No such image.")
    image = row[0]
    path = os.path.join(db.uploads_for(slide_id), image.stored_name)
    if not os.path.exists(path):
        raise HTTPException(404, "The image file is missing.")
    return FileResponse(path, media_type=image.content_type, headers={"Cache-Control": "private, max-age=3600"})


@router.delete("/slides/{slide_id}", status_code=204, tags=["slides"])
def remove_slide(slide_id: int, admin=Depends(require("admin")), session=Depends(db.get_session)):
    slide = session.get(Slide, slide_id)
    if slide is None:
        raise HTTPException(404, "No such slide.")
    shutil.rmtree(db.uploads_for(slide_id), ignore_errors=True)
    session.delete(slide)
    session.commit()
