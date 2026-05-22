# Tech Stack

## Project's own code
Only the Python sync scripts under `scripts/` are first-party code. Everything else in the workspace is **read-only reference material** (notes + cached external sources + cloned repos).

### Scripts
- **Python** (no version pin in code; uses `dict | None` syntax → 3.10+)
- Deps (`requirements.txt`):
  - `pyyaml>=6.0` — read `sources.yaml`
  - `requests>=2.31.0` — HTTP for articles + GitHub API/raw
  - `beautifulsoup4>=4.12.0` — HTML parsing
  - `markdownify>=0.13.0` — HTML → Markdown conversion
- Dependency / venv manager: **`uv`** (see [[suggested_commands]]).
- Linting: **flake8** (`max-line-length = 200`, see `.flake8`).
- No formatter pinned, no test suite.

## Reference-material languages (for Serena/Codegraph indexing only)
Active language servers in `.serena/project.yml`: **python, typescript, java, csharp, kotlin, elixir, php, rust, markdown**. The first one is the default/fallback language server.

## MCP servers (external)
- **Serena** — invoked as `serena start-mcp-server --context claude-code --project .` (must be on `PATH`).
- **Codegraph** — invoked as `codegraph serve --mcp` (must be on `PATH`). Index lives under `.codegraph/`.

Both are wired in `.mcp.json` and auto-start when the folder is opened in Claude Code.

## Excluded from indexing
- `.serena/project.yml` `ignored_paths`: `.codegraph`, `repos_cloned/**/.git` (other gitignored paths inherit via `ignore_all_files_in_gitignore: true`).
- `.codegraph/config.json` has an extensive `exclude` list (node_modules, build dirs, caches, vendor dirs, etc.) — see file directly when relevant.
- `repos_cloned/` is intentionally **not** gitignored so all tools can see it, but its nested `.git` directories show as untracked in `git status` and must not be staged.
