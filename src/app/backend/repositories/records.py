"""
Turns database rows into the dicts the API returns, and works out the overall result of a slide.

The overall result of a slide is its most serious finding. Each image counts with its final grade:
the clinician's if they have reviewed it (confirmed or corrected), otherwise the model's.
Order: group first (high > low > negative), then the exact grade, then the model's confidence for
images nobody has reviewed yet.
"""

import json

from sqlmodel import select

from models import FeedbackEntry, Patient, Prediction, Slide, SlideImage, User
from services.grading import CLASS_NAMES, SEVERITY_RANK, TIER_LABELS, TIER_RANK, tier_of_class


def _prediction(pred):
    if pred is None:
        return None
    if pred.error:
        return {"id": pred.id, "error": pred.error}
    return {
        "id": pred.id,
        "predicted_class": pred.predicted_class,
        "confidence": pred.confidence,
        "tier": pred.tier,
        "tier_label": TIER_LABELS[pred.tier],
        "tier_confidence": pred.tier_confidence,
        "low_confidence": bool(pred.low_confidence),
        "probabilities": json.loads(pred.probabilities),
        "mode": pred.mode or "cell",
        "detections": json.loads(pred.detections) if pred.detections else None,
        "model_name": pred.model_name,
        "model_version": pred.model_version,
        "mock": bool(pred.mock),
    }


def _feedback(fb, clinician_name):
    if fb is None:
        return None
    return {
        "id": fb.id,
        "action": fb.action,
        "corrected_class": fb.corrected_class,
        "clinician_id": fb.clinician_id,
        "clinician_name": clinician_name,
        "updated_at": fb.updated_at,
    }


def image_dict(image, pred, fb, clinician_name):
    pred, fb = _prediction(pred), _feedback(fb, clinician_name)
    final_class = final_tier = None
    if pred and "error" not in pred:
        final_class = fb["corrected_class"] if fb and fb["action"] == "corrected" else pred["predicted_class"]
        final_tier = tier_of_class(final_class) if fb else pred["tier"]
    return {"id": image.id, "position": image.position, "filename": image.filename,
            "prediction": pred, "feedback": fb, "final_class": final_class, "final_tier": final_tier}


def overall_of(images):
    """The overall result for a list of image dicts (see the module note), or None if nothing was readable."""
    readable = [im for im in images if im["final_class"]]
    reviewed = sum(1 for im in readable if im["feedback"])
    base = {"images_total": len(images), "images_read": len(readable), "images_reviewed": reviewed,
            "fully_reviewed": bool(readable) and reviewed == len(readable)}
    if not readable:
        return {**base, "tier": None, "tier_label": None, "class": None, "image_id": None, "position": None,
                "low_confidence_images": 0, "mock": False}

    def key(im):
        return (TIER_RANK[im["final_tier"]], SEVERITY_RANK[im["final_class"]],
                1.0 if im["feedback"] else im["prediction"]["confidence"])

    best = max(readable, key=key)
    return {**base, "tier": best["final_tier"], "tier_label": TIER_LABELS[best["final_tier"]], "class": best["final_class"],
            "image_id": best["id"], "position": best["position"],
            "low_confidence_images": sum(1 for im in readable if not im["feedback"] and im["prediction"]["low_confidence"]),
            "mock": any(im["prediction"]["mock"] for im in readable)}


def images_for_slides(session, slide_ids):
    """{slide_id: [image dicts]} for many slides in one query. Each image comes with its prediction, review and reviewer's name."""
    if not slide_ids:
        return {}
    stmt = (select(SlideImage, Prediction, FeedbackEntry, User.full_name)
            .outerjoin(Prediction, Prediction.slide_image_id == SlideImage.id)
            .outerjoin(FeedbackEntry, FeedbackEntry.prediction_id == Prediction.id)
            .outerjoin(User, User.id == FeedbackEntry.clinician_id)
            .where(SlideImage.slide_id.in_(list(slide_ids)))
            .order_by(SlideImage.slide_id, SlideImage.position))
    out = {sid: [] for sid in slide_ids}
    for image, pred, fb, clinician_name in session.exec(stmt).all():
        out[image.slide_id].append(image_dict(image, pred, fb, clinician_name))
    return out


def slide_query():
    """Slides with their patient's code and the uploader's name: rows of (slide, patient_code, uploader_name)."""
    return (select(Slide, Patient.code, User.full_name)
            .join(Patient, Patient.id == Slide.patient_id)
            .join(User, User.id == Slide.uploaded_by))


def slide_summary(row, images):
    slide, patient_code, uploader_name = row
    return {"id": slide.id, "patient_id": slide.patient_id, "patient_code": patient_code, "note": slide.note,
            "created_at": slide.created_at, "uploaded_by": slide.uploaded_by, "uploader_name": uploader_name,
            "image_count": len(images), "overall": overall_of(images)}


def slide_detail(session, slide_id):
    row = session.exec(slide_query().where(Slide.id == slide_id)).first()
    if row is None:
        return None
    images = images_for_slides(session, [slide_id])[slide_id]
    out = slide_summary(row, images)
    out["images"] = images
    return out


def valid_class(name):
    return name in CLASS_NAMES
