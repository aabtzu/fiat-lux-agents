"""Flask blueprint factory for fla-auth.

Username-based usage (libertas / default):
    auth_bp = make_auth_blueprint(
        get_connection=get_db,
        use_postgres=USE_POSTGRES,
        invite_code=os.environ.get("INVITE_CODE", ""),
        secret_key=os.environ["SECRET_KEY"],
        app_url="https://libertas-travel.onrender.com",
        from_email="noreply@libertas-travel.onrender.com",
    )

Email-based usage (fiat-lux style):
    auth_bp = make_auth_blueprint(
        get_connection=db,
        login_field="email",
        has_display_name=True,
        secret_key=os.environ["SECRET_KEY"],
        app_url="https://fiat-lux.onrender.com",
        from_email="noreply@fiat-lux.onrender.com",
        app_name="Fiat Lux",
    )
"""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from typing import Callable

from flask import Blueprint, jsonify, redirect, request, session

from .db import AuthDB
from . import handlers


def make_auth_blueprint(
    get_connection: Callable,
    use_postgres: bool = False,
    login_field: str = "username",
    has_display_name: bool = False,
    invite_code: str = "",
    secret_key: str = "",
    app_url: str = "",
    from_email: str = "",
    app_name: str = "Libertas",
    url_prefix: str = "/api",
    blueprint_name: str = "fla_auth",
    google_client_id: str = "",
    google_client_secret: str = "",
    admin_email: str = "",
) -> Blueprint:
    """Return a configured auth blueprint.

    Args:
        get_connection:  callable returning a context manager for a DB connection
        use_postgres:    True if the DB uses %s placeholders (Postgres), False for ? (SQLite)
        login_field:     "username" (default) or "email" — which field is used to log in
        has_display_name: True if the users table has a display_name column
        invite_code:     if set, required on registration
        secret_key:      HMAC key for reset tokens (use app SECRET_KEY)
        app_url:         base URL for reset links
        from_email:      sender address for reset emails
        app_name:        app name shown in emails
        url_prefix:      prefix for all routes (default /api)
        blueprint_name:  Flask blueprint name (change if registering multiple times)
        admin_email:     if set, receive an email notification on every new signup
    """
    db = AuthDB(get_connection, use_postgres, login_field=login_field, has_display_name=has_display_name)
    bp = Blueprint(blueprint_name, __name__, template_folder="templates")

    def _notify_signup(identifier: str, method: str) -> None:
        if not admin_email or not from_email:
            return
        from . import email as mailer

        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        subject = f"[{app_name}] New signup: {identifier}"
        body = (
            f"<p>New user signed up on {app_name}.</p>"
            f"<p><strong>Account:</strong> {identifier}<br>"
            f"<strong>Method:</strong> {method}<br>"
            f"<strong>Time:</strong> {ts}</p>"
        )
        try:
            mailer.send(admin_email, subject, body, from_email)
        except Exception as e:
            print(f"[fla-auth] signup notify failed: {e}")

    def _ok(data: dict) -> tuple:
        return jsonify({"success": True, **data}), 200

    def _err(message: str, status: int = 400) -> tuple:
        return jsonify({"success": False, "error": message}), status

    @bp.post(f"{url_prefix}/login")
    def login():
        data = request.get_json(silent=True) or {}
        credential = data.get(login_field, "")
        user, error = handlers.login(db, credential, data.get("password", ""))
        if error:
            return _err(error, 401 if "Invalid" in error else 400)
        session.permanent = True
        session["user_id"] = user["id"]
        if login_field == "email":
            session["email"] = user.get("email", "")
            if has_display_name:
                session["display_name"] = user.get("display_name", "")
            return _ok({"email": user.get("email", ""), "display_name": user.get("display_name", "")})
        else:
            session["username"] = user["username"]
            return _ok({"username": user["username"]})

    @bp.post(f"{url_prefix}/register")
    def register():
        data = request.get_json(silent=True) or {}
        success, error = handlers.register(
            db,
            username=data.get("username", ""),
            email=data.get("email", ""),
            password=data.get("password", ""),
            display_name=data.get("display_name", ""),
            invite_code=data.get("invite_code", ""),
            required_invite_code=invite_code,
        )
        if success:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            identifier = data.get(login_field, "").strip()
            print(f"[fla-auth][SIGNUP] {identifier} @ {ts}", flush=True)
            _notify_signup(identifier, "email/password")
            return _ok({})
        return _err(error)

    @bp.post(f"{url_prefix}/logout")
    def logout():
        session.clear()
        return _ok({})

    @bp.post(f"{url_prefix}/user/change-password")
    def change_password():
        user_id = session.get("user_id")
        if not user_id:
            return _err("Not logged in", 401)
        data = request.get_json(silent=True) or {}
        success, error = handlers.change_password(
            db,
            user_id=user_id,
            current_password=data.get("current_password", ""),
            new_password=data.get("new_password", ""),
            confirm_password=data.get("confirm_password", ""),
        )
        if success:
            return _ok({})
        return _err(error)

    @bp.post(f"{url_prefix}/forgot-password")
    def forgot_password():
        if not secret_key or not app_url or not from_email:
            return _err("Password reset is not configured", 503)
        data = request.get_json(silent=True) or {}
        success, error = handlers.forgot_password(
            db,
            email=data.get("email", ""),
            secret_key=secret_key,
            app_url=app_url,
            from_email=from_email,
            app_name=app_name,
        )
        if success:
            return _ok({})
        return _err(error)

    @bp.post(f"{url_prefix}/reset-password")
    def reset_password():
        if not secret_key:
            return _err("Password reset is not configured", 503)
        data = request.get_json(silent=True) or {}
        success, error = handlers.reset_password(
            db,
            token=data.get("token", ""),
            new_password=data.get("new_password", ""),
            confirm_password=data.get("confirm_password", ""),
            secret_key=secret_key,
        )
        if success:
            return _ok({})
        return _err(error)

    # Google OAuth routes - only registered when client credentials are provided.
    if google_client_id and google_client_secret:
        _GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
        _GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
        _GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
        _GOOGLE_SCOPES = "openid email profile"

        @bp.get("/auth/google")
        def google_login():
            import urllib.parse

            state = secrets.token_urlsafe(16)
            session["oauth_state"] = state
            redirect_uri = f"{app_url.rstrip('/')}/auth/google/callback"
            params = {
                "client_id": google_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": _GOOGLE_SCOPES,
                "state": state,
                "access_type": "online",
            }
            return redirect(f"{_GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")

        @bp.get("/auth/google/callback")
        def google_callback():
            import urllib.parse

            import requests as http

            error = request.args.get("error")
            if error:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_denied")

            state = request.args.get("state", "")
            if not state or state != session.pop("oauth_state", None):
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_state")

            code = request.args.get("code", "")
            redirect_uri = f"{app_url.rstrip('/')}/auth/google/callback"

            # Exchange code for tokens.
            token_resp = http.post(
                _GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": google_client_id,
                    "client_secret": google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                timeout=10,
            )
            if not token_resp.ok:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_token")

            access_token = token_resp.json().get("access_token", "")
            if not access_token:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_token")

            # Fetch the user's profile from Google.
            userinfo_resp = http.get(
                _GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if not userinfo_resp.ok:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_userinfo")

            info = userinfo_resp.json()
            email = (info.get("email") or "").strip().lower()
            name = info.get("name") or info.get("given_name") or ""

            if not email:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_no_email")

            is_new = not db.email_exists(email)
            user = db.get_or_create_google_user(email, name)
            if not user:
                return redirect(f"{app_url.rstrip('/')}/login.html?error=google_db")
            session.permanent = True
            session["user_id"] = user["id"]
            session["username"] = user.get("username", "")

            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[fla-auth][GOOGLE] {email} (user {user['id']}) @ {ts}", flush=True)
            if is_new:
                _notify_signup(email, "Google")

            return redirect(f"{app_url.rstrip('/')}/trips.html")

    return bp
