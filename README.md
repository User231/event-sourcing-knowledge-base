# Event Sourcing Knowledge Base

A local knowledge base for event sourcing — markdown notes plus a curated set of cloned reference repositories — made queryable in Claude Code via two MCP servers: [Serena](https://github.com/oraios/serena) (LSP-backed symbol intelligence) and [Codegraph](https://github.com/codegraph/codegraph) (SQLite knowledge graph of symbols + edges).

## What This Does

- **Markdown notes** in `knowledge_base/` for concepts, patterns, libraries, and language-specific guides.
- **Reference implementations** in `repos_cloned/` — 13 event sourcing libraries and example repos across C#, Java/Kotlin, TypeScript, Python, Elixir, PHP, and Rust. Tracked in this repo so Claude Code can navigate them.
- **Serena MCP** — symbol-aware code navigation across `knowledge_base/` and `repos_cloned/` via language servers (find symbol, find references, rename, edit by symbol).
- **Codegraph MCP** — pre-built knowledge graph of every symbol, edge, and file; sub-millisecond lookups for callers/callees/impact/context.

## Prerequisites

- [Serena](https://github.com/oraios/serena) installed and on PATH as `serena`
- [Codegraph](https://github.com/codegraph/codegraph) installed and on PATH as `codegraph`
- For Serena symbol tools to work on a given repo, the corresponding language server must be available locally. Serena auto-installs most of these; see [Serena's language servers docs](https://oraios.github.io/serena/01-about/020_programming-languages.html#language-servers) for any that need manual setup (notably C#/Java/Kotlin can require extra steps).

## Quick Start

Both MCP servers are wired up in `.mcp.json` and start automatically when you open this folder in Claude Code. Just ask:

- "Where is the `Aggregate` base class defined in Marten?"
- "Show me how `commanded` handles snapshotting."
- "What calls `apply_event` across the Python eventsourcing library?"

Claude Code will route those to Codegraph (for graph-style lookups) or Serena (for symbol-aware reads/edits).

## Managing Sources

### Local markdown notes

Drop `.md` files anywhere under `knowledge_base/`. Serena and Codegraph pick them up via filesystem traversal — no manual indexing step. Codegraph's watcher reflects edits within roughly a second.

### Cloned reference repos

Repos live under `repos_cloned/<owner>_<repo>/` and are committed to this repository so the knowledge base is self-contained.

To add a new repo:

```bash
git clone --depth 1 https://github.com/<owner>/<repo>.git \
  repos_cloned/<owner>_<repo>
rm -rf repos_cloned/<owner>_<repo>/.git
git add repos_cloned/<owner>_<repo>
```

(Stripping `.git` keeps it a plain directory tree rather than a submodule.)

To refresh a repo, delete the directory and re-clone with the steps above.

To remove a repo, just `rm -rf` its directory and commit.

### Serena project config

[.serena/project.yml](.serena/project.yml) lists the languages Serena should start language servers for. Edit the `languages:` list there if you add a repo in a language not yet covered.

## Project Structure

```
event-sourcing-knowlege-base/
├── knowledge_base/          # Your markdown knowledge files
│   ├── concepts/            # Core ES concepts
│   ├── implementation-patterns/
│   ├── patterns/
│   ├── libraries/
│   └── languages/
├── repos_cloned/            # Reference implementations (committed)
│   ├── AxonFramework_AxonFramework/
│   ├── JasperFx_marten/
│   └── ...
├── .mcp.json                # MCP server config (serena + codegraph)
├── .serena/project.yml      # Serena language list and ignores
└── README.md
```

## How It Works

1. **Serena** runs a language server per configured language and exposes symbol-level tools (`find_symbol`, `find_referencing_symbols`, `replace_symbol_body`, etc.) over MCP. Best for "edit this method" or "where is X referenced."
2. **Codegraph** maintains a SQLite knowledge graph of every symbol, edge, and file in the workspace, updated incrementally by a file watcher. Best for "what calls this," "blast radius of changing X," and broad area-context queries.
3. Both servers respect `.gitignore`, so anything ignored (e.g. `.venv/`) is invisible to them. `repos_cloned/` is **not** ignored, so its contents are fully indexed.

## Tips

- Ask Codegraph first for "where is X" / "what calls Y" — it's faster and broader than grep.
- Use Serena when you need to read or modify a specific symbol's body.
- If Serena reports a language server failure for a given repo, check that the LSP for that language is installed on your system.
