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


def forgot_password(
    db: AuthDB,
    email: str,
    secret_key: str,
    app_url: str,
    from_email: str,
    app_name: str = "Libertas",
) -> tuple[bool, str | None]:
    """Look up user by email, send reset link. Returns (sent, error).

    Always returns (True, None) even if email not found - avoids leaking
    whether an address is registered.
    """
    from .tokens import generate_reset_token
    from . import email as mailer

    email = email.strip().lower()
    user = db.get_user_by_email(email)
    if not user:
        return True, None  # silent - don't reveal if email exists

    token = generate_reset_token(user["id"], secret_key)
    reset_url = f"{app_url.rstrip('/')}/reset-password.html?token={token}"

    body = f"""
<p>Hi {user['username']},</p>
<p>Someone requested a password reset for your {app_name} account.</p>
<p><a href="{reset_url}" style="background:#667eea;color:white;padding:12px 24px;
border-radius:8px;text-decoration:none;font-weight:600;">Reset Password</a></p>
<p>This link expires in 1 hour. If you didn't request this, ignore this email.</p>
<p>{app_name}</p>
"""
    try:
        mailer.send(email, f"Reset your {app_name} password", body, from_email)
    except Exception as e:
        print(f"[fla-auth] email send failed: {e}")
        return False, "Failed to send reset email - please try again later"

    return True, None


def reset_password(
    db: AuthDB,
    token: str,
    new_password: str,
    confirm_password: str,
    secret_key: str,
) -> tuple[bool, str | None]:
    """Verify token and set new password. Returns (success, error)."""
    from .tokens import verify_reset_token

    if not new_password or not confirm_password:
        return False, "All fields are required"
    if new_password != confirm_password:
        return False, "Passwords do not match"
    if len(new_password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters"

    user_id = verify_reset_token(token, secret_key)
    if not user_id:
        return False, "Reset link is invalid or has expired"

    ok = db.set_password_by_id(user_id, new_password)
    if not ok:
        return False, "Failed to reset password"
    return True, None


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
