"""
Things the routers share: who is signed in, what role they need, and one user repository per request.
"""

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core import institution
from core.security import TokenService, load_secret
from db import database as db
from repositories.users import UserRepository

tokens = TokenService(load_secret(db.DATA_DIR))
bearer = HTTPBearer(auto_error=False)


def get_users(session=Depends(db.get_session)):
    """One UserRepository per request, on the same session as everything else in that request."""
    return UserRepository(session)


def current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer), users=Depends(get_users)):
    if creds is None:
        raise HTTPException(401, "Please sign in.")
    uid = tokens.read(creds.credentials)
    row = users.by_id(uid) if uid else None
    if row is None or not row.active:
        raise HTTPException(401, "Your session has ended. Please sign in again.")
    if not institution.is_institutional(row.username):
        raise HTTPException(403, institution.rejection_message())
    return row


def require(*roles):
    def dep(user=Depends(current_user)):
        if user.role not in roles:
            raise HTTPException(403, "Your role cannot do this.")
        return user
    return dep


def can_see(user, uploaded_by):
    """Technicians see only their own slides. Clinicians and admins see all of them. uploaded_by is the slide's uploader id."""
    return user.role != "technician" or uploaded_by == user.id
