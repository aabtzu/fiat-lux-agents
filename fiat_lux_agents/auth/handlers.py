"""Auth business logic - registration, login, change-password."""

from __future__ import annotations

from .db import AuthDB

MIN_USERNAME_LEN = 3
MIN_PASSWORD_LEN = 6


def register(
    db: AuthDB,
    username: str,
    email: str,
    password: str,
    invite_code: str = "",
    required_invite_code: str = "",
) -> tuple[bool, str | None]:
    """Validate and create a new user. Returns (success, error_message)."""
    username = username.strip()
    email = email.strip()
    password = password.strip()

    if len(username) < MIN_USERNAME_LEN:
        return False, f"Username must be at least {MIN_USERNAME_LEN} characters"
    if not email or "@" not in email:
        return False, "Invalid email address"
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters"

    if required_invite_code:
        if not invite_code:
            return False, "An invite code is required to register"
        if invite_code != required_invite_code:
            return False, "Invalid invite code"

    if db.username_exists(username):
        return False, "Username already taken"
    if db.email_exists(email):
        return False, "Email already registered"

    user_id = db.create_user(username, email, password)
    if user_id:
        return True, None
    return False, "Failed to create user"


def login(
    db: AuthDB, username: str, password: str
) -> tuple[dict | None, str | None]:
    """Authenticate. Returns (user_dict, None) or (None, error_message)."""
    username = username.strip()
    password = password.strip()
    if not username or not password:
        return None, "Username and password required"
    user = db.authenticate(username, password)
    if not user:
        return None, "Invalid username or password"
    return user, None


def change_password(
    db: AuthDB,
    user_id: int,
    current_password: str,
    new_password: str,
    confirm_password: str,
) -> tuple[bool, str | None]:
    """Validate and change a user's password. Returns (success, error)."""
    if not current_password or not new_password or not confirm_password:
        return False, "All fields are required"
    if new_password != confirm_password:
        return False, "New passwords do not match"
    if len(new_password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters"
    return db.change_password(user_id, current_password, new_password)
