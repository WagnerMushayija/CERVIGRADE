"""Passwords, login tokens and the users table."""

import importlib
import sqlite3
import sys
import tempfile

import pytest

from security import PasswordHasher, TokenService


def test_a_password_checks_out_against_its_own_hash_only():
    h = PasswordHasher(iterations=1000)
    stored = h.hash("correct horse")
    assert h.verify("correct horse", stored)
    assert not h.verify("wrong horse", stored)
    assert "correct horse" not in stored


def test_the_same_password_gets_a_different_hash_each_time():
    h = PasswordHasher(iterations=1000)
    assert h.hash("same") != h.hash("same")


def test_garbage_in_the_database_does_not_crash_a_login():
    assert not PasswordHasher().verify("x", "not-a-hash")


def test_a_token_gives_back_its_user():
    t = TokenService("k" * 40)
    assert t.read(t.make(42)) == 42


def test_tokens_from_another_key_or_tampered_or_expired_are_refused():
    t = TokenService("k" * 40)
    good = t.make(7)
    assert TokenService("o" * 40).read(good) is None
    assert t.read(good[:-3] + "abc") is None
    assert TokenService("k" * 40, hours=-1).read(TokenService("k" * 40, hours=-1).make(7)) is None
    assert t.read("garbage") is None


@pytest.fixture
def repo(monkeypatch):
    monkeypatch.setenv("CERVIGRADE_DATA", tempfile.mkdtemp())
    for name in ("db", "users"):
        sys.modules.pop(name, None)
    db = importlib.import_module("db")
    users = importlib.import_module("users")
    db.init_db()
    conn = db.connect()
    yield users.UserRepository(conn)
    conn.close()


def test_create_find_and_reject_a_duplicate(repo):
    uid = repo.create("a@alustudent.com", "Ada", "technician", "password-1")
    assert repo.by_id(uid)["full_name"] == "Ada"
    assert repo.by_username("a@alustudent.com")["id"] == uid
    with pytest.raises(sqlite3.IntegrityError):
        repo.create("a@alustudent.com", "Ada again", "technician", "password-1")


def test_update_changes_only_the_given_fields(repo):
    uid = repo.create("b@alustudent.com", "Bo", "technician", "password-1")
    old_hash = repo.by_id(uid)["password_hash"]
    repo.update(uid, full_name="  Bola  ", role="clinician")
    row = repo.by_id(uid)
    assert (row["full_name"], row["role"], row["active"], row["password_hash"]) == ("Bola", "clinician", 1, old_hash)
    repo.update(uid, active=False, password="new-password-1")
    row = repo.by_id(uid)
    assert row["active"] == 0 and row["password_hash"] != old_hash


def test_the_last_active_admin_is_counted_correctly(repo):
    a = repo.create("root@alustudent.com", "Root", "admin", "password-1")
    repo.create("t@alustudent.com", "Tee", "technician", "password-1")
    assert repo.count_active_admins() == 1
    repo.update(a, active=False)
    assert repo.count_active_admins() == 0


def test_login_time_and_password_are_recorded(repo):
    uid = repo.create("c@alustudent.com", "Cy", "clinician", "password-1")
    assert repo.by_id(uid)["last_login"] is None
    repo.record_login(uid)
    assert repo.by_id(uid)["last_login"]
    repo.set_password(uid, "another-password")
    assert repo.by_id(uid)["password_hash"].startswith("pbkdf2_sha256$")


def test_a_user_with_no_records_can_be_deleted(repo):
    uid = repo.create("d@alustudent.com", "Di", "technician", "password-1")
    assert repo.usage_count(uid) == 0
    repo.delete(uid)
    assert repo.by_id(uid) is None
