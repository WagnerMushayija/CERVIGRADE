"""
Admin commands that work without signing in, for when you are locked out or want demo data.

    python manage.py list-users
    python manage.py create-user <email> "<Full name>" <technician|clinician|admin> <password>
    python manage.py reset-password <email> <new password>
    python manage.py seed-demo        # one technician, one clinician and a few patient codes, for trying the page

Run it from this folder, with the same CERVIGRADE_DATA as the server if you set one.
"""

import sqlite3
import sys

import db
import institution
from security import hash_password

USAGE = __doc__


def main(argv):
    db.init_db()
    conn = db.connect()
    cmd = argv[1] if len(argv) > 1 else ""
    try:
        if cmd == "list-users":
            for r in conn.execute("SELECT username, full_name, role, active, last_login FROM users ORDER BY role, username"):
                print(f"{r['username']:<18}{r['role']:<12}{'active' if r['active'] else 'inactive':<10}{r['full_name']}  (last sign-in: {r['last_login'] or 'never'})")
        elif cmd == "create-user" and len(argv) == 6:
            _, _, username, full_name, role, password = argv
            if not institution.is_institutional(username):
                sys.exit(institution.rejection_message())
            if role not in db.ROLES:
                sys.exit(f"Role must be one of: {', '.join(db.ROLES)}")
            if len(password) < 8:
                sys.exit("The password needs at least 8 characters.")
            db.create_user(conn, institution.normalise(username), full_name, role, password)
            print(f"Created {role} '{institution.normalise(username)}'.")
        elif cmd == "reset-password" and len(argv) == 4:
            if len(argv[3]) < 8:
                sys.exit("The password needs at least 8 characters.")
            cur = conn.execute("UPDATE users SET password_hash = ?, active = 1 WHERE username = ?", (hash_password(argv[3]), institution.normalise(argv[2])))
            conn.commit()
            print("Password changed." if cur.rowcount else "No such user.")
        elif cmd == "seed-demo":
            domain = "alustudent.com" if institution.OPEN_TO_ANY else institution.DOMAINS[0]
            for username, name, role in [(f"tech.demo@{domain}", "Demo Technician", "technician"), (f"clin.demo@{domain}", "Demo Clinician", "clinician")]:
                try:
                    db.create_user(conn, username, name, role, "demo-password-1")
                    print(f"Created {role} '{username}' with password demo-password-1 (change it or deactivate the account after trying the page).")
                except sqlite3.IntegrityError:
                    print(f"'{username}' already exists.")
        else:
            print(USAGE)
    finally:
        conn.close()


if __name__ == "__main__":
    main(sys.argv)
