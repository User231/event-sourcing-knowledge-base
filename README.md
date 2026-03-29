# Event Sourcing Knowledge Base (RAG)

A local, self-hosted knowledge base for event sourcing architecture — powered by ChromaDB + Anthropic Claude.

## What This Does

- **Indexes** markdown notes, web articles, GitHub repo docs, and **actual source code** into a local vector store
- **Searches** across all sources with semantic similarity (not just keyword matching)
- **Code Search** — find real coding examples across 13+ event sourcing repos (aggregates, snapshots, projections, etc.)
- **Answers** natural-language questions using RAG (Retrieval-Augmented Generation) via Claude
- **Grows** with you — add your own notes, articles, and repos over time

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Clone GitHub repos (source code for code search)
python scripts/clone_repos.py

# 4. Ingest everything (markdown, articles, READMEs, source code)
python scripts/ingest.py

# 5. Ask questions (RAG with Claude)
python scripts/query.py "What is event sourcing and when should I use it?"
python scripts/query.py "Compare EventStoreDB vs Marten for .NET"

# 6. Search for code examples
python scripts/search_code.py "restoring aggregate state from snapshot"
python scripts/search_code.py --language csharp "event upcasting"
python scripts/search_code.py --language typescript "aggregate root"
```

## Adding Your Own Sources

### Markdown notes

Drop `.md` files into any folder under `knowledge_base/`. Then re-run ingestion:

```bash
python scripts/ingest.py
```

### Web articles

Add URLs to `sources.yaml` under the `articles:` section:

```yaml
articles:
  - url: https://example.com/great-event-sourcing-article
    tags: [patterns, cqrs]
```

Then re-run ingestion.

### GitHub repositories

Add repos to `sources.yaml` under `github_repos:`:

```yaml
github_repos:
  - url: https://github.com/owner/repo
    description: "Short description of what this repo demonstrates"
    tags: [python, example]
    clone: true              # Set to false to skip cloning source code
    code_paths: ["src/"]     # Optional: scope indexing to specific directories
```

Then clone and re-ingest:

```bash
python scripts/clone_repos.py
python scripts/ingest.py
```

## Project Structure

```
event-sourcing-kb/
├── knowledge_base/          # Your markdown knowledge files
│   ├── concepts/            # Core ES concepts
│   ├── patterns/            # Implementation patterns
│   ├── libraries/           # Library guides & comparisons
│   └── languages/           # Language-specific strategies
├── scripts/
│   ├── ingest.py            # Ingest all sources into ChromaDB
│   ├── query.py             # CLI query interface (RAG + Claude)
│   ├── search_code.py       # Search for code examples
│   ├── clone_repos.py       # Clone GitHub repos for code indexing
│   ├── index_code.py        # Index source code files
│   ├── fetch_web.py         # Fetch & extract article content
│   └── fetch_github.py      # Fetch GitHub repo READMEs/docs
├── repos_cloned/            # Shallow-cloned GitHub repos (gitignored)
├── ingested_sources/        # Cache of fetched web/GitHub content
├── sources.yaml             # External sources registry
├── requirements.txt
└── README.md
```

## How It Works

1. **Ingestion** splits all sources into overlapping chunks, embeds them using a local sentence-transformer model, and stores them in a ChromaDB collection.
2. **Querying** embeds your question, retrieves the top-k most relevant chunks, and sends them as context to Claude with your question.
3. **Sources are tagged** with metadata (type, language, tags) so you can filter queries if needed.

## Tips

- Run `python scripts/query.py --list-sources` to see everything indexed
- Run `python scripts/query.py --filter-tag python "your question"` to scope results
- Run `python scripts/search_code.py --list-languages` to see what code is indexed
- Run `python scripts/search_code.py --language csharp "your query"` to filter code by language
- Run `python scripts/clone_repos.py --pull` to update cloned repos
- The vector DB lives in `./chroma_db/` — delete it and re-ingest to rebuild from scratch
