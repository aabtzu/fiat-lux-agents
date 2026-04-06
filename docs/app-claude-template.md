# Claude Code Rules — App Template

**Copy this file to the root of your new app as `CLAUDE.md` and customise as needed.**

This template covers conventions for apps built on top of fiat-lux-agents.
The parent library's rules (`fiat-lux-agents/CLAUDE.md`) also apply.

---

## Naming
- Always write "fiat-lux-agents" in full — in code, comments, docs, issues, and PRs
- Never abbreviate it (e.g. "fla") in any written artifact

---

## Project Structure
- `agents/` — feature modules, one sub-package per domain area
- `agents/<feature>/routes.py` — blueprint/router (thin wrappers only)
- `agents/<feature>/handler.py` — business logic for that feature
- `agents/<feature>/templates/` — HTML templates for that feature
- `agents/common/` — shared helpers, auth decorators, response utilities
- `static/js/`, `static/css/` — frontend assets
- `tests/` — all tests (pytest)
- `scripts/` — one-off utility scripts; never imported by the app
- Keep repo root clean — only essential files at root (`app.py`, `auth.py`, config files)

---

## Web Framework
- Use **Flask** (preferred) or **FastAPI** — do not mix both in one app
- **Flask**: blueprint-per-feature (`agents/*/routes.py`), `app.py` as factory
  - Sessions: Flask signed cookie (`session["user_id"]`), requires `SECRET_KEY` env var
  - Start locally: `AUTH_DISABLED=true SECRET_KEY=dev python3 app.py` or via `dev.sh`
  - Production: gunicorn — `gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --timeout 120`
- **FastAPI**: router-per-feature, `app.py` as factory with `include_router`
  - Production: uvicorn — `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Routes are **thin wrappers** — parse request, call handler, return response
- Business logic belongs in `handler.py`, not in route functions

---

## Frontend
- Vanilla JS only — no frameworks (no React, Vue, etc.)
- Never inline styles or scripts in HTML — always separate files
- Templates: `agents/<feature>/templates/` or root `templates/`
- Static assets: `static/js/` and `static/css/`
- Bump JS version query strings (e.g. `?v=2`) when editing JS files
- Use `novalidate` on forms where JS handles validation

---

## File Length
- Target: no file longer than 500 lines; hard limit 800 lines
- Split by responsibility before adding more code to a long file
- Python: split by domain (`trips.py`, `users.py`, etc.)
- JS: split by feature area (`app-chat.js`, `app-map.js`, etc.)

---

## SQL Style
- SQL queries must be **module-level named constants** — never inline inside functions
- Name in SCREAMING_SNAKE_CASE: `_SQL_INSERT_USER`, `_SQL_GET_TRIP_BY_LINK`
- Functions call the constant: `cursor.execute(_SQL_INSERT_USER, (...))`
- When SQL differs between PostgreSQL and SQLite, define separate constants:
  `_SQL_PG_INSERT_USER` / `_SQL_SQLITE_INSERT_USER`
- Dynamic WHERE clauses (filter builders) are the only exception — document why

---

## LLM / Agent Design
- Keep LLM calls out of route handlers — they belong in `handler.py` or agent classes
- Model selection:
  - **Haiku** (`claude-haiku-4-5-20251001`) — speed/cost: classification, filtering
  - **Sonnet** (`claude-sonnet-4-6`) — quality: parsing, chat, reasoning, generation
  - **Opus** (`claude-opus-4-6`) — hardest tasks only (expensive)
- Use named constants for model IDs — never hardcode strings in logic
- Cache LLM results where possible

---

## Auth
- Local dev bypass: `AUTH_DISABLED=true` env var
- Never hardcode credentials or API keys — always use environment variables
- Auth logic belongs in `agents/common/` (e.g. `require_auth` decorator)

---

## Database
- Support PostgreSQL (production) + SQLite (local dev) via `DATABASE_URL` env var
- Schema init at startup via `init_db()` — use `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`
- Split DB functions into focused modules (`users.py`, `trips.py`, etc.)
- Re-export everything from `database/__init__.py` so callers do `import database as db`

---

## Code Quality
- No hardcoded model names, config values, URLs, paths, or magic strings
- Comments explain *why*, not just *what*
- No duplicate logic — shared behavior goes in `agents/common/`
- No error handling for impossible scenarios — trust internal guarantees
- No speculative abstractions — build what the task requires

---

## Code Style (Python)
- Enforced by **ruff**: `ruff check . && ruff format .` before every commit
- Auto-fix: `ruff check --fix . && ruff format .`
- Config in `pyproject.toml` under `[tool.ruff]`

---

## CI (GitHub Actions)
Add `.github/workflows/ci.yml`:

```yaml
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
```

- CI must pass before merge — never bypass
- Unit tests must complete under 60 seconds; slow/API tests use `@pytest.mark.integration`

---

## Testing
- All tests in `tests/` using pytest
- Run: `.venv/bin/python3 -m pytest tests/ -x -q`
- Write or update a test for every feature or bug fix
- Never claim done without running tests and confirming they pass
- No hardcoded local paths, no live API calls unless `@pytest.mark.integration`
- If a change touches fiat-lux-agents, also run:
  `.venv/bin/python3 -m pytest ~/repos/fiat-lux-agents/tests/ -x -q`

---

## Deployment (Render)

**`render.yaml`** — commit this to the repo:
```yaml
services:
  - type: web
    name: my-app
    runtime: python
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 2 --timeout 120
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: my-app-db
          property: connectionString
      # SECRET_KEY and ANTHROPIC_API_KEY must be set in the Render dashboard
      # Generate SECRET_KEY with: openssl rand -hex 32

databases:
  - name: my-app-db
    databaseName: myapp
    plan: free
```

**Required env vars** — set in the Render dashboard, never committed:
- `SECRET_KEY` — Flask session signing key (`openssl rand -hex 32`)
- `ANTHROPIC_API_KEY` — for LLM calls

**Common Render gotchas**:
- Dashboard "Start Command" overrides `render.yaml` — keep it blank or in sync
- Free Postgres expires after 90 days — upgrade or back up before then
- `DATABASE_URL` uses `postgres://` scheme; psycopg2 needs `postgresql://` — replace on connect
- Static files served by gunicorn on Render (no CDN) — keep them small
