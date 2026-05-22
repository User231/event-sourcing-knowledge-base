# Suggested Commands

## Environment setup (one-time)
```bash
uv venv
uv pip install -r requirements.txt
```

`uv` is the canonical runner — invoke scripts with `uv run scripts/<name>.py` rather than activating the venv manually.

## Source sync (the only "real" workflows in this repo)

```bash
# Clone all repos with clone: true in sources.yaml (shallow, --depth 1)
uv run scripts/clone_repos.py

# Cache web articles → ingested_sources/web/*.md
uv run scripts/fetch_web.py

# Cache GitHub READMEs → ingested_sources/github/<owner>_<repo>/combined.md
uv run scripts/fetch_github.py
```

All three skip items already on disk. Flags:

- `--force` on any of them: re-fetch / re-clone from scratch.
- `--pull` on `clone_repos.py`: `git pull --ff-only` in existing clones instead of cloning.

## Indexing
```bash
codegraph index            # (Re)build the Codegraph SQLite graph
codegraph status           # Check index health/size (via MCP tool too)
```
Serena indexes lazily on demand; no explicit index command.

## Lint
```bash
.venv/bin/flake8 scripts/
# or, if venv is active:
flake8 scripts/
```
There is no `make`/`tox`/CI configuration; flake8 is the only configured check (`.flake8`: `max-line-length = 200`).

## Tests
There are no tests in this repo.

## Adding a new source
Edit `sources.yaml`, then run the relevant fetcher script. See `README.md` "Adding a new repo / article" sections. Item schema:

```yaml
# In github_repos:
- url: https://github.com/owner/repo
  tags: [language, library]
  description: "What this repo is"
  clone: true                   # default true; set false to only cache README
  code_paths: ["src/core/"]     # optional scope hint (informational only — no script enforces it yet)

# In articles:
- url: https://example.com/post
  tags: [concepts]
  description: "Why this article matters"
```

## Darwin/macOS notes
- Shell is `zsh`. Standard BSD-flavored `find`, `sed`, `grep` — prefer Serena MCP tools (`find_symbol`, `search_for_pattern`, `find_file`, `get_symbols_overview`) for code/markdown discovery (see [[code_style_conventions]] and the CLAUDE.md rules).
- For directory listing/cd, plain `ls`, `cd`, `pwd`, `cat`, `head`, `tail` work.

## Git notes
- Never `git add repos_cloned/` — the nested `.git` directories make the clones appear untracked but they must not be staged.
- Main branch is `main`.
