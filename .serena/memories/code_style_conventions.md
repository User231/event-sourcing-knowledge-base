# Code Style & Conventions

This applies only to first-party code in `scripts/`. Cloned repos and ingested sources follow their own upstream conventions and should not be reformatted.

## Python (scripts/)
- **Module docstring** as a one-liner at the top of each script (see `scripts/clone_repos.py`, `scripts/fetch_web.py`, `scripts/fetch_github.py`).
- **Function docstrings**: short, single-line or short multi-line, describing behavior and return shape. No reST/Google/Numpy formal style — just plain prose.
- **Type hints**: used on function signatures and return types. Modern syntax — `str | None`, `list[dict]`, `tuple[str, str]` (Python 3.10+).
- **Imports**: standard-library first, then third-party, separated by a blank line. No relative imports (single-package flat scripts).
- **Paths**: built with `os.path.join` and `os.path.dirname(__file__)`. (Not `pathlib` — keep consistent with existing scripts.)
- **Constants**: module-level UPPER_SNAKE_CASE (e.g. `PROJECT_ROOT`, `CACHE_DIR`, `SOURCES_PATH`, `DOC_FILES`).
- **CLI**: `argparse` in an `if __name__ == "__main__":` block. Boolean flags use `action="store_true"`. Always include a short `description` and `help` per flag.
- **Output**: human-readable `print()` lines with a `✓`/`✗`/`↻` prefix and a separator line (`"=" * 60`) for section headers. Don't introduce a logging framework — keep the prints.
- **Errors**: subprocesses and HTTP calls wrap in `try`/`except Exception` and print a `[WARN]` / `✗` line; functions return `None` (or `False`) on failure rather than raising.
- **Line length**: 200 (per `.flake8`). Long lines are tolerated; don't aggressively wrap.
- **Comments**: minimal. Existing scripts use them sparingly to explain *intent* (e.g. URL→slug mapping). Don't add narrative or task-tracking comments (matches the global CLAUDE rules).

## Markdown (knowledge_base/)
- Organized by topic under `knowledge_base/{concepts,implementation-patterns,patterns,libraries,languages}/`.
- No fixed frontmatter/heading template enforced — match neighboring files when adding new notes.

## CLAUDE.md project rules (enforced)
From `CLAUDE.md` at the repo root:
- Use **Serena MCP** proactively for code navigation/search (`find_symbol`, `get_symbols_overview`, `search_for_pattern`, `find_referencing_symbols`, etc.).
- Use **Codegraph MCP** proactively for indexed structure (`codegraph_context`, `codegraph_callers`, `codegraph_callees`, `codegraph_impact`, `codegraph_node`, `codegraph_explore`).
- If something in the project surprises you, alert the developer and add a note under "Agent notes" in `CLAUDE.md` so future agents don't hit the same issue.
