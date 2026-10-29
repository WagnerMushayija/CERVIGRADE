"""
Turns database rows into the dicts the API returns, and works out the overall result of a slide.

The overall result of a slide is its most serious finding. Each image counts with its final grade:
the clinician's if they have reviewed it (confirmed or corrected), otherwise the model's.
Order: group first (high > low > negative), then the exact grade, then the model's confidence for
images nobody has reviewed yet.
"""

import json

from model import CLASS_NAMES, SEVERITY_RANK, TIER_LABELS, TIER_RANK, tier_of_class


def _prediction(row):
    if row["pred_id"] is None:
        return None
    if row["error"]:
        return {"id": row["pred_id"], "error": row["error"]}
    return {
        "id": row["pred_id"],
        "predicted_class": row["predicted_class"],
        "confidence": row["confidence"],
        "tier": row["tier"],
        "tier_label": TIER_LABELS[row["tier"]],
        "tier_confidence": row["tier_confidence"],
        "low_confidence": bool(row["low_confidence"]),
        "probabilities": json.loads(row["probabilities"]),
        "mode": row["mode"] or "cell",
        "detections": json.loads(row["detections"]) if row["detections"] else None,
        "model_name": row["model_name"],
        "model_version": row["model_version"],
        "mock": bool(row["mock"]),
    }


def _feedback(row):
    if row["fb_id"] is None:
        return None
    return {
        "id": row["fb_id"],
        "action": row["fb_action"],
        "corrected_class": row["fb_corrected"],
        "clinician_id": row["fb_clinician_id"],
        "clinician_name": row["fb_clinician_name"],
        "updated_at": row["fb_updated"],
    }


IMAGE_QUERY = """
SELECT si.id AS image_id, si.slide_id, si.position, si.filename,
       p.id AS pred_id, p.error, p.predicted_class, p.confidence, p.tier, p.tier_confidence, p.low_confidence,
       p.probabilities, p.mode, p.detections, p.model_name, p.model_version, p.mock,
       f.id AS fb_id, f.action AS fb_action, f.corrected_class AS fb_corrected, f.clinician_id AS fb_clinician_id,
       f.updated_at AS fb_updated, u.full_name AS fb_clinician_name
FROM slide_images si
LEFT JOIN predictions p ON p.slide_image_id = si.id
LEFT JOIN feedback_entries f ON f.prediction_id = p.id
LEFT JOIN users u ON u.id = f.clinician_id
"""


def image_dict(row):
    pred, fb = _prediction(row), _feedback(row)
    final_class = final_tier = None
    if pred and "error" not in pred:
        final_class = fb["corrected_class"] if fb and fb["action"] == "corrected" else pred["predicted_class"]
        final_tier = tier_of_class(final_class) if fb else pred["tier"]
    return {"id": row["image_id"], "position": row["position"], "filename": row["filename"],
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


def images_for_slides(conn, slide_ids):
    """{slide_id: [image dicts]} for many slides in one query."""
    if not slide_ids:
        return {}
    marks = ",".join("?" * len(slide_ids))
    rows = conn.execute(IMAGE_QUERY + f" WHERE si.slide_id IN ({marks}) ORDER BY si.slide_id, si.position", list(slide_ids)).fetchall()
    out = {sid: [] for sid in slide_ids}
    for r in rows:
        out[r["slide_id"]].append(image_dict(r))
    return out


SLIDE_QUERY = """
SELECT s.id, s.note, s.created_at, s.uploaded_by, pt.id AS patient_id, pt.code AS patient_code, u.full_name AS uploader_name
FROM slides s JOIN patients pt ON pt.id = s.patient_id JOIN users u ON u.id = s.uploaded_by
"""


def slide_summary(row, images):
    return {"id": row["id"], "patient_id": row["patient_id"], "patient_code": row["patient_code"], "note": row["note"],
            "created_at": row["created_at"], "uploaded_by": row["uploaded_by"], "uploader_name": row["uploader_name"],
            "image_count": len(images), "overall": overall_of(images)}


def slide_detail(conn, slide_id):
    row = conn.execute(SLIDE_QUERY + " WHERE s.id = ?", (slide_id,)).fetchone()
    if row is None:
        return None
    images = images_for_slides(conn, [slide_id])[slide_id]
    out = slide_summary(row, images)
    out["images"] = images
    return out


def valid_class(name):
    return name in CLASS_NAMES
