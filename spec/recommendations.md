## Current Implementation

**ChromaDB + sentence-transformers (`all-MiniLM-L6-v2`)** with custom Python scripts for:
- 4 ingestion pipelines (local markdown, web articles, GitHub READMEs, cloned repo code)
- Character-based chunking (1000 chars docs / 1500 chars code with overlap)
- MCP server exposing semantic search to Claude
- Metadata filtering by language, repo, tags

It works, but: custom scripts to maintain, no UI, basic chunking (not AST-aware), no hybrid search, manual setup per repo.

---

## Recommendation

For your requirements (turnkey, multi-repo, open source, UI, maintainable):

### 1. **Onyx (formerly Danswer)** — Best overall fit

- **What**: Open-source enterprise search & RAG platform
- **Why it fits**:
  - Built-in connectors: GitHub, GitLab, Google Drive, Confluence, Slack, web scraping — no custom ingestion scripts
  - Multi-workspace: each repo/project gets its own isolated workspace
  - Web UI with chat, search, and admin dashboard
  - Hybrid search (keyword + semantic) out of the box
  - Docker-compose: `docker compose up` and you're running
  - Very active (16k+ GitHub stars, backed by YC)
  - Supports custom embedding models
- **Tradeoff**: Heavier (Postgres + Vespa + app server). Overkill for single-person use.
- **Add new repo**: Create new connector in UI, point at repo, done.

### 2. **Khoj** — Lighter alternative

- **What**: Open-source personal AI with built-in RAG
- **Why it fits**:
  - GitHub integration, file sync, web content indexing
  - Simple web UI + chat
  - Much lighter than Onyx (single process, SQLite optional)
  - Multi-user support, per-user knowledge bases
  - Can self-host with Docker
  - ~15k GitHub stars
- **Tradeoff**: Less enterprise features, weaker code-specific search.

### 3. **RAGFlow** — Best if you want graph visualization

- **What**: Open-source RAG engine by InfiniFlow
- **Why it fits**:
  - Has knowledge graph visualization (your "graph UI" ask)
  - Deep document parsing (PDF, code, markdown, structured data)
  - Chunk visualization — see how documents were split
  - Multi-knowledge-base support (one per repo)
  - Docker-compose deployment
  - 40k+ GitHub stars
- **Tradeoff**: More document-oriented than code-oriented. Graph features are the differentiator.

---

## Comparison

| Criteria | Current (ChromaDB) | Onyx | Khoj | RAGFlow |
|---|---|---|---|---|
| Setup effort | High (custom scripts) | Low (docker-compose) | Low (docker) | Low (docker-compose) |
| Multi-repo isolation | Manual | Workspaces | Per-user KBs | Multi-KB |
| Code-aware search | Basic | Good (connectors) | Basic | Moderate |
| Hybrid search | No (semantic only) | Yes | Yes | Yes |
| Graph UI | No | No | No | **Yes** |
| Web UI | No | Yes | Yes | Yes |
| MCP integration | Native | Would need adapter | Has plugins | Would need adapter |
| Maintenance | You maintain scripts | Community maintains | Community maintains | Community maintains |
| Weight | Lightest | Heaviest | Light | Medium |

---

## My pick

**Onyx** if you want the most robust, production-grade solution that Just Works across repos. The connector model means "add repo = click a button in UI."

**RAGFlow** if the graph visualization and chunk inspection matter to you — it's the only one with that built in.

For either, you can still keep your MCP server as a thin proxy that calls their search API, preserving Claude Code integration.

Want me to dig deeper into any of these, or explore the setup for one?