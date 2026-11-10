"""
Tests for the institution email rule. Run from the backend folder:  python -m pytest tests -q
They need no model weights: only core/institution.py and the SQLite helpers are loaded.
"""

import importlib
import os
import sys
import tempfile

import pytest
from sqlmodel import Session, select

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from models import User      # noqa: E402  (the users table; only its definition is needed here)


def load(domains="alustudent.com", data_dir=None):
    """Import institution.py and db.py fresh, with the settings a test wants."""
    os.environ["CERVIGRADE_EMAIL_DOMAINS"] = domains
    os.environ["CERVIGRADE_DATA"] = data_dir or tempfile.mkdtemp()
    for name in ("core.institution", "db.database"):
        sys.modules.pop(name, None)
    return importlib.import_module("core.institution"), importlib.import_module("db.database")


@pytest.mark.parametrize("email", ["w.mushayija@alustudent.com", "A.B@AluStudent.com", "  x1@alustudent.com  "])
def test_institution_addresses_are_accepted(email):
    inst, _ = load()
    assert inst.is_institutional(email)


@pytest.mark.parametrize("email", [
    "someone@gmail.com", "admin", "", None, "name@alustudent.com.evil.org", "name@evilalustudent.com",
    "name@sub.alustudent.com", "@alustudent.com", "name@alustudent", "a b@alustudent.com", "name@@alustudent.com"])
def test_everything_else_is_refused(email):
    inst, _ = load()
    assert not inst.is_institutional(email)


def test_several_domains_and_the_off_switch():
    inst, _ = load("alustudent.com, @alueducation.com")
    assert inst.is_institutional("staff@alueducation.com") and not inst.is_institutional("x@gmail.com")
    inst, _ = load("*")
    assert inst.is_institutional("x@gmail.com") and not inst.is_institutional("not-an-email")


def test_old_plain_usernames_are_moved_to_the_institution_domain():
    data = tempfile.mkdtemp()
    inst, db = load("*", data)                 # an old database: made while the rule was off
    db.init_db()
    with Session(db.engine) as session:
        for name, full_name, role in [("admin", "Administrator", "admin"), ("tech1", "Tech One", "technician"), ("other@gmail.com", "Outsider", "clinician")]:
            session.add(User(username=name, full_name=full_name, role=role, password_hash="x", created_at=db.now()))
        session.commit()
    inst, db = load("alustudent.com", data)    # the server restarts with the rule on
    db.adopt_institution_emails()
    with Session(db.engine) as session:
        names = sorted(session.exec(select(User.username)).all())
    assert names == ["admin@alustudent.com", "other@gmail.com", "tech1@alustudent.com"]
    assert not inst.is_institutional("other@gmail.com")   # still cannot sign in


def test_first_admin_gets_an_institution_address():
    inst, db = load()
    db.init_db()
    db.bootstrap_admin()
    with Session(db.engine) as session:
        name = session.exec(select(User.username)).first()
    assert name == "admin@alustudent.com" and inst.is_institutional(name)


def test_policy_class_works_without_touching_the_environment():
    inst, _ = load()
    policy = inst.InstitutionPolicy(["@alustudent.com", " AluEducation.com "])
    assert policy.domains == ("alustudent.com", "alueducation.com")
    assert policy.is_institutional("x@alueducation.com") and not policy.is_institutional("x@gmail.com")
    assert policy.describe() == "@alustudent.com or @alueducation.com"
    assert "Only @alustudent.com or @alueducation.com accounts" in policy.rejection_message()
    assert policy.default_admin_email() == "admin@alustudent.com"
