"""Sign in, who am I, and change my password."""

import time

from fastapi import APIRouter, Depends, HTTPException

from core import institution
from core.security import verify_password
from dependencies import current_user, get_users, tokens
from schemas.auth import LoginIn, PasswordIn
from schemas.users import public_user

router = APIRouter()

_failures = {}      # username -> times of recent wrong passwords
MAX_FAILURES, WINDOW_SECONDS = 5, 300


def _throttled(username):
    recent = [t for t in _failures.get(username, []) if time.time() - t < WINDOW_SECONDS]
    _failures[username] = recent
    return len(recent) >= MAX_FAILURES


@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn, users=Depends(get_users)):
    username = institution.normalise(body.username)
    if not institution.is_institutional(username):
        raise HTTPException(403, institution.rejection_message())
    if _throttled(username):
        raise HTTPException(429, "Too many wrong passwords. Wait a few minutes and try again.")
    row = users.by_username(username)
    if row is None or not row.active or not verify_password(body.password, row.password_hash):
        _failures.setdefault(username, []).append(time.time())
        raise HTTPException(401, "Wrong email or password.")
    _failures.pop(username, None)
    users.record_login(row.id)
    return {"token": tokens.make(row.id), "user": public_user(row)}


@router.get("/auth/me", tags=["auth"])
def me(user=Depends(current_user)):
    return public_user(user)


@router.post("/auth/change-password", tags=["auth"])
def change_password(body: PasswordIn, user=Depends(current_user), users=Depends(get_users)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "The current password is not right.")
    users.set_password(user.id, body.new_password)
    return {"ok": True}
