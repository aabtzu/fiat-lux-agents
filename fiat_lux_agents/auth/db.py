"""Auth DB helpers - create/verify users, change passwords.

Designed to work with any connection factory that returns a context manager
yielding a DBAPI2 connection. Caller passes ``get_connection`` and
``use_postgres`` so the plugin stays decoupled from the app's DB layer.

``login_field`` selects which column is used as the login credential:
  - "username" (default): classic username + email registration
  - "email": email-only registration (no username column required)

``has_display_name`` adds optional display_name support for apps whose users
table has a display_name column.
"""

from __future__ import annotations

from typing import Any, Callable

import bcrypt

# --- SQL constants ---

_SQL_PG_INSERT_USER = (
    "INSERT INTO users (username, email, password_hash)"
    " VALUES (%s, %s, %s) RETURNING id"
)
_SQL_SQ_INSERT_USER = (
    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)"
)

_SQL_PG_INSERT_USER_DN = (
    "INSERT INTO users (username, email, password_hash, display_name)"
    " VALUES (%s, %s, %s, %s) RETURNING id"
)
_SQL_SQ_INSERT_USER_DN = (
    "INSERT INTO users (username, email, password_hash, display_name) VALUES (?, ?, ?, ?)"
)

# Email-only insert (no username column)
_SQL_PG_INSERT_EMAIL_USER = (
    "INSERT INTO users (email, password_hash) VALUES (%s, %s) RETURNING id"
)
_SQL_SQ_INSERT_EMAIL_USER = (
    "INSERT INTO users (email, password_hash) VALUES (?, ?)"
)

_SQL_PG_INSERT_EMAIL_USER_DN = (
    "INSERT INTO users (email, password_hash, display_name) VALUES (%s, %s, %s) RETURNING id"
)
_SQL_SQ_INSERT_EMAIL_USER_DN = (
    "INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)"
)

_SQL_PG_GET_BY_USERNAME = (
    "SELECT id, username, email, password_hash FROM users WHERE username = %s"
)
_SQL_SQ_GET_BY_USERNAME = (
    "SELECT id, username, email, password_hash FROM users WHERE username = ?"
)

_SQL_PG_GET_BY_EMAIL = (
    "SELECT id, email, password_hash FROM users WHERE email = %s"
)
_SQL_SQ_GET_BY_EMAIL = (
    "SELECT id, email, password_hash FROM users WHERE email = ?"
)

_SQL_PG_GET_BY_EMAIL_DN = (
    "SELECT id, email, password_hash, display_name FROM users WHERE email = %s"
)
_SQL_SQ_GET_BY_EMAIL_DN = (
    "SELECT id, email, password_hash, display_name FROM users WHERE email = ?"
)

_SQL_PG_USERNAME_EXISTS = "SELECT 1 FROM users WHERE username = %s"
_SQL_SQ_USERNAME_EXISTS = "SELECT 1 FROM users WHERE username = ?"

_SQL_PG_EMAIL_EXISTS = "SELECT 1 FROM users WHERE email = %s"
_SQL_SQ_EMAIL_EXISTS = "SELECT 1 FROM users WHERE email = ?"

_SQL_PG_SET_PASSWORD = "UPDATE users SET password_hash = %s WHERE id = %s"
_SQL_SQ_SET_PASSWORD = "UPDATE users SET password_hash = ? WHERE id = ?"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def _row_to_user(row, use_postgres: bool) -> dict[str, Any]:
    if use_postgres:
        return dict(zip([d[0] for d in row.description], row)) if hasattr(row, 'description') else {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "password_hash": row[3],
        }
    return dict(row)


class AuthDB:
    """Thin wrapper that binds a connection factory to the SQL helpers.

    Args:
        get_connection:  Callable returning a context manager for a DB connection.
        use_postgres:    True if the DB uses %s placeholders (Postgres), False for ? (SQLite).
        login_field:     Column used as login credential — "username" (default) or "email".
        has_display_name: True if the users table has a display_name column.
    """

    def __init__(
        self,
        get_connection: Callable,
        use_postgres: bool = False,
        login_field: str = "username",
        has_display_name: bool = False,
    ):
        self._get = get_connection
        self._pg = use_postgres
        self.login_field = login_field
        self.has_display_name = has_display_name

    def _p(self, pg_sql: str, sq_sql: str) -> str:
        return pg_sql if self._pg else sq_sql

    def create_user(
        self,
        email: str,
        password: str,
        username: str = "",
        display_name: str = "",
    ) -> int | str | None:
        """Create a user. Returns the new user's id, or None on failure.

        When login_field="username", username is required.
        When login_field="email", username is ignored.
        display_name is stored only when has_display_name=True.
        """
        password_hash = hash_password(password)
        with self._get() as conn:
            cur = conn.cursor()
            try:
                if self.login_field == "email":
                    if self.has_display_name:
                        sql_pg, sql_sq = _SQL_PG_INSERT_EMAIL_USER_DN, _SQL_SQ_INSERT_EMAIL_USER_DN
                        params = (email, password_hash, display_name)
                    else:
                        sql_pg, sql_sq = _SQL_PG_INSERT_EMAIL_USER, _SQL_SQ_INSERT_EMAIL_USER
                        params = (email, password_hash)
                else:
                    if self.has_display_name:
                        sql_pg, sql_sq = _SQL_PG_INSERT_USER_DN, _SQL_SQ_INSERT_USER_DN
                        params = (username, email, password_hash, display_name)
                    else:
                        sql_pg, sql_sq = _SQL_PG_INSERT_USER, _SQL_SQ_INSERT_USER
                        params = (username, email, password_hash)

                if self._pg:
                    cur.execute(sql_pg, params)
                    return cur.fetchone()[0]
                else:
                    cur.execute(sql_sq, params)
                    return cur.lastrowid
            except Exception as e:
                print(f"[fla-auth] create_user failed: {e}")
                return None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        with self._get() as conn:
            cur = conn.cursor()
            cur.execute(
                self._p(_SQL_PG_GET_BY_USERNAME, _SQL_SQ_GET_BY_USERNAME),
                (username,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        sq = _SQL_SQ_GET_BY_EMAIL_DN if self.has_display_name else _SQL_SQ_GET_BY_EMAIL
        pg = _SQL_PG_GET_BY_EMAIL_DN if self.has_display_name else _SQL_PG_GET_BY_EMAIL
        with self._get() as conn:
            cur = conn.cursor()
            cur.execute(self._p(pg, sq), (email,))
            row = cur.fetchone()
            return dict(row) if row else None

    def username_exists(self, username: str) -> bool:
        with self._get() as conn:
            cur = conn.cursor()
            cur.execute(
                self._p(_SQL_PG_USERNAME_EXISTS, _SQL_SQ_USERNAME_EXISTS),
                (username,),
            )
            return cur.fetchone() is not None

    def email_exists(self, email: str) -> bool:
        with self._get() as conn:
            cur = conn.cursor()
            cur.execute(
                self._p(_SQL_PG_EMAIL_EXISTS, _SQL_SQ_EMAIL_EXISTS),
                (email,),
            )
            return cur.fetchone() is not None

    def authenticate(self, credential: str, password: str) -> dict[str, Any] | None:
        """Authenticate using the configured login_field (username or email).

        Returns a user dict without password_hash on success, or None.
        """
        if self.login_field == "email":
            user = self.get_user_by_email(credential)
        else:
            user = self.get_user_by_username(credential)
        if user and verify_password(password, user["password_hash"]):
            user = dict(user)
            del user["password_hash"]
            return user
        return None

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> tuple[bool, str | None]:
        """Verify current password then set new one. Returns (ok, error)."""
        with self._get() as conn:
            cur = conn.cursor()
            if self._pg:
                cur.execute(
                    "SELECT password_hash FROM users WHERE id = %s", (user_id,)
                )
            else:
                cur.execute(
                    "SELECT password_hash FROM users WHERE id = ?", (user_id,)
                )
            row = cur.fetchone()
            if not row:
                return False, "User not found"
            stored_hash = row[0] if self._pg else row["password_hash"]
            if not verify_password(current_password, stored_hash):
                return False, "Current password is incorrect"
            new_hash = hash_password(new_password)
            cur.execute(
                self._p(_SQL_PG_SET_PASSWORD, _SQL_SQ_SET_PASSWORD),
                (new_hash, user_id),
            )
            return True, None

    def set_password_by_id(self, user_id: int, new_password: str) -> bool:
        """Set password directly by user ID - used after token verification."""
        new_hash = hash_password(new_password)
        with self._get() as conn:
            cur = conn.cursor()
            cur.execute(
                self._p(_SQL_PG_SET_PASSWORD, _SQL_SQ_SET_PASSWORD),
                (new_hash, user_id),
            )
            return cur.rowcount > 0
