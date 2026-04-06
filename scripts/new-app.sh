#!/usr/bin/env bash
# new-app.sh — scaffold a new fiat-lux-agents app
#
# Usage: ./scripts/new-app.sh <app-name> <target-dir>
# Example: ./scripts/new-app.sh my-travel-app ~/repos/my-travel-app
#
# Creates the standard project skeleton and copies the CLAUDE.md template
# so Claude Code has the right rules from the very first message.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLA_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEMPLATE="$FLA_ROOT/docs/app-claude-template.md"

if [[ $# -lt 2 ]]; then
    echo "Usage: $0 <app-name> <target-dir>"
    echo "  app-name   — short slug used in render.yaml and requirements (e.g. my-app)"
    echo "  target-dir — path where the new project will be created"
    exit 1
fi

APP_NAME="$1"
TARGET="$2"

if [[ -d "$TARGET" ]]; then
    echo "Error: $TARGET already exists. Choose a new directory."
    exit 1
fi

echo "Scaffolding $APP_NAME at $TARGET ..."

# --- Directory structure ---
mkdir -p "$TARGET"/{agents/common,static/{js,css},templates,tests,scripts}
mkdir -p "$TARGET"/.github/workflows

# --- CLAUDE.md (from template) ---
cp "$TEMPLATE" "$TARGET/CLAUDE.md"
echo "✓ CLAUDE.md copied from template"

# --- app.py ---
cat > "$TARGET/app.py" << 'PYTHON'
"""Flask application factory."""

from __future__ import annotations

import os

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.secret_key = os.environ["SECRET_KEY"]
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # type: ignore[assignment]

    # Register blueprints here, e.g.:
    # from agents.pages.routes import pages_bp
    # app.register_blueprint(pages_bp)

    from database.connection import init_db
    with app.app_context():
        init_db()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=False)
PYTHON
echo "✓ app.py"

# --- agents/common/flask_utils.py ---
cat > "$TARGET/agents/common/flask_utils.py" << 'PYTHON'
"""Shared Flask helpers: auth decorator, JSON response helpers."""

from __future__ import annotations

import functools
import os

from flask import g, jsonify, redirect, request, session


def load_current_user() -> None:
    """Populate g.user_id on every request from the session."""
    g.user_id = session.get("user_id")
    g.auth_disabled = os.environ.get("AUTH_DISABLED") == "true"


def require_auth(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not g.auth_disabled and not g.user_id:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Unauthorized"}), 401
            return redirect(f"/login?redirect={request.path}")
        return f(*args, **kwargs)
    return decorated


def json_ok(data):
    return jsonify(data), 200


def json_err(msg, status=400):
    return jsonify({"error": msg}), status
PYTHON
touch "$TARGET/agents/__init__.py"
touch "$TARGET/agents/common/__init__.py"
echo "✓ agents/common/flask_utils.py"

# --- database/connection.py ---
mkdir -p "$TARGET/database"
cat > "$TARGET/database/__init__.py" << 'PYTHON'
"""Database package — re-export all public functions here."""

from database.connection import get_db, init_db, USE_POSTGRES  # noqa: F401
PYTHON

cat > "$TARGET/database/connection.py" << 'PYTHON'
"""Database connection management and schema initialisation."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

try:
    import psycopg2
    import psycopg2.extras
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False

DATABASE_URL = os.environ.get("DATABASE_URL")
USE_POSTGRES = HAS_POSTGRES and DATABASE_URL is not None

_DDL_SQLITE_PRAGMA = "PRAGMA foreign_keys = ON"


def get_connection():
    """Return a raw database connection."""
    if USE_POSTGRES:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(_DDL_SQLITE_PRAGMA)
    return conn


@contextmanager
def get_db():
    """Context manager — yields a connection, commits or rolls back on exit."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables. Add DDL constants above and call cursor.execute() here."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Add your CREATE TABLE IF NOT EXISTS statements here
        print(f"[DB] Initialised {'PostgreSQL' if USE_POSTGRES else 'SQLite'} database")
PYTHON
echo "✓ database/connection.py"

# --- requirements.txt ---
cat > "$TARGET/requirements.txt" << REQS
# Core
flask>=3.0.0
gunicorn>=21.0.0
werkzeug>=3.0.0

# fiat-lux-agents (update path/version as needed)
fiat-lux-agents @ git+https://github.com/aabtzu/fiat-lux-agents

# Database
psycopg2-binary>=2.9.0

# Auth
bcrypt>=4.0.0

# Dev
python-dotenv>=1.0.0
pytest>=7.4.0
ruff>=0.4.0
REQS
echo "✓ requirements.txt"

# --- pyproject.toml (ruff config) ---
cat > "$TARGET/pyproject.toml" << TOML
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "W"]
ignore = ["E501"]
TOML
echo "✓ pyproject.toml"

# --- render.yaml ---
sed "s/my-app/$APP_NAME/g; s/myapp/${APP_NAME//-/_}/g" > "$TARGET/render.yaml" << YAML
services:
  - type: web
    name: $APP_NAME
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn "app:create_app()" --bind 0.0.0.0:\$PORT --workers 2 --timeout 120
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: ${APP_NAME}-db
          property: connectionString
      # SECRET_KEY and ANTHROPIC_API_KEY must be set in the Render dashboard
      # (never commit secrets). Generate SECRET_KEY with: openssl rand -hex 32

databases:
  - name: ${APP_NAME}-db
    databaseName: ${APP_NAME//-/_}
    plan: free
YAML
echo "✓ render.yaml"

# --- dev.sh ---
cat > "$TARGET/dev.sh" << 'BASH'
#!/usr/bin/env bash
set -euo pipefail

CMD="${1:-start}"

case "$CMD" in
  start)
    AUTH_DISABLED=true SECRET_KEY=dev python3 app.py
    ;;
  test)
    .venv/bin/python3 -m pytest tests/ -x -q "$@"
    ;;
  lint)
    .venv/bin/ruff check . && .venv/bin/ruff format .
    ;;
  *)
    echo "Usage: $0 [start|test|lint]"
    exit 1
    ;;
esac
BASH
chmod +x "$TARGET/dev.sh"
echo "✓ dev.sh"

# --- .github/workflows/ci.yml ---
cat > "$TARGET/.github/workflows/ci.yml" << YAML
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: ruff check .
      - run: ruff format --check .
      - run: pytest tests/ -x -q -m "not integration"
YAML
echo "✓ .github/workflows/ci.yml"

# --- .gitignore ---
cat > "$TARGET/.gitignore" << 'GITIGNORE'
.venv/
__pycache__/
*.pyc
*.pyo
.env
*.db
.DS_Store
GITIGNORE
echo "✓ .gitignore"

# --- tests/conftest.py stub ---
cat > "$TARGET/tests/conftest.py" << 'PYTHON'
"""pytest configuration."""

import os
import pytest

# Use SQLite in-memory for tests — never touch the dev or prod database
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.pop("DATABASE_URL", None)  # force SQLite
PYTHON
echo "✓ tests/conftest.py"

echo ""
echo "Done! Your app is at: $TARGET"
echo ""
echo "Next steps:"
echo "  cd $TARGET"
echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
echo "  cp .env.example .env  # then add ANTHROPIC_API_KEY"
echo "  ./dev.sh start"
echo ""
echo "Remember to:"
echo "  - Review and customise CLAUDE.md for your app's specific rules"
echo "  - Set SECRET_KEY and ANTHROPIC_API_KEY in the Render dashboard before deploying"
