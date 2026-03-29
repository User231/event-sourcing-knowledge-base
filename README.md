# Event Sourcing Knowledge Base (RAG)

A local, self-hosted knowledge base for event sourcing architecture — powered by ChromaDB + Anthropic Claude.

## What This Does

- **Indexes** markdown notes, web articles, GitHub repo docs, and library references into a local vector store
- **Searches** across all sources with semantic similarity (not just keyword matching)
- **Answers** natural-language questions using RAG (Retrieval-Augmented Generation) via Claude
- **Grows** with you — add your own notes, articles, and repos over time

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Anthropic API key
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. Ingest the pre-seeded knowledge base
python scripts/ingest.py

# 4. Ask questions
python scripts/query.py "What is event sourcing and when should I use it?"
python scripts/query.py "Compare EventStoreDB vs Marten for .NET"
python scripts/query.py "How do I handle event versioning?"
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
│   ├── query.py             # CLI query interface (RAG)
│   ├── fetch_web.py         # Fetch & extract article content
│   └── fetch_github.py      # Fetch GitHub repo READMEs/docs
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
- The vector DB lives in `./chroma_db/` — delete it and re-ingest to rebuild from scratch
