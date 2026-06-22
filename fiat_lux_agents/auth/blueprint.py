"""Flask blueprint factory for fla-auth.

Usage in app.py:
    from fiat_lux_agents.auth import make_auth_blueprint
    from database.connection import get_db, USE_POSTGRES

    auth_bp = make_auth_blueprint(
        get_connection=get_db,
        use_postgres=USE_POSTGRES,
        invite_code=os.environ.get("INVITE_CODE", ""),
    )
    app.register_blueprint(auth_bp)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Callable

from flask import Blueprint, jsonify, request, session

from .db import AuthDB
from . import handlers


def make_auth_blueprint(
    get_connection: Callable,
    use_postgres: bool = False,
    invite_code: str = "",
    url_prefix: str = "/api",
    blueprint_name: str = "fla_auth",
) -> Blueprint:
    """Return a configured auth blueprint.

    Args:
        get_connection: callable returning a context manager for a DB connection
        use_postgres:   True if the DB uses %s placeholders (Postgres), False for ? (SQLite)
        invite_code:    if set, required on registration
        url_prefix:     prefix for all routes (default /api)
        blueprint_name: Flask blueprint name (change if registering multiple times)
    """
    db = AuthDB(get_connection, use_postgres)
    bp = Blueprint(blueprint_name, __name__, template_folder="templates")

    def _ok(data: dict) -> tuple:
        return jsonify({"success": True, **data}), 200

    def _err(message: str, status: int = 400) -> tuple:
        return jsonify({"success": False, "error": message}), status

    @bp.post(f"{url_prefix}/login")
    def login():
        data = request.get_json(silent=True) or {}
        user, error = handlers.login(
            db,
            data.get("username", ""),
            data.get("password", ""),
        )
        if error:
            return _err(error, 401 if "Invalid" in error else 400)
        session["user_id"] = user["id"]
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
            invite_code=data.get("invite_code", ""),
            required_invite_code=invite_code,
        )
        if success:
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            print(f"[fla-auth][SIGNUP] {data.get('username', '').strip()} @ {ts}", flush=True)
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

    return bp
