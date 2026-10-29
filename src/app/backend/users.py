"""
Reading and writing the users table, in one place.

The endpoints in main.py ask a UserRepository for what they need instead of writing SQL themselves,
so the table's columns and the rules for keeping it consistent live here only.
"""

import db
from security import hash_password


class UserRepository:
    """All the database work for accounts. One instance wraps one open connection (one request)."""

    def __init__(self, conn):
        self._conn = conn

    # ---- reading
    def by_id(self, user_id):
        return self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def by_username(self, username):
        return self._conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    def count_active_admins(self):
        return self._conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND active = 1").fetchone()[0]

    def usage_count(self, user_id):
        """How many slides this user uploaded plus grades they reviewed. Records depend on those, so such users cannot be deleted."""
        return self._conn.execute(
            "SELECT (SELECT COUNT(*) FROM slides WHERE uploaded_by = ?) + (SELECT COUNT(*) FROM feedback_entries WHERE clinician_id = ?)",
            (user_id, user_id)).fetchone()[0]

    def list_with_activity(self):
        return self._conn.execute("""
            SELECT u.*, (SELECT COUNT(*) FROM slides s WHERE s.uploaded_by = u.id) AS slides_uploaded,
                        (SELECT COUNT(*) FROM feedback_entries f WHERE f.clinician_id = u.id) AS reviews_made
            FROM users u ORDER BY u.active DESC, u.role, u.username""").fetchall()

    # ---- writing
    def create(self, username, full_name, role, password):
        """Add an account and return its id. Raises sqlite3.IntegrityError when the username is taken."""
        return db.create_user(self._conn, username, full_name, role, password)

    def record_login(self, user_id):
        self._conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (db.now(), user_id))
        self._conn.commit()

    def set_password(self, user_id, new_password):
        self._conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_password), user_id))
        self._conn.commit()

    def update(self, user_id, full_name=None, role=None, active=None, password=None):
        """Change only the fields that are given."""
        fields, values = [], []
        if full_name is not None:
            fields.append("full_name = ?"); values.append(full_name.strip())
        if role is not None:
            fields.append("role = ?"); values.append(role)
        if active is not None:
            fields.append("active = ?"); values.append(int(active))
        if password is not None:
            fields.append("password_hash = ?"); values.append(hash_password(password))
        if fields:
            self._conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", (*values, user_id))
            self._conn.commit()

    def delete(self, user_id):
        """Remove an account. Raises sqlite3.IntegrityError (after rolling back) when other records still point at it."""
        try:
            self._conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
