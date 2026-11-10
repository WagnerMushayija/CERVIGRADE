"""Patient codes. A code is a pseudonym, never a name."""

import shutil

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from core.config import CODE_RE
from db import database as db
from dependencies import current_user, require
from models import Patient, Slide
from schemas.patients import PatientPatch

router = APIRouter()


@router.get("/patients", tags=["patients"])
def list_patients(user=Depends(current_user), session=Depends(db.get_session)):
    rows = session.exec(
        select(Patient.id, Patient.code, Patient.created_at,
               func.count(Slide.id).label("slide_count"), func.max(Slide.created_at).label("last_slide_at"))
        .outerjoin(Slide, Slide.patient_id == Patient.id)
        .group_by(Patient.id).order_by(Patient.code)).all()
    return [dict(r._mapping) for r in rows]


@router.patch("/patients/{patient_id}", tags=["patients"])
def rename_patient(patient_id: int, body: PatientPatch, admin=Depends(require("admin")), session=Depends(db.get_session)):
    code = body.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(422, "A patient code is 3 to 32 letters, numbers, dashes or underscores, with no spaces.")
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "No such patient.")
    patient.code = code
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, f"The code '{code}' already exists.")
    return {"id": patient.id, "code": patient.code, "created_at": patient.created_at}


@router.delete("/patients/{patient_id}", status_code=204, tags=["patients"])
def remove_patient(patient_id: int, admin=Depends(require("admin")), session=Depends(db.get_session)):
    patient = session.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(404, "No such patient.")
    for slide_id in session.exec(select(Slide.id).where(Slide.patient_id == patient_id)).all():
        shutil.rmtree(db.uploads_for(slide_id), ignore_errors=True)
    session.delete(patient)          # slides, images, predictions and feedback follow (the tables cascade)
    session.commit()
