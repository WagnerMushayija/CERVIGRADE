"""The web page itself, the redirect from the front door, and the liveness check."""

import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from core import institution
from core.config import FRONTEND_FILE
from services.grading import CLASS_NAMES, LOW_CONFIDENCE, SEVERITY_ORDER, TIER_LABELS, TIER_MEMBERS
from services.pipeline import PIPELINE

router = APIRouter()


@router.get("/", include_in_schema=False)
def root():
    """Visitors land on the web page when it is next to the backend, otherwise on the Swagger docs."""
    return RedirectResponse(url="/app" if os.path.exists(FRONTEND_FILE) else "/docs")


@router.get("/app", include_in_schema=False)
def web_page():
    """The web page itself, so one address (this server's) serves everything: handy locally and behind a tunnel or a host."""
    if not os.path.exists(FRONTEND_FILE):
        raise HTTPException(404, "The web page file was not found next to the backend.")
    return FileResponse(FRONTEND_FILE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/health", tags=["status"])
def health():
    """Liveness check. Also says whether real model weights are loaded or the stub predictor is running."""
    name, version = PIPELINE.classifier.identity()
    return {"status": "ok", "classes": CLASS_NAMES, "severity_order": SEVERITY_ORDER, "tiers": TIER_MEMBERS,
            "tier_labels": TIER_LABELS, "low_confidence_below": LOW_CONFIDENCE, "using_real_model": PIPELINE.classifier.is_real,
            "model_name": name, "model_version": version, "detector": PIPELINE.detector.identity,
            "detector_conf": PIPELINE.detector.conf, "cnn_sure": PIPELINE.cnn_sure,
            "email_domains": None if institution.OPEN_TO_ANY else list(institution.DOMAINS)}
