# Event Sourcing Knowledge Base

A local knowledge base for event sourcing — markdown notes plus a curated set of cloned reference repositories — made queryable in Claude Code via two MCP servers: [Serena](https://github.com/oraios/serena) (LSP-backed symbol intelligence) and [Codegraph](https://github.com/codegraph/codegraph) (SQLite knowledge graph of symbols + edges).

## What This Does

- **Markdown notes** in [knowledge_base/](knowledge_base/) for concepts, patterns, libraries, and language-specific guides.
- **Reference implementations** in `repos_cloned/` — 13+ event sourcing libraries and example repos across C#, Java/Kotlin, TypeScript, Python, Elixir, PHP, and Rust. Cloned locally and visible to VS Code, Serena, and Codegraph. Each clone keeps its own `.git/` so you can `git pull` for updates; just don't `git add repos_cloned/` in this repository.
- **Serena MCP** — symbol-aware code navigation across notes and cloned repos via language servers (find symbol, find references, rename, edit by symbol).
- **Codegraph MCP** — pre-built knowledge graph of every symbol, edge, and file; sub-millisecond lookups for callers/callees/impact/context.

## Prerequisites

- [Serena](https://github.com/oraios/serena) installed and on `PATH` as `serena`
- [Codegraph](https://github.com/codegraph/codegraph) installed and on `PATH` as `codegraph`
- For Serena symbol tools to work on a given repo, the corresponding language server must be available locally. Serena auto-installs most of these; see [Serena's language servers docs](https://oraios.github.io/serena/01-about/020_programming-languages.html#language-servers) for any that need manual setup (notably C#/Java/Kotlin can require extra steps).

## Quick Start

```bash
# 1. Pull down the reference repos (idempotent — re-run to refresh)
./scripts/clone-repos.sh

# 2. Build the Codegraph index (Serena indexes lazily on demand)
codegraph index
```

Both MCP servers are wired up in [.mcp.json](.mcp.json) and start automatically when you open this folder in Claude Code. Then just ask:

- "Where is the `Aggregate` base class defined in Marten?"
- "Show me how `commanded` handles snapshotting."
- "What calls `apply_event` across the Python eventsourcing library?"

Claude Code will route those to Codegraph (for graph-style lookups) or Serena (for symbol-aware reads/edits).

## Managing Sources

### Local markdown notes

Drop `.md` files anywhere under [knowledge_base/](knowledge_base/). Codegraph's watcher reflects edits within roughly a second; Serena picks them up on its next tool call.

### Cloned reference repos

The canonical list lives in [scripts/clone-repos.sh](scripts/clone-repos.sh). To add a new repo, append `"<owner>/<repo>"` to the `REPOS` array and re-run the script.

To refresh a single repo manually:

```bash
git -C repos_cloned/<owner>_<repo> pull --ff-only
```

To remove a repo, `rm -rf repos_cloned/<owner>_<repo>` and delete its entry from `scripts/clone-repos.sh`.

`repos_cloned/` is intentionally **not** git-ignored so VS Code's file explorer, search, and the Codegraph / Serena indexers all see it. The nested `.git/` directories make each clone show as untracked inside this repository — that's fine, just don't stage them.

### Indexing config

- **Codegraph**: [.codegraph/config.json](.codegraph/config.json) controls include/exclude globs. Re-index with `codegraph index` after adding repos.
- **Serena**: [.serena/project.yml](.serena/project.yml) lists active language servers and explicit `ignored_paths` (including `repos_cloned/**/.git`).

## Project Structure

```
event-sourcing-knowlege-base/
├── knowledge_base/          # Markdown knowledge files (committed)
│   ├── concepts/
│   ├── implementation-patterns/
│   ├── patterns/
│   ├── libraries/
│   └── languages/
├── repos_cloned/            # Reference implementations (local, not committed)
│   ├── AxonFramework_AxonFramework/
│   ├── JasperFx_marten/
│   └── ...
├── scripts/
│   └── clone-repos.sh       # Bootstrap / refresh the reference repos
├── .mcp.json                # MCP server config (serena + codegraph)
├── .serena/project.yml      # Serena language list and ignore rules
├── .codegraph/config.json   # Codegraph include/exclude globs
└── README.md
```

## How It Works

1. **Serena** runs a language server per configured language and exposes symbol-level tools (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, etc.) over MCP. Best for "edit this method" or "where is X referenced."
2. **Codegraph** maintains a SQLite knowledge graph of every symbol, edge, and file in the workspace, updated incrementally by a file watcher. Best for "what calls this," "blast radius of changing X," and broad area-context queries.

## Tips

- Ask Codegraph first for "where is X" / "what calls Y" — it's faster and broader than grep.
- Use Serena when you need to read or modify a specific symbol's body.
- If Serena reports a language server failure for a given repo, check that the LSP for that language is installed on your system.
