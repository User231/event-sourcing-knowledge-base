# Event Sourcing Knowledge Base

A local knowledge base for event sourcing — markdown notes, cached web articles, fetched GitHub READMEs, and full clones of reference repos — made queryable in Claude Code via two MCP servers: [Serena](https://github.com/oraios/serena) (LSP-backed symbol intelligence) and [Codegraph](https://github.com/codegraph/codegraph) (SQLite knowledge graph of symbols + edges).

## What This Does

- **Markdown notes** in [knowledge_base/](knowledge_base/) for concepts, patterns, libraries, and language-specific guides.
- **Cached web articles** in `ingested_sources/web/` — fetched and converted to Markdown so they are searchable locally.
- **Cached GitHub READMEs** in `ingested_sources/github/` — for repos where we don't want a full clone (storage-engine internals, website-only repos).
- **Full clones** in `repos_cloned/` — 13+ event sourcing libraries and example repos across C#, Java/Kotlin, TypeScript, Python, Elixir, PHP, and Rust. Each clone keeps its own `.git/` so `git pull` keeps it fresh; just don't `git add repos_cloned/` here.
- **Serena MCP** — symbol-aware code navigation across notes and cloned repos via language servers (find symbol, find references, rename, edit by symbol).
- **Codegraph MCP** — pre-built knowledge graph of every symbol, edge, and file; sub-millisecond lookups for callers/callees/impact/context.

## Prerequisites

- [Serena](https://github.com/oraios/serena) installed and on `PATH` as `serena`
- [Codegraph](https://github.com/codegraph/codegraph) installed and on `PATH` as `codegraph`
- [uv](https://docs.astral.sh/uv/) for the source-management scripts:
  ```bash
  uv venv
  uv pip install -r requirements.txt
  ```
- For Serena symbol tools to work on a given repo, the corresponding language server must be available locally. Serena auto-installs most; see [Serena's language servers docs](https://oraios.github.io/serena/01-about/020_programming-languages.html#language-servers) for any that need manual setup (notably C#/Java/Kotlin can require extra steps).

## Quick Start

```bash
# 1. Pull down the reference repos listed in sources.yaml
uv run scripts/clone_repos.py

# 2. Cache web articles + GitHub READMEs into ingested_sources/
uv run scripts/fetch_web.py
uv run scripts/fetch_github.py

# 3. Build the Codegraph index (Serena indexes lazily on demand)
codegraph index
```

Both MCP servers are wired up in [.mcp.json](.mcp.json) and start automatically when you open this folder in Claude Code. Then ask:

- "Where is the `Aggregate` base class defined in Marten?"
- "Show me how `commanded` handles snapshotting."
- "What calls `apply_event` across the Python eventsourcing library?"

Claude Code will route those to Codegraph (for graph-style lookups) or Serena (for symbol-aware reads/edits).

## Managing Sources

All external sources are listed in [sources.yaml](sources.yaml). After editing it, re-run the relevant fetch/clone script:

| Source type | Defined in | Fetched by | Stored in |
|---|---|---|---|
| Web articles | `articles:` | `scripts/fetch_web.py` | `ingested_sources/web/` |
| GitHub READMEs (any repo) | `github_repos:` | `scripts/fetch_github.py` | `ingested_sources/github/` |
| Full clones (where `clone: true`) | `github_repos:` | `scripts/clone_repos.py` | `repos_cloned/<owner>_<repo>/` |

By default each script skips items that already exist on disk (cached web pages, cached READMEs, already-cloned repos). Pass `--force` to re-fetch / re-clone:

```bash
# Re-fetch articles even if cached Markdown exists
uv run scripts/fetch_web.py --force

# Re-fetch GitHub READMEs even if cached
uv run scripts/fetch_github.py --force

# Re-clone every repo from scratch
uv run scripts/clone_repos.py --force

# Or pull latest commits in already-cloned repos (no re-clone)
uv run scripts/clone_repos.py --pull
```

### Adding a new repo

Append it under `github_repos:` in [sources.yaml](sources.yaml):

```yaml
- url: https://github.com/owner/repo
  tags: [language, library]
  description: "What this repo is"
  clone: true                   # default; set false to only fetch README
  code_paths: ["src/core/"]     # optional scope for large repos
```

Then `python scripts/clone_repos.py` to clone, or `python scripts/fetch_github.py` to grab just the README.

### Adding a new article

Append under `articles:` in sources.yaml, then `python scripts/fetch_web.py`. The article is converted to Markdown and cached locally so Serena/grep can find it offline.

### Local markdown notes

Drop `.md` files anywhere under [knowledge_base/](knowledge_base/). Codegraph's watcher reflects edits within ~1s; Serena picks them up on its next tool call.

## Indexing Config

- **Codegraph**: [.codegraph/config.json](.codegraph/config.json) controls include/exclude globs. Re-run `codegraph index` after large source changes (it incrementally updates via a file watcher otherwise).
- **Serena**: [.serena/project.yml](.serena/project.yml) lists active language servers and explicit `ignored_paths` (including `repos_cloned/**/.git`).

`repos_cloned/` is intentionally **not** git-ignored so VS Code, Serena, and Codegraph all see it. The nested `.git/` directories make each clone show as untracked inside this repository — that's expected; just don't stage them.

## Project Structure

```
event-sourcing-knowlege-base/
├── knowledge_base/          # Markdown knowledge files (committed)
│   ├── concepts/
│   ├── implementation-patterns/
│   ├── patterns/
│   ├── libraries/
│   └── languages/
├── ingested_sources/        # Fetched caches (committed)
│   ├── web/                 # Articles converted to Markdown
│   └── github/              # READMEs for repos we don't fully clone
├── repos_cloned/            # Full clones (local only, not committed)
├── scripts/
│   ├── clone_repos.py       # Clone/refresh repos listed in sources.yaml
│   ├── fetch_web.py         # Cache web articles as Markdown
│   └── fetch_github.py      # Cache GitHub READMEs for clone:false repos
├── sources.yaml             # Manifest: articles + GitHub repos
├── requirements.txt         # Python deps for the scripts above
├── .mcp.json                # MCP server config (serena + codegraph)
├── .serena/project.yml      # Serena language list and ignore rules
├── .codegraph/config.json   # Codegraph include/exclude globs
└── README.md
```

## How It Works

1. **Serena** runs a language server per configured language and exposes symbol-level tools (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, etc.) over MCP. Best for "edit this method" or "where is X referenced."
2. **Codegraph** maintains a SQLite knowledge graph of every symbol, edge, and file in the workspace, updated incrementally by a file watcher. Best for "what calls this," "blast radius of changing X," and broad area-context queries.
3. The `scripts/` are just plumbing: clone source repos and pull cached docs to disk so the MCP servers and grep have something to index. There is no separate vector store anymore — Codegraph and Serena work directly on the filesystem.

## Tips

- Ask Codegraph first for "where is X" / "what calls Y" — it's faster and broader than grep.
- Use Serena when you need to read or modify a specific symbol's body.
- If Serena reports a language server failure for a given repo, check that the LSP for that language is installed on your system.
