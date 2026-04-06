# Event Sourcing Knowledge Base

A local, semantic knowledge base for event sourcing architecture — powered by [repo-rag](https://github.com/user/repo-rag) (Qdrant + nomic-embed-text + tree-sitter).

## What This Does

- **Indexes** markdown notes, web articles, GitHub repo docs, and source code into a Qdrant vector store
- **Hybrid search** across all sources — semantic similarity + BM25 keyword matching with RRF fusion
- **Code search** — find real implementations across 13+ event sourcing repos (aggregates, snapshots, projections, etc.)
- **MCP server** — Claude Code can search the knowledge base directly via tool calls
- **Auto-reindex** — the MCP server detects git changes and incrementally updates the index

## Prerequisites

- [repo-rag](~/git/my/repo-rag) installed (`pip install -e ~/git/my/repo-rag`)
- Qdrant running (`docker compose -f ~/git/my/repo-rag/docker-compose.yaml up -d`)

## Quick Start

```bash
# Index everything (local docs, web articles, GitHub repos + code)
repo-rag index --force

# Search from terminal
repo-rag search "What is event sourcing and when should I use it?"
repo-rag search "aggregate pattern" --code-only
repo-rag search "snapshot" --language csharp

# Check what's indexed
repo-rag info

# Start MCP server (for Claude Code integration)
repo-rag serve
```

## Managing Sources

All sources are configured in `repo-rag.yaml`. After any change, re-run `repo-rag index --force`.

### Local markdown notes

Drop `.md` files into any folder under `knowledge_base/`. They're picked up automatically by the `local` source.

### Web articles

Add URLs under the `web:` section in `repo-rag.yaml`:

```yaml
sources:
  web:
    - url: https://example.com/great-event-sourcing-article
      tags: [patterns, cqrs]
```

Fetched articles are cached in `.repo-rag/web/`. To re-fetch all articles (e.g. if content changed), delete the cache and re-index:

```bash
rm -rf .repo-rag/web/
repo-rag index --force
```

### GitHub repositories

Add repos under the `github:` section in `repo-rag.yaml`:

```yaml
sources:
  github:
    - url: https://github.com/owner/repo
      tags: [python, example]
      clone: true                    # Set to false for README-only indexing
      code_paths: ["src/"]           # Optional: scope to specific directories
```

- **`clone: true`** — shallow-clones the repo to `.repo-rag/repos/` and indexes source code files
- **`clone: false`** — only fetches the README and key docs, no code indexing
- **`code_paths`** — limits which directories get indexed (useful for large repos where only specific paths have relevant code)

GitHub READMEs are cached in `.repo-rag/github/`.

### Removing a source

1. Remove the entry from `repo-rag.yaml`
2. Run `repo-rag index --force` to rebuild the index without it
3. Optionally clean up the cache:

```bash
# Remove a specific cloned repo
rm -rf .repo-rag/repos/owner_repo

# Remove a cached web article (find filename by URL slug)
ls .repo-rag/web/
rm .repo-rag/web/example_com_*.md

# Remove a cached GitHub README
rm -rf .repo-rag/github/owner_repo
```

### Updating cached content

```bash
# Re-fetch all web articles
rm -rf .repo-rag/web/
repo-rag index --force

# Re-clone all GitHub repos (get latest code)
rm -rf .repo-rag/repos/
repo-rag index --force

# Nuclear option: clear everything and rebuild
rm -rf .repo-rag/
repo-rag index --force
```

## Project Structure

```
event-sourcing-knowlege-base/
├── knowledge_base/          # Your markdown knowledge files
│   ├── concepts/            # Core ES concepts
│   ├── patterns/            # Implementation patterns
│   ├── libraries/           # Library guides & comparisons
│   └── languages/           # Language-specific strategies
├── repo-rag.yaml            # Source configuration
├── .mcp.json                # MCP server config for Claude Code
└── README.md
```

Cache and index data locations:

| Data | Location |
|---|---|
| Vector index | Qdrant Docker volume (http://localhost:6333/dashboard) |
| Web article cache | `.repo-rag/web/` |
| GitHub README cache | `.repo-rag/github/` |
| Cloned repos | `.repo-rag/repos/` |
| Index state | `.repo-rag/.state` |

## How It Works

1. **Indexing** scans all sources, chunks code with tree-sitter (AST-aware: functions, classes as units) and docs by paragraphs, embeds with nomic-embed-text-v1.5, and stores in Qdrant with dense + BM25 sparse vectors.
2. **Searching** uses hybrid retrieval — semantic similarity and keyword matching fused with Reciprocal Rank Fusion (RRF).
3. **Incremental updates** — on subsequent `repo-rag index` calls, only files changed since the last git commit are re-indexed.
4. **MCP auto-reindex** — when Claude Code calls a search tool, the server checks if git HEAD has moved and incrementally updates before searching.

## Tips

- Run `repo-rag info` to see chunk counts by source type and language
- Use `--code-only` flag to search only code (no docs/articles)
- Use `--language python` to filter code by language
- Visit http://localhost:6333/dashboard to browse the Qdrant collection visually
