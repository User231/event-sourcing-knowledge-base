# Event Sourcing Knowledge Base — Project Overview

## Purpose
A **local knowledge base** for event sourcing. It is not application code — it is a curated, queryable corpus of:

- **Markdown notes** in `knowledge_base/` (concepts, patterns, libraries, languages).
- **Cached web articles** in `ingested_sources/web/` (fetched from URLs in `sources.yaml`, converted to Markdown).
- **Cached GitHub READMEs** in `ingested_sources/github/` (for repos where a full clone isn't wanted).
- **Full clones** of reference event-sourcing libraries/examples in `repos_cloned/` (kept as nested `.git` directories, not staged).

The corpus is made searchable inside Claude Code via two MCP servers configured in `.mcp.json`:

- **Serena** — LSP-backed symbol intelligence across the active languages (Python, TypeScript, Java, C#, Kotlin, Elixir, PHP, Rust, Markdown).
- **Codegraph** — SQLite knowledge graph of every symbol + edge + file; sub-millisecond lookups for callers/callees/context/impact.

## Typical user
The user (Dmytro) uses this repo to research/cross-reference event sourcing patterns across many languages and libraries by asking Claude Code questions like "where is the Aggregate base class defined in Marten?" or "what calls `apply_event` across pyeventsourcing?".

## What this repo is NOT
- Not a runnable application or library — there are no entrypoints to "run the app."
- Not a vector store / RAG system — Serena + Codegraph work directly on the filesystem; there is no embedding pipeline.
- The Python scripts under `scripts/` are **plumbing** for cloning/fetching sources, not core logic.
