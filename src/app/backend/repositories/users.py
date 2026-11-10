"""
Reading and writing the users table, in one place.

The endpoints ask a UserRepository for what they need instead of writing queries themselves,
so the table's columns and the rules for keeping it consistent live here only.
"""

from sqlalchemy import func
from sqlmodel import select

from core.security import hash_password
from db import database as db
from models import FeedbackEntry, Slide, User


class UserRepository:
    """All the database work for accounts. One instance wraps one open session (one request)."""

    def __init__(self, session):
        self._s = session

    # ---- reading
    def by_id(self, user_id):
        return self._s.get(User, user_id)

    def by_username(self, username):
        return self._s.exec(select(User).where(User.username == username)).first()

    def count_active_admins(self):
        return self._s.exec(select(func.count()).select_from(User).where(User.role == "admin", User.active == True)).one()  # noqa: E712

    def usage_count(self, user_id):
        """How many slides this user uploaded plus grades they reviewed. Records depend on those, so such users cannot be deleted."""
        slides = self._s.exec(select(func.count()).select_from(Slide).where(Slide.uploaded_by == user_id)).one()
        reviews = self._s.exec(select(func.count()).select_from(FeedbackEntry).where(FeedbackEntry.clinician_id == user_id)).one()
        return slides + reviews

    def list_with_activity(self):
        """Every user with how many slides they uploaded and grades they reviewed: a list of (user, slides_uploaded, reviews_made)."""
        slides = select(func.count()).select_from(Slide).where(Slide.uploaded_by == User.id).correlate(User).scalar_subquery()
        reviews = select(func.count()).select_from(FeedbackEntry).where(FeedbackEntry.clinician_id == User.id).correlate(User).scalar_subquery()
        stmt = select(User, slides, reviews).order_by(User.active.desc(), User.role, User.username)
        return self._s.exec(stmt).all()

    # ---- writing
    def create(self, username, full_name, role, password):
        """Add an account and return its id. Raises sqlalchemy.exc.IntegrityError (after rolling back) when the username is taken."""
        user = User(username=username, full_name=full_name, role=role, password_hash=hash_password(password), active=True, created_at=db.now())
        self._s.add(user)
        self._commit()
        return user.id

    def record_login(self, user_id):
        self._s.get(User, user_id).last_login = db.now()
        self._commit()

    def set_password(self, user_id, new_password):
        self._s.get(User, user_id).password_hash = hash_password(new_password)
        self._commit()

    def update(self, user_id, full_name=None, role=None, active=None, password=None):
        """Change only the fields that are given."""
        user = self._s.get(User, user_id)
        if full_name is not None:
            user.full_name = full_name.strip()
        if role is not None:
            user.role = role
        if active is not None:
            user.active = bool(active)
        if password is not None:
            user.password_hash = hash_password(password)
        self._commit()

    def delete(self, user_id):
        """Remove an account. Raises sqlalchemy.exc.IntegrityError (after rolling back) when other records still point at it."""
        self._s.delete(self._s.get(User, user_id))
        self._commit()

    def _commit(self):
        try:
            self._s.commit()
        except Exception:
            self._s.rollback()
            raise
