# Task Completion Checklist

There is no CI, no test suite, and no formatter in this repo. When you change code, do the minimum that is actually configured:

## After editing `scripts/*.py`
1. **Lint with flake8** (the only configured check):
   ```bash
   .venv/bin/flake8 scripts/
   ```
   The only configured rule is `max-line-length = 200` (`.flake8`). Fix any reported issues.
2. **Smoke-run the affected script** if behavior changed. Each script is safe to re-run because they all default to skip-if-cached:
   ```bash
   uv run scripts/clone_repos.py     # uses --force/--pull as appropriate
   uv run scripts/fetch_web.py
   uv run scripts/fetch_github.py
   ```
3. **Do not** add or invoke `pytest`, `black`, `ruff`, `mypy`, or any other tool that isn't already configured in the repo — the user has not opted into them.

## After editing `sources.yaml`
- Re-run the matching fetcher script (see [[suggested_commands]]). Without `--force`, only the newly added entries are fetched.

## After editing `knowledge_base/*.md` or anything under `ingested_sources/`
- No build step. Codegraph's watcher reflects edits within ~1s; Serena picks them up on its next tool call.
- If you've done a large reshuffle, run `codegraph index` to be safe.

## Before committing
- `git status` — confirm no `repos_cloned/` paths are staged (the nested `.git` dirs make clones look untracked, but they must not be added).
- Don't stage `.venv/`, `__pycache__/`, `.DS_Store`, or `.obsidian/` (all in `.gitignore`).
- Don't commit unless the user explicitly asks (per global CLAUDE rules).

## Reporting back
- Be terse — the user is the sole developer, no PR review process to write for. State what changed and what's next in 1–2 sentences.
