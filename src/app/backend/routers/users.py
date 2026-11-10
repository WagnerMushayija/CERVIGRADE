"""User management, for administrators."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError

from core import institution
from dependencies import get_users, require
from schemas.users import UserIn, UserPatch, public_user

router = APIRouter()


@router.get("/users", tags=["users"])
def list_users(admin=Depends(require("admin")), users=Depends(get_users)):
    return [{**public_user(user), "slides_uploaded": slides, "reviews_made": reviews} for user, slides, reviews in users.list_with_activity()]


@router.post("/users", status_code=201, tags=["users"])
def add_user(body: UserIn, admin=Depends(require("admin")), users=Depends(get_users)):
    username = institution.normalise(body.username)
    if not institution.is_institutional(username):
        raise HTTPException(422, institution.rejection_message())
    try:
        uid = users.create(username, body.full_name.strip(), body.role, body.password)
    except IntegrityError:
        raise HTTPException(409, f"An account for {username} already exists.")
    return public_user(users.by_id(uid))


@router.patch("/users/{user_id}", tags=["users"])
def edit_user(user_id: int, body: UserPatch, admin=Depends(require("admin")), users=Depends(get_users)):
    row = users.by_id(user_id)
    if row is None:
        raise HTTPException(404, "No such user.")
    losing_admin = row.role == "admin" and row.active and (body.role not in (None, "admin") or body.active is False)
    if losing_admin and users.count_active_admins() <= 1:
        raise HTTPException(409, "This is the last active admin. Make another admin first.")
    if user_id == admin.id and body.active is False:
        raise HTTPException(409, "You cannot deactivate your own account.")
    users.update(user_id, full_name=body.full_name, role=body.role, active=body.active, password=body.password)
    return public_user(users.by_id(user_id))


@router.delete("/users/{user_id}", status_code=204, tags=["users"])
def remove_user(user_id: int, admin=Depends(require("admin")), users=Depends(get_users)):
    row = users.by_id(user_id)
    if row is None:
        raise HTTPException(404, "No such user.")
    if user_id == admin.id:
        raise HTTPException(409, "You cannot delete your own account.")
    if row.role == "admin" and row.active and users.count_active_admins() <= 1:
        raise HTTPException(409, "This is the last active admin.")
    if users.usage_count(user_id):
        raise HTTPException(409, "This user has uploaded slides or reviewed grades, so the records need them. Deactivate the account instead.")
    try:
        users.delete(user_id)
    except IntegrityError:
        raise HTTPException(409, "This user is still referenced by other records. Deactivate the account instead.")
