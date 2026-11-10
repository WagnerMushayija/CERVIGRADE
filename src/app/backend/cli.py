"""
Admin commands that work without signing in, for when you are locked out or want demo data.

    python cli.py list-users
    python cli.py create-user <email> "<Full name>" <technician|clinician|admin> <password>
    python cli.py reset-password <email> <new password>
    python cli.py seed-demo        # one technician, one clinician and a few patient codes, for trying the page

Run it from this folder, with the same CERVIGRADE_DATA as the server if you set one.
"""

import sys

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from core import institution
from core.security import hash_password
from db import database as db
from models import User
from repositories.users import UserRepository

USAGE = __doc__


def main(argv):
    db.init_db()
    cmd = argv[1] if len(argv) > 1 else ""
    with Session(db.engine) as session:
        users = UserRepository(session)
        if cmd == "list-users":
            for u in session.exec(select(User).order_by(User.role, User.username)).all():
                print(f"{u.username:<30}{u.role:<12}{'active' if u.active else 'inactive':<10}{u.full_name}  (last sign-in: {u.last_login or 'never'})")
        elif cmd == "create-user" and len(argv) == 6:
            _, _, username, full_name, role, password = argv
            if not institution.is_institutional(username):
                sys.exit(institution.rejection_message())
            if role not in db.ROLES:
                sys.exit(f"Role must be one of: {', '.join(db.ROLES)}")
            if len(password) < 8:
                sys.exit("The password needs at least 8 characters.")
            try:
                users.create(institution.normalise(username), full_name, role, password)
            except IntegrityError:
                sys.exit(f"An account for {institution.normalise(username)} already exists.")
            print(f"Created {role} '{institution.normalise(username)}'.")
        elif cmd == "reset-password" and len(argv) == 4:
            if len(argv[3]) < 8:
                sys.exit("The password needs at least 8 characters.")
            user = users.by_username(institution.normalise(argv[2]))
            if user is None:
                print("No such user.")
            else:
                user.password_hash, user.active = hash_password(argv[3]), True
                session.commit()
                print("Password changed.")
        elif cmd == "seed-demo":
            domain = "alustudent.com" if institution.OPEN_TO_ANY else institution.DOMAINS[0]
            for username, name, role in [(f"tech.demo@{domain}", "Demo Technician", "technician"), (f"clin.demo@{domain}", "Demo Clinician", "clinician")]:
                try:
                    users.create(username, name, role, "demo-password-1")
                    print(f"Created {role} '{username}' with password demo-password-1 (change it or deactivate the account after trying the page).")
                except IntegrityError:
                    print(f"'{username}' already exists.")
        else:
            print(USAGE)


if __name__ == "__main__":
    main(sys.argv)
