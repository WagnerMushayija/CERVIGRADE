"""
CerviGrade API.

Run with:
    uvicorn main:app --reload --port 8000

Then open:
    http://localhost:8000/docs   (Swagger UI: press Authorize after signing in through /auth/login)
    ../frontend/index.html       (the web page, calls this API)

Three kinds of user, as in the proposal's use case diagram:
  technician  registers a patient's slide (a pseudonym code) and uploads its images
  clinician   reviews each grade: confirms or corrects it
  admin       the data scientist: manages users, patients and slides, and sees the model status

Images are stored in app_data/uploads on this computer and are removed when a slide is deleted.
Research prototype, not a medical device.
"""

import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from typing import Literal, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import db
import institution
import records
from model import CLASS_NAMES, LOW_CONFIDENCE, SEVERITY_ORDER, TIER_LABELS, TIER_MEMBERS, TIER_RANK, SEVERITY_RANK, tier_of_class
from pipeline import PIPELINE
from security import TokenService, load_secret, verify_password
from users import UserRepository

MAX_IMAGES = 40
MAX_BYTES = 15 * 1024 * 1024     # per image
CODE_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")           # a code, so no spaces and no room for a name
EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/bmp": ".bmp", "image/tiff": ".tif", "image/webp": ".webp"}

db.init_db()
db.adopt_institution_emails()
db.bootstrap_admin()
tokens = TokenService(load_secret(db.DATA_DIR))

app = FastAPI(
    title="CerviGrade API",
    description=("Severity grading for cervical cytology cell images, with sign-in, roles and saved records. "
                 "Each image gets a Bethesda grade and one of three groups (negative, low-grade, high-grade). "
                 "A slide's overall result is its most serious finding, using the clinician's confirmed grade where there is one. "
                 "Research prototype, not a medical device."),
    version="0.5.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # fine on a laptop (tokens travel in a header, not a cookie); restrict before any real deployment
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ sign-in helpers

bearer = HTTPBearer(auto_error=False)
PUBLIC_USER_FIELDS = ("id", "username", "full_name", "role", "active", "created_at", "last_login")


def public_user(row):
    d = {k: row[k] for k in PUBLIC_USER_FIELDS}
    d["active"] = bool(d["active"])
    return d


def get_users(conn=Depends(db.get_db)):
    """One UserRepository per request, on the same connection as everything else in that request."""
    return UserRepository(conn)


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), users=Depends(get_users)):
    if creds is None:
        raise HTTPException(401, "Please sign in.")
    uid = tokens.read(creds.credentials)
    row = users.by_id(uid) if uid else None
    if row is None or not row["active"]:
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    if not institution.is_institutional(row["username"]):
        raise HTTPException(403, institution.rejection_message())
    return dict(row)


def require(*roles):
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user
    return dep


_failures = {}      # username -> times of recent wrong passwords
MAX_FAILURES, WINDOW_SECONDS = 5, 300


def _throttled(username):
    recent = [t for t in _failures.get(username, []) if time.time() - t < WINDOW_SECONDS]
    _failures[username] = recent
    return len(recent) >= MAX_FAILURES


# ------------------------------------------------------------------ small input models

class LoginIn(BaseModel):
    username: str
    password: str


class PasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserIn(BaseModel):
    username: str
    full_name: str = Field(min_length=2, max_length=80)
    role: Literal["technician", "clinician", "admin"]
    password: str = Field(min_length=8, max_length=128)


class UserPatch(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    role: Optional[Literal["technician", "clinician", "admin"]] = None
    active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class PatientPatch(BaseModel):
    code: str


class FeedbackIn(BaseModel):
    action: Literal["confirmed", "corrected"]
    corrected_class: Optional[str] = None


# ------------------------------------------------------------------ status

FRONTEND_FILE = os.environ.get("CERVIGRADE_FRONTEND", os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html"))


# The page's own stylesheet and scripts (css/ and js/ next to index.html), served at /css and /js so the page can load them.
for _folder in ("css", "js"):
    _path = os.path.join(os.path.dirname(FRONTEND_FILE), _folder)
    if os.path.isdir(_path):
        app.mount(f"/{_folder}", StaticFiles(directory=_path), name=_folder)


@app.get("/", include_in_schema=False)
def root():
    """Visitors land on the web page when it is next to the backend, otherwise on the Swagger docs."""
    return RedirectResponse(url="/app" if os.path.exists(FRONTEND_FILE) else "/docs")


@app.get("/app", include_in_schema=False)
def web_page():
    """The web page itself, so one address (this server's) serves everything: handy locally and behind a tunnel or a host."""
    if not os.path.exists(FRONTEND_FILE):
        raise HTTPException(404, "The web page file was not found next to the backend.")
    return FileResponse(FRONTEND_FILE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/health", tags=["status"])
def health():
    """Liveness check. Also says whether real model weights are loaded or the stub predictor is running."""
    name, version = PIPELINE.classifier.identity()
    return {"status": "ok", "classes": CLASS_NAMES, "severity_order": SEVERITY_ORDER, "tiers": TIER_MEMBERS,
            "tier_labels": TIER_LABELS, "low_confidence_below": LOW_CONFIDENCE, "using_real_model": PIPELINE.classifier.is_real,
            "model_name": name, "model_version": version, "detector": PIPELINE.detector.identity,
            "detector_conf": PIPELINE.detector.conf, "cnn_sure": PIPELINE.cnn_sure,
            "email_domains": None if institution.OPEN_TO_ANY else list(institution.DOMAINS)}


# ------------------------------------------------------------------ auth

@app.post("/auth/login", tags=["auth"])
def login(body: LoginIn, users=Depends(get_users)):
    username = institution.normalise(body.username)
    if not institution.is_institutional(username):
        raise HTTPException(403, institution.rejection_message())
    if _throttled(username):
        raise HTTPException(429, "Too many wrong passwords. Wait a few minutes and try again.")
    row = users.by_username(username)
    if row is None or not row["active"] or not verify_password(body.password, row["password_hash"]):
        _failures.setdefault(username, []).append(time.time())
        raise HTTPException(401, "Wrong email or password.")
    _failures.pop(username, None)
    users.record_login(row["id"])
    return {"token": tokens.make(row["id"]), "user": public_user(row)}


@app.get("/auth/me", tags=["auth"])
def me(user=Depends(current_user)):
    return {k: user[k] if k != "active" else bool(user[k]) for k in PUBLIC_USER_FIELDS}


@app.post("/auth/change-password", tags=["auth"])
def change_password(body: PasswordIn, user=Depends(current_user), users=Depends(get_users)):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(400, "The current password is not right.")
    users.set_password(user["id"], body.new_password)
    return {"ok": True}


# ------------------------------------------------------------------ users (admin)

@app.get("/users", tags=["users"])
def list_users(admin=Depends(require("admin")), users=Depends(get_users)):
    return [{**public_user(r), "slides_uploaded": r["slides_uploaded"], "reviews_made": r["reviews_made"]} for r in users.list_with_activity()]


@app.post("/users", status_code=201, tags=["users"])
def add_user(body: UserIn, admin=Depends(require("admin")), users=Depends(get_users)):
    username = institution.normalise(body.username)
    if not institution.is_institutional(username):
        raise HTTPException(422, institution.rejection_message())
    try:
        uid = users.create(username, body.full_name.strip(), body.role, body.password)
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"An account for {username} already exists.")
    return public_user(users.by_id(uid))


@app.patch("/users/{user_id}", tags=["users"])
def edit_user(user_id: int, body: UserPatch, admin=Depends(require("admin")), users=Depends(get_users)):
    row = users.by_id(user_id)
    if row is None:
        raise HTTPException(404, "No such user.")
    losing_admin = row["role"] == "admin" and row["active"] and (body.role not in (None, "admin") or body.active is False)
    if losing_admin and users.count_active_admins() <= 1:
        raise HTTPException(409, "This is the last active admin. Make another admin first.")
    if user_id == admin["id"] and body.active is False:
        raise HTTPException(409, "You cannot deactivate your own account.")
    users.update(user_id, full_name=body.full_name, role=body.role, active=body.active, password=body.password)
    return public_user(users.by_id(user_id))


@app.delete("/users/{user_id}", status_code=204, tags=["users"])
def remove_user(user_id: int, admin=Depends(require("admin")), users=Depends(get_users)):
    row = users.by_id(user_id)
    if row is None:
        raise HTTPException(404, "No such user.")
    if user_id == admin["id"]:
        raise HTTPException(409, "You cannot delete your own account.")
    if row["role"] == "admin" and row["active"] and users.count_active_admins() <= 1:
        raise HTTPException(409, "This is the last active admin.")
    if users.usage_count(user_id):
        raise HTTPException(409, "This user has uploaded slides or reviewed grades, so the records need them. Deactivate the account instead.")
    try:
        users.delete(user_id)
    except sqlite3.IntegrityError:
        raise HTTPException(409, "This user is still referenced by other records. Deactivate the account instead.")


# ------------------------------------------------------------------ review statistics

@app.get("/stats/review", tags=["stats"])
def review_stats(admin=Depends(require("admin")), conn=Depends(db.get_db)):
    """
    How often the clinicians agreed with the tool. Counts photos (one prediction each), not single cells.
    This is agreement with a reviewer, not accuracy: it only covers photos a clinician has opened.
    """
    row = conn.execute("""
        SELECT COUNT(*) AS graded,
               COALESCE(SUM(f.id IS NOT NULL), 0) AS reviewed,
               COALESCE(SUM(f.action = 'confirmed'), 0) AS confirmed,
               COALESCE(SUM(f.action = 'corrected'), 0) AS corrected
        FROM predictions p LEFT JOIN feedback_entries f ON f.prediction_id = p.id
        WHERE p.error IS NULL AND p.mock = 0""").fetchone()
    fixes = conn.execute("""
        SELECT p.predicted_class AS model, f.corrected_class AS clinician, COUNT(*) AS n
        FROM predictions p JOIN feedback_entries f ON f.prediction_id = p.id
        WHERE f.action = 'corrected' AND p.error IS NULL AND p.mock = 0
        GROUP BY p.predicted_class, f.corrected_class ORDER BY n DESC, model, clinician""").fetchall()
    corrections = [dict(r) for r in fixes]
    group_changed = sum(c["n"] for c in corrections if tier_of_class(c["model"]) != tier_of_class(c["clinician"]))
    out = dict(row)
    out["waiting"] = out["graded"] - out["reviewed"]
    out["group_changed"] = group_changed
    out["corrections"] = corrections[:5]
    return out


# ------------------------------------------------------------------ patients

@app.get("/patients", tags=["patients"])
def list_patients(user=Depends(current_user), conn=Depends(db.get_db)):
    rows = conn.execute("""
        SELECT p.id, p.code, p.created_at, COUNT(s.id) AS slide_count, MAX(s.created_at) AS last_slide_at
        FROM patients p LEFT JOIN slides s ON s.patient_id = p.id GROUP BY p.id ORDER BY p.code""").fetchall()
    return [dict(r) for r in rows]


@app.patch("/patients/{patient_id}", tags=["patients"])
def rename_patient(patient_id: int, body: PatientPatch, admin=Depends(require("admin")), conn=Depends(db.get_db)):
    code = body.code.strip()
    if not CODE_RE.match(code):
        raise HTTPException(422, "A patient code is 3 to 32 letters, numbers, dashes or underscores, with no spaces.")
    try:
        cur = conn.execute("UPDATE patients SET code = ? WHERE id = ?", (code, patient_id))
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, f"The code '{code}' already exists.")
    if cur.rowcount == 0:
        raise HTTPException(404, "No such patient.")
    return dict(conn.execute("SELECT id, code, created_at FROM patients WHERE id = ?", (patient_id,)).fetchone())


@app.delete("/patients/{patient_id}", status_code=204, tags=["patients"])
def remove_patient(patient_id: int, admin=Depends(require("admin")), conn=Depends(db.get_db)):
    if conn.execute("SELECT 1 FROM patients WHERE id = ?", (patient_id,)).fetchone() is None:
        raise HTTPException(404, "No such patient.")
    for (sid,) in conn.execute("SELECT id FROM slides WHERE patient_id = ?", (patient_id,)).fetchall():
        shutil.rmtree(db.uploads_for(sid), ignore_errors=True)
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))      # slides, images, predictions and feedback follow
    conn.commit()


# ------------------------------------------------------------------ slides

def _can_see(user, slide_row):
    return user["role"] != "technician" or slide_row["uploaded_by"] == user["id"]


@app.post("/slides", status_code=201, tags=["slides"])
async def upload_slide(patient_code: str = Form(...), note: Optional[str] = Form(None), files: list[UploadFile] = File(...),
                       user=Depends(require("technician")), conn=Depends(db.get_db)):
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
        conn.execute("INSERT OR IGNORE INTO patients (code, created_at, created_by) VALUES (?, ?, ?)", (code, db.now(), user["id"]))
        patient_id = conn.execute("SELECT id FROM patients WHERE code = ?", (code,)).fetchone()[0]
        slide_id = conn.execute("INSERT INTO slides (patient_id, uploaded_by, note, created_at) VALUES (?, ?, ?, ?)",
                                (patient_id, user["id"], (note or "").strip()[:500] or None, db.now())).lastrowid
        folder = db.uploads_for(slide_id)
        os.makedirs(folder, exist_ok=True)
        for pos, (data, name, ctype, res) in enumerate(zip(blobs, names, types, results), start=1):
            stored = uuid.uuid4().hex + EXTENSIONS.get(ctype, ".img")
            with open(os.path.join(folder, stored), "wb") as out:
                out.write(data)
            image_id = conn.execute("INSERT INTO slide_images (slide_id, position, filename, stored_name, content_type) VALUES (?, ?, ?, ?, ?)",
                                    (slide_id, pos, name, stored, ctype)).lastrowid
            if "error" in res:
                conn.execute("INSERT INTO predictions (slide_image_id, error, model_name, model_version, mock, created_at) VALUES (?, ?, ?, ?, 0, ?)",
                             (image_id, res["error"], model_name, model_version, db.now()))
            else:
                conn.execute("""INSERT INTO predictions (slide_image_id, predicted_class, confidence, tier, tier_confidence, low_confidence,
                                probabilities, mode, detections, model_name, model_version, mock, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                             (image_id, res["predicted_class"], res["confidence"], res["tier"], res["tier_confidence"], int(res["low_confidence"]),
                              json.dumps(res["probabilities"]), res.get("mode"),
                              json.dumps(res["detections"]) if res.get("detections") else None, model_name, model_version, int(res["mock"]), db.now()))
        conn.commit()
    except Exception:
        conn.rollback()
        if slide_id:
            shutil.rmtree(db.uploads_for(slide_id), ignore_errors=True)
        raise
    return records.slide_detail(conn, slide_id)


@app.get("/slides", tags=["slides"])
def list_slides(q: str = "", status: Literal["all", "needs_review", "reviewed"] = "all",
                sort: Literal["newest", "severity"] = "newest", limit: int = 200,
                user=Depends(current_user), conn=Depends(db.get_db)):
    """Technicians see their own slides. Clinicians and admins see all of them."""
    sql = records.SLIDE_QUERY + " WHERE 1 = 1"
    args = []
    if user["role"] == "technician":
        sql += " AND s.uploaded_by = ?"; args.append(user["id"])
    if q.strip():
        sql += " AND pt.code LIKE ?"; args.append(f"%{q.strip()}%")
    rows = conn.execute(sql + " ORDER BY s.created_at DESC, s.id DESC", args).fetchall()
    images = records.images_for_slides(conn, [r["id"] for r in rows])
    out = [records.slide_summary(r, images[r["id"]]) for r in rows]
    if status == "needs_review":
        out = [s for s in out if s["overall"]["images_read"] and not s["overall"]["fully_reviewed"]]
    elif status == "reviewed":
        out = [s for s in out if s["overall"]["fully_reviewed"]]
    if sort == "severity":
        out.sort(key=lambda s: (-(TIER_RANK[s["overall"]["tier"]] if s["overall"]["tier"] else -1),
                                -(SEVERITY_RANK[s["overall"]["class"]] if s["overall"]["class"] else 0), s["created_at"]))
    return out[:max(1, min(limit, 500))]


@app.get("/slides/{slide_id}", tags=["slides"])
def get_slide(slide_id: int, user=Depends(current_user), conn=Depends(db.get_db)):
    row = conn.execute("SELECT uploaded_by FROM slides WHERE id = ?", (slide_id,)).fetchone()
    if row is None or not _can_see(user, row):
        raise HTTPException(404, "No such slide.")
    return records.slide_detail(conn, slide_id)


@app.get("/slides/{slide_id}/images/{image_id}", tags=["slides"])
def get_image(slide_id: int, image_id: int, user=Depends(current_user), conn=Depends(db.get_db)):
    row = conn.execute("""SELECT si.stored_name, si.content_type, s.uploaded_by FROM slide_images si JOIN slides s ON s.id = si.slide_id
                          WHERE si.id = ? AND si.slide_id = ?""", (image_id, slide_id)).fetchone()
    if row is None or not _can_see(user, row):
        raise HTTPException(404, "No such image.")
    path = os.path.join(db.uploads_for(slide_id), row["stored_name"])
    if not os.path.exists(path):
        raise HTTPException(404, "The image file is missing.")
    return FileResponse(path, media_type=row["content_type"], headers={"Cache-Control": "private, max-age=3600"})


@app.get("/predictions/{prediction_id}/cam", tags=["explain"])
async def prediction_cam(prediction_id: int, cell: int = 0, overlay: bool = True, user=Depends(current_user), conn=Depends(db.get_db)):
    """
    Grad-CAM for one cell of a photo: the cell crop with a heat overlay showing where the model looked for the grade it gave.
    cell is the box number from the photo's detections (0 for a photo graded as a single cell). overlay=false gives the plain crop.
    """
    row = conn.execute("""SELECT p.error, p.predicted_class, p.mode, p.detections, si.slide_id, si.stored_name, s.uploaded_by
                          FROM predictions p JOIN slide_images si ON si.id = p.slide_image_id JOIN slides s ON s.id = si.slide_id
                          WHERE p.id = ?""", (prediction_id,)).fetchone()
    if row is None or not _can_see(user, row) or row["error"]:
        raise HTTPException(404, "No such prediction.")
    if not PIPELINE.classifier.is_real:
        raise HTTPException(409, "The explanation needs the real model, and only the placeholder is running.")
    path = os.path.join(db.uploads_for(row["slide_id"]), row["stored_name"])
    if not os.path.exists(path):
        raise HTTPException(404, "The image file is missing.")
    if row["detections"]:
        cells = json.loads(row["detections"])["cells"]
        if not 0 <= cell < len(cells):
            raise HTTPException(404, "No such cell.")
        box, grade = cells[cell]["box"], cells[cell]["cls"]
    else:
        if cell != 0:
            raise HTTPException(404, "No such cell.")
        box, grade = None, row["predicted_class"]
    png = await run_in_threadpool(PIPELINE.explain, path, box, CLASS_NAMES.index(grade), overlay)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.delete("/slides/{slide_id}", status_code=204, tags=["slides"])
def remove_slide(slide_id: int, admin=Depends(require("admin")), conn=Depends(db.get_db)):
    if conn.execute("SELECT 1 FROM slides WHERE id = ?", (slide_id,)).fetchone() is None:
        raise HTTPException(404, "No such slide.")
    shutil.rmtree(db.uploads_for(slide_id), ignore_errors=True)
    conn.execute("DELETE FROM slides WHERE id = ?", (slide_id,))
    conn.commit()


# ------------------------------------------------------------------ clinician feedback

def _prediction_slide(conn, prediction_id):
    return conn.execute("""SELECT p.id, p.error, p.predicted_class, si.slide_id FROM predictions p
                           JOIN slide_images si ON si.id = p.slide_image_id WHERE p.id = ?""", (prediction_id,)).fetchone()


@app.put("/predictions/{prediction_id}/feedback", tags=["feedback"])
def give_feedback(prediction_id: int, body: FeedbackIn, clinician=Depends(require("clinician")), conn=Depends(db.get_db)):
    """A clinician confirms the model's grade or corrects it. One entry per prediction; sending again replaces it."""
    pred = _prediction_slide(conn, prediction_id)
    if pred is None or pred["error"]:
        raise HTTPException(404, "No such grade to review.")
    corrected = None
    if body.action == "corrected":
        if not body.corrected_class or not records.valid_class(body.corrected_class):
            raise HTTPException(422, f"Choose one of: {', '.join(CLASS_NAMES)}.")
        if body.corrected_class == pred["predicted_class"]:
            raise HTTPException(422, "That is the grade the model already gave. Use 'confirmed' instead.")
        corrected = body.corrected_class
    now = db.now()
    conn.execute("""INSERT INTO feedback_entries (prediction_id, clinician_id, action, corrected_class, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(prediction_id) DO UPDATE SET clinician_id = excluded.clinician_id, action = excluded.action,
                    corrected_class = excluded.corrected_class, updated_at = excluded.updated_at""",
                 (prediction_id, clinician["id"], body.action, corrected, now, now))
    conn.commit()
    return records.slide_detail(conn, pred["slide_id"])


@app.delete("/predictions/{prediction_id}/feedback", tags=["feedback"])
def undo_feedback(prediction_id: int, clinician=Depends(require("clinician")), conn=Depends(db.get_db)):
    pred = _prediction_slide(conn, prediction_id)
    if pred is None:
        raise HTTPException(404, "No such grade.")
    conn.execute("DELETE FROM feedback_entries WHERE prediction_id = ?", (prediction_id,))
    conn.commit()
    return records.slide_detail(conn, pred["slide_id"])
