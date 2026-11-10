"""
The database for CerviGrade, through SQLModel (an ORM): the tables are the Python classes in models/, and the
queries are written in Python instead of SQL text. The tables follow the entity-relationship diagram in the proposal:
users, patients, slides, slide_images, predictions and feedback_entries.

The prototype keeps everything in one folder, app_data/ in the repo root (set CERVIGRADE_DATA to move it):
  cervigrade.db   the database (a SQLite file, which needs no server)
  uploads/        the uploaded images, one folder per slide
  secret.key      the key that signs login tokens
Changing to PostgreSQL later means changing DATABASE_URL below, not the queries.
"""

import os
import secrets
from datetime import datetime, timezone

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine, func, select

import models                                    # noqa: F401  (importing it registers every table)
from core import institution
from core.config import REPO_ROOT
from models import User

DATA_DIR = os.environ.get("CERVIGRADE_DATA") or os.path.join(REPO_ROOT, "app_data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "cervigrade.db")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{DB_PATH}"

ROLES = ("technician", "clinician", "admin")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _turn_on_foreign_keys(dbapi_connection, _record):
    """SQLite ignores foreign keys unless asked, and the cascades (deleting a slide removes its images) depend on them."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_session():
    """FastAPI dependency: one session per request. Its changes are committed by the code that makes them."""
    with Session(engine, expire_on_commit=False) as session:
        yield session


def init_db():
    """Create any table that does not exist yet. Existing tables and their rows are left alone."""
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode = WAL"))
    SQLModel.metadata.create_all(engine)
    have = {c["name"] for c in inspect(engine).get_columns("predictions")}
    with engine.begin() as conn:
        for col in ("mode", "detections"):          # databases made before the detector was added
            if col not in have:
                conn.execute(text(f"ALTER TABLE predictions ADD COLUMN {col} TEXT"))


def adopt_institution_emails():
    """
    Accounts made before the email rule have plain usernames ('admin', 'tech1'). Without a fix nobody could sign in,
    the administrator included, so each one gets the institution domain added to its name ('admin' -> 'admin@alustudent.com').
    Names that are already allowed are left alone, and so is any name whose new form is already taken.
    """
    if institution.OPEN_TO_ANY:
        return
    domain = institution.DOMAINS[0]
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        taken = {u.username for u in users}
        for user in users:
            name = user.username
            if institution.is_institutional(name):
                continue
            new = f"{name}@{domain}"
            if "@" in name or new in taken or not institution.is_institutional(new):
                print(f"[accounts] '{name}' cannot sign in: it is not an {institution.describe_domains()} address. Rename it or add a new account.")
                continue
            user.username = new
            taken.add(new)
            print(f"[accounts] '{name}' is now '{new}' (accounts must use an {institution.describe_domains()} address).")
        session.commit()


def bootstrap_admin():
    """On the very first start there are no users, so create one admin and say so in the terminal."""
    from repositories.users import UserRepository
    with Session(engine) as session:
        if session.exec(select(func.count()).select_from(User)).one() > 0:
            return
        password = os.environ.get("CERVIGRADE_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        email = institution.default_admin_email()
        UserRepository(session).create(email, "Administrator", "admin", password)
        shown = "(the one you set in CERVIGRADE_ADMIN_PASSWORD)" if os.environ.get("CERVIGRADE_ADMIN_PASSWORD") else password
        print("\n" + "=" * 62)
        print(" First start: an admin account was created.")
        print(f"   email:    {email}")
        print(f"   password: {shown}")
        print(" Sign in, then add your technicians and clinicians under Users.")
        print("=" * 62 + "\n")


def uploads_for(slide_id: int) -> str:
    return os.path.join(UPLOAD_DIR, str(slide_id))
