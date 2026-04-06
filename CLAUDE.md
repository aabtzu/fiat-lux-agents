# Claude Code Rules — fiat-lux-agents

fiat-lux-agents is a **Python library** of reusable AI agents for data exploration.
It is the foundation that downstream apps (libertas, etc.) build on.
Changes here affect every app that depends on it — be conservative with breaking changes.

---

## Naming
- Always write "fiat-lux-agents" in full — in code, comments, docs, issues, and PRs
- Never abbreviate it (e.g. "fla") in any written artifact
- Package import name is `fiat_lux_agents` (underscores)

---

## Repository Structure
- `fiat_lux_agents/` — the library itself; this is what gets pip-installed
  - `base.py` — `LLMBase` class and shared utilities; all agents extend this
  - `explorer/` — `ExplorerBlueprint` Flask blueprint (mountable by any app)
  - `*_bot.py`, `*_engine.py` — individual agent classes
- `testapp/` — reference Flask app for manual and integration testing of the library
- `tests/` — pytest unit/integration tests for the library
- `docs/` — documentation and templates (including `app-claude-template.md`)
- `scripts/` — one-off utility scripts; never imported

---

## Adding a New Agent
- New agent classes go in `fiat_lux_agents/<name>_bot.py` or `<name>_engine.py`
- Extend `LLMBase` from `base.py`
- Export from `fiat_lux_agents/__init__.py` so apps can do `from fiat_lux_agents import MyBot`
- Add at least one test in `tests/`
- Document the public interface in `docs/`

---

## Model Selection
- `DEFAULT_MODEL` in `base.py` is the library-wide default — change it there, nowhere else
- Current default: `claude-sonnet-4-6`
- Agent-level overrides are fine but must use the same constants, not string literals
- Guidance for consumers:
  - **Haiku** (`claude-haiku-4-5-20251001`) — speed/cost tasks: classification, filtering
  - **Sonnet** (`claude-sonnet-4-6`) — quality tasks: parsing, chat, reasoning
  - **Opus** (`claude-opus-4-6`) — hardest reasoning tasks only

---

## File Length
- Target: no file longer than 500 lines; hard limit 800 lines
- Split large agent files by responsibility before adding more code
- Prefer many small focused files over one large one

---

## Code Quality
- No hardcoded model strings in logic — use `DEFAULT_MODEL` or a named constant
- No hardcoded config values or magic strings — use parameters or env vars
- Write comments explaining *why*, not just *what*
- Keep agent classes focused — one agent per file
- No speculative abstractions — build what is needed, not what might be needed

---

## Code Style (Python)
- Style enforced by **ruff** — run `ruff check . && ruff format .` before committing
- To auto-fix: `ruff check --fix . && ruff format .`
- Config lives in `pyproject.toml` under `[tool.ruff]`

---

## CI (GitHub Actions)
- CI runs on every push and PR to `main`
- Required checks: ruff lint, ruff format, pytest
- Never bypass CI — fix the root cause if checks fail
- Keep unit tests fast (under 60s); slow/API tests marked `@pytest.mark.integration`

---

## Testing
- All tests in `tests/` using pytest
- Run: `.venv/bin/python3 -m pytest tests/ -x -q`
- After any change to the library, run tests before considering the task done
- Tests must not rely on live API calls unless marked `@pytest.mark.integration`
- The `testapp/` is for manual testing and integration smoke tests — not a substitute for unit tests

---

## Downstream App Impact
- fiat-lux-agents is pip-installed by downstream apps — breaking the public API breaks those apps
- Public API = anything exported from `fiat_lux_agents/__init__.py`
- Before removing or renaming a public symbol, check if any downstream app uses it
- Prefer adding optional parameters over changing signatures
- When making breaking changes: bump the version in `pyproject.toml` and note it clearly in the commit

---

## testapp
- The `testapp/` is a Flask app — see `docs/app-claude-template.md` for Flask conventions
- Its purpose is to demonstrate and test the library, not to be a production app
- Keep it in sync with the library's public API
