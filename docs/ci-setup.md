# CI + Auto-merge Setup

How to configure a repo so Claude commits to a branch, opens a PR, waits for CI, and merges — automatically, with no confirmation prompts.

---

## How it works

There is no GitHub-side auto-merge configured. The entire flow is driven by the CLAUDE.md instruction and the `gh` CLI:

1. Claude creates a feature branch and pushes commits
2. `gh pr create` opens the PR
3. `gh pr checks <number> --watch` blocks until all CI checks pass
4. `gh pr merge <number> --squash --delete-branch` merges and deletes the branch
5. `git checkout main && git pull` returns to main

No branch protection rules are required for this to work, though you can add them for extra safety.

---

## Step 1 — CLAUDE.md rule

Add this to the project `CLAUDE.md` (already present in the fiat-lux-agents app template):

```markdown
## Git workflow
- For every code change: commit to a branch, push, open a PR, wait for CI to pass, then merge. Do all of this automatically without asking for confirmation at any step.
- Never push directly to main.
- After merging, pull main locally and delete the feature branch.
```

This is also in the global `~/.claude/CLAUDE.md` so it applies to repos that don't have their own CLAUDE.md.

---

## Step 2 — CI workflow

Create `.github/workflows/ci.yml`. Adjust the test command for the project stack.

**Python / pytest:**
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

**Node / npm:**
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
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm ci
      - run: npm test
```

The `gh pr checks --watch` command waits for all checks in this workflow before merging. CI must run on `pull_request` to `main` for the watch to have something to block on.

---

## Step 3 — Deploy workflow (Cloud Run, optional)

If the app deploys to Google Cloud Run, add `.github/workflows/deploy.yml`. This triggers automatically on merge to main, so deploy follows CI without any extra steps.

```yaml
name: Deploy to Cloud Run
on:
  push:
    branches: [main]
concurrency:
  group: deploy
  cancel-in-progress: true
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write
    env:
      PROJECT_ID: your-gcp-project-id
      REGION: us-central1
      SERVICE: your-service-name
    steps:
      - uses: actions/checkout@v4
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}
      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: ${{ env.SERVICE }}
          region: ${{ env.REGION }}
          source: .
```

Required GitHub secrets:
- `GCP_WORKLOAD_IDENTITY_PROVIDER` — Workload Identity Federation provider resource name
- `GCP_SERVICE_ACCOUNT` — service account email with Cloud Run deploy permissions

---

## Step 4 — gh CLI (prerequisite)

Claude uses the `gh` CLI for all PR operations. Confirm it is installed and authenticated:

```bash
gh auth status
```

If not installed: `brew install gh && gh auth login`

---

## Optional — GitHub repo settings

These are not required but reduce noise:

| Setting | Value | Why |
|---|---|---|
| Default merge method | Squash | Keeps main history linear; `--squash` flag matches |
| Automatically delete head branches | On | Belt-and-suspenders alongside `--delete-branch` |
| Require status checks before merging | On (branch protection) | Prevents merge if CI is skipped |

Set via: **Repo Settings → General → Pull Requests** and **Branches → Branch protection rules**.

---

## Checklist for a new repo

- [ ] Add git workflow rule to `CLAUDE.md`
- [ ] Add `.github/workflows/ci.yml`
- [ ] Add `.github/workflows/deploy.yml` (if Cloud Run)
- [ ] Confirm `gh auth status` is authenticated
- [ ] (Optional) Enable squash-only merge and auto-delete branches in repo settings
