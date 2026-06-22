"""Tests for fiat_lux_agents.auth plugin."""

from __future__ import annotations

import contextlib
import sqlite3

import pytest
from flask import Flask

from fiat_lux_agents.auth import make_auth_blueprint
from fiat_lux_agents.auth.db import AuthDB, hash_password, verify_password
from fiat_lux_agents.auth import handlers


# ---------------------------------------------------------------------------
# In-memory SQLite fixture
# ---------------------------------------------------------------------------

_CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
)
"""


@pytest.fixture
def mem_db_factory():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_USERS)
    conn.commit()

    @contextlib.contextmanager
    def get_connection():
        yield conn

    yield get_connection
    conn.close()


@pytest.fixture
def auth_db(mem_db_factory):
    return AuthDB(mem_db_factory, use_postgres=False)


@pytest.fixture
def client(mem_db_factory):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["TESTING"] = True
    bp = make_auth_blueprint(mem_db_factory, use_postgres=False)
    app.register_blueprint(bp)
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# AuthDB unit tests
# ---------------------------------------------------------------------------


class TestHashAndVerify:
    def test_round_trip(self):
        h = hash_password("hello123")
        assert verify_password("hello123", h)

    def test_wrong_password(self):
        h = hash_password("hello123")
        assert not verify_password("wrong", h)


class TestAuthDB:
    def test_create_and_authenticate(self, auth_db):
        uid = auth_db.create_user("alice", "alice@example.com", "secret99")
        assert uid is not None
        user = auth_db.authenticate("alice", "secret99")
        assert user is not None
        assert user["username"] == "alice"
        assert "password_hash" not in user

    def test_authenticate_wrong_password(self, auth_db):
        auth_db.create_user("bob", "bob@example.com", "rightpass")
        assert auth_db.authenticate("bob", "wrongpass") is None

    def test_username_exists(self, auth_db):
        auth_db.create_user("carol", "carol@example.com", "pass123")
        assert auth_db.username_exists("carol")
        assert not auth_db.username_exists("nobody")

    def test_email_exists(self, auth_db):
        auth_db.create_user("dave", "dave@example.com", "pass123")
        assert auth_db.email_exists("dave@example.com")
        assert not auth_db.email_exists("other@example.com")

    def test_change_password(self, auth_db):
        uid = auth_db.create_user("eve", "eve@example.com", "oldpass1")
        ok, err = auth_db.change_password(uid, "oldpass1", "newpass1")
        assert ok
        assert auth_db.authenticate("eve", "newpass1") is not None
        assert auth_db.authenticate("eve", "oldpass1") is None

    def test_change_password_wrong_current(self, auth_db):
        uid = auth_db.create_user("frank", "frank@example.com", "pass123")
        ok, err = auth_db.change_password(uid, "wrongcurrent", "newpass1")
        assert not ok
        assert "incorrect" in err.lower()


# ---------------------------------------------------------------------------
# Handler unit tests
# ---------------------------------------------------------------------------


class TestHandlers:
    def test_register_valid(self, auth_db):
        ok, err = handlers.register(auth_db, "grace", "grace@example.com", "pass123")
        assert ok
        assert err is None

    def test_register_short_username(self, auth_db):
        ok, err = handlers.register(auth_db, "ab", "ab@example.com", "pass123")
        assert not ok
        assert "Username" in err

    def test_register_invalid_email(self, auth_db):
        ok, err = handlers.register(auth_db, "henry", "notanemail", "pass123")
        assert not ok
        assert "email" in err.lower()

    def test_register_short_password(self, auth_db):
        ok, err = handlers.register(auth_db, "ivan", "ivan@example.com", "12345")
        assert not ok
        assert "Password" in err

    def test_register_duplicate_username(self, auth_db):
        handlers.register(auth_db, "judy", "judy@example.com", "pass123")
        ok, err = handlers.register(auth_db, "judy", "other@example.com", "pass123")
        assert not ok
        assert "taken" in err.lower()

    def test_register_invite_code_required(self, auth_db):
        ok, err = handlers.register(
            auth_db, "kent", "kent@example.com", "pass123",
            invite_code="", required_invite_code="secret"
        )
        assert not ok

    def test_register_invite_code_wrong(self, auth_db):
        ok, err = handlers.register(
            auth_db, "kent", "kent@example.com", "pass123",
            invite_code="wrong", required_invite_code="secret"
        )
        assert not ok

    def test_register_invite_code_correct(self, auth_db):
        ok, err = handlers.register(
            auth_db, "kent", "kent@example.com", "pass123",
            invite_code="secret", required_invite_code="secret"
        )
        assert ok

    def test_change_password_mismatch(self, auth_db):
        uid = auth_db.create_user("lena", "lena@example.com", "pass123")
        ok, err = handlers.change_password(auth_db, uid, "pass123", "newpass1", "newpass2")
        assert not ok
        assert "match" in err.lower()


# ---------------------------------------------------------------------------
# Blueprint / route integration tests
# ---------------------------------------------------------------------------


class TestBlueprint:
    def test_login_success(self, auth_db, client):
        auth_db.create_user("mary", "mary@example.com", "pass123")
        r = client.post("/api/login", json={"username": "mary", "password": "pass123"})
        assert r.status_code == 200
        assert r.get_json()["success"] is True

    def test_login_wrong_password(self, client):
        r = client.post("/api/login", json={"username": "nobody", "password": "x"})
        assert r.status_code == 401

    def test_register_and_login(self, client):
        r = client.post("/api/register", json={
            "username": "newuser", "email": "new@example.com", "password": "pass123"
        })
        assert r.status_code == 200
        r = client.post("/api/login", json={"username": "newuser", "password": "pass123"})
        assert r.status_code == 200

    def test_logout(self, client):
        r = client.post("/api/logout", json={})
        assert r.status_code == 200

    def test_change_password_not_logged_in(self, client):
        r = client.post("/api/user/change-password", json={
            "current_password": "a", "new_password": "bb", "confirm_password": "bb"
        })
        assert r.status_code == 401

    def test_change_password_logged_in(self, auth_db, client):
        auth_db.create_user("nick", "nick@example.com", "oldpass1")
        client.post("/api/login", json={"username": "nick", "password": "oldpass1"})
        r = client.post("/api/user/change-password", json={
            "current_password": "oldpass1",
            "new_password": "newpass1",
            "confirm_password": "newpass1",
        })
        assert r.status_code == 200
        assert r.get_json()["success"] is True
        # old password no longer works
        assert auth_db.authenticate("nick", "oldpass1") is None
        assert auth_db.authenticate("nick", "newpass1") is not None
