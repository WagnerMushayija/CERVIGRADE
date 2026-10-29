"""
SQLite storage for CerviGrade. The tables follow the entity-relationship diagram in the proposal:
users, patients, slides, slide_images, predictions and feedback_entries.

The prototype keeps everything in one folder, app_data/ in the repo root (set CERVIGRADE_DATA to move it):
  cervigrade.db   the database
  uploads/        the uploaded images, one folder per slide
  secret.key      the key that signs login tokens
SQLite needs no server. The same tables can move to PostgreSQL later.
"""

import os
import secrets
import sqlite3
from datetime import datetime, timezone

import institution
from security import hash_password

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DATA_DIR = os.environ.get("CERVIGRADE_DATA") or os.path.join(_REPO_ROOT, "app_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "cervigrade.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ROLES = ("technician", "clinician", "admin")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('technician', 'clinician', 'admin')),
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_login    TEXT
);
CREATE TABLE IF NOT EXISTS patients (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    code       TEXT NOT NULL UNIQUE,                 -- a pseudonym code, never a name
    created_at TEXT NOT NULL,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS slides (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    uploaded_by INTEGER NOT NULL REFERENCES users(id),
    note        TEXT,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slide_images (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    slide_id     INTEGER NOT NULL REFERENCES slides(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL,
    filename     TEXT NOT NULL,
    stored_name  TEXT NOT NULL,
    content_type TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS predictions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    slide_image_id   INTEGER NOT NULL UNIQUE REFERENCES slide_images(id) ON DELETE CASCADE,
    error            TEXT,
    predicted_class  TEXT,
    confidence       REAL,
    tier             TEXT,
    tier_confidence  REAL,
    low_confidence   INTEGER,
    probabilities    TEXT,                           -- JSON, six numbers
    mode             TEXT,                           -- 'field' (detector + CNN), 'cell' (one cell) or 'whole'
    detections       TEXT,                           -- JSON: boxes, per-box grade, which counted (field mode only)
    model_name       TEXT NOT NULL,
    model_version    TEXT NOT NULL,
    mock             INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prediction_id   INTEGER NOT NULL UNIQUE REFERENCES predictions(id) ON DELETE CASCADE,  -- at most one per prediction
    clinician_id    INTEGER NOT NULL REFERENCES users(id),
    action          TEXT NOT NULL CHECK (action IN ('confirmed', 'corrected')),
    corrected_class TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_slides_patient ON slides(patient_id);
CREATE INDEX IF NOT EXISTS idx_images_slide ON slide_images(slide_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """FastAPI dependency: one connection per request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        have = {r[1] for r in conn.execute("PRAGMA table_info(predictions)")}
        for col in ("mode", "detections"):          # databases made before the detector was added
            if col not in have:
                conn.execute(f"ALTER TABLE predictions ADD COLUMN {col} TEXT")
        conn.commit()
    finally:
        conn.close()


def create_user(conn, username, full_name, role, password) -> int:
    cur = conn.execute(
        "INSERT INTO users (username, full_name, role, password_hash, active, created_at) VALUES (?, ?, ?, ?, 1, ?)",
        (username, full_name, role, hash_password(password), now()))
    conn.commit()
    return cur.lastrowid


def adopt_institution_emails():
    """
    Accounts made before the email rule have plain usernames ('admin', 'tech1'). Without a fix nobody could sign in,
    the administrator included, so each one gets the institution domain added to its name ('admin' -> 'admin@alustudent.com').
    Names that are already allowed are left alone, and so is any name whose new form is already taken.
    """
    if institution.OPEN_TO_ANY:
        return
    domain = institution.DOMAINS[0]
    conn = connect()
    try:
        taken = {r[0] for r in conn.execute("SELECT username FROM users")}
        for (uid, name) in conn.execute("SELECT id, username FROM users").fetchall():
            if institution.is_institutional(name):
                continue
            new = f"{name}@{domain}"
            if "@" in name or new in taken or not institution.is_institutional(new):
                print(f"[accounts] '{name}' cannot sign in: it is not an {institution.describe_domains()} address. Rename it or add a new account.")
                continue
            conn.execute("UPDATE users SET username = ? WHERE id = ?", (new, uid))
            taken.add(new)
            print(f"[accounts] '{name}' is now '{new}' (accounts must use an {institution.describe_domains()} address).")
        conn.commit()
    finally:
        conn.close()


def bootstrap_admin():
    """On the very first start there are no users, so create one admin and say so in the terminal."""
    conn = connect()
    try:
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
            return
        password = os.environ.get("CERVIGRADE_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        email = institution.default_admin_email()
        create_user(conn, email, "Administrator", "admin", password)
        shown = "(the one you set in CERVIGRADE_ADMIN_PASSWORD)" if os.environ.get("CERVIGRADE_ADMIN_PASSWORD") else password
        print("\n" + "=" * 62)
        print(" First start: an admin account was created.")
        print(f"   email:    {email}")
        print(f"   password: {shown}")
        print(" Sign in, then add your technicians and clinicians under Users.")
        print("=" * 62 + "\n")
    finally:
        conn.close()


def uploads_for(slide_id: int) -> str:
    return os.path.join(UPLOAD_DIR, str(slide_id))
