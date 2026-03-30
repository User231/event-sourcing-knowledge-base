#!/usr/bin/env python3
"""MCP server exposing the Event Sourcing knowledge base to Claude."""

import os
import chromadb
from chromadb.utils import embedding_functions
from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = os.path.dirname(__file__)
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "event_sourcing_kb"

mcp = FastMCP("event-sourcing-kb")

_collection = None


def get_collection():
    global _collection
    if _collection is None:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        client = chromadb.PersistentClient(path=CHROMA_DIR)
        _collection = client.get_collection(
            name=COLLECTION_NAME, embedding_function=ef
        )
    return _collection


@mcp.tool()
def search_knowledge_base(query: str, top_k: int = 8, filter_tag: str | None = None) -> str:
    """Search the Event Sourcing knowledge base using semantic similarity.

    Use this to find information about event sourcing concepts, patterns,
    libraries, frameworks, CQRS, event stores, and related architecture topics.

    Args:
        query: Natural language question or search terms
        top_k: Number of results to return (default 8)
        filter_tag: Optional tag to filter results (e.g. "python", "dotnet", "cqrs")
    """
    collection = get_collection()

    where_filter = None
    if filter_tag:
        where_filter = {"tags": {"$contains": filter_tag}}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    if not results["documents"][0]:
        return "No relevant results found. Try a different query or broader terms."

    output_parts = []
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        output_parts.append(
            f"--- Result [{i+1}] (relevance: {1-dist:.2f}) ---\n"
            f"Source: {meta['title']} ({meta['source_type']})\n"
            f"Path/URL: {meta['source']}\n"
            f"Tags: {meta.get('tags', '')}\n\n"
            f"{doc}\n"
        )

    return "\n".join(output_parts)


@mcp.tool()
def search_code_examples(
    query: str,
    top_k: int = 10,
    language: str | None = None,
    repo: str | None = None,
    filter_tag: str | None = None,
) -> str:
    """Search for real code examples across cloned event sourcing repositories.

    Use this to find actual implementation code showing how to do things like:
    - Aggregate root implementation
    - Restoring aggregate state from snapshot
    - Event upcasting / versioning
    - Projections / read model building
    - Saga / process manager patterns
    - Command handling

    Available languages: csharp, java, typescript, python, elixir, php, rust, fsharp, kotlin
    Available repos: AxonFramework, EventSourcing.NetCore, EventSourcing.NodeJS,
        eventuous, marten, event-nest, EventSourcing.JVM, eventsourcing (python),
        commanded, prooph, thalo, castore, ocoda/event-sourcing

    Args:
        query: What code pattern or example to search for
        top_k: Number of results to return (default 10)
        language: Filter by programming language (e.g. "csharp", "python", "typescript")
        repo: Filter by repository name (partial match, e.g. "oskardudycz")
        filter_tag: Filter by tag (e.g. "nestjs", "dotnet")
    """
    collection = get_collection()

    where_conditions = [{"source_type": "github_code"}]

    if language:
        where_conditions.append({"language": language})
    if filter_tag:
        where_conditions.append({"tags": {"$contains": filter_tag}})
    if repo:
        where_conditions.append({"repo": {"$contains": repo}})

    if len(where_conditions) == 1:
        where_filter = where_conditions[0]
    else:
        where_filter = {"$and": where_conditions}

    try:
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        return f"Search error: {e}. Make sure you've run ingestion (python scripts/ingest.py)."

    if not results["documents"][0]:
        return "No code examples found. Try a different query, or run 'python scripts/clone_repos.py' and 'python scripts/ingest.py' first."

    output_parts = []
    for i, (doc, meta, dist) in enumerate(zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    )):
        relevance = 1 - dist
        lang = meta.get("language", "unknown")
        output_parts.append(
            f"--- Code Example [{i+1}] (relevance: {relevance:.1%}) ---\n"
            f"Repository: {meta.get('repo', 'unknown')}\n"
            f"File: {meta.get('file_path', 'unknown')}\n"
            f"Language: {lang}\n"
            f"URL: {meta['source']}\n\n"
            f"```{lang}\n{doc}\n```\n"
        )

    return "\n".join(output_parts)


@mcp.tool()
def list_code_languages() -> str:
    """List all programming languages and repositories available in the indexed code.

    Use this to discover what languages and repos are searchable before
    calling search_code_examples with a language or repo filter.
    """
    collection = get_collection()
    results = collection.get(
        where={"source_type": "github_code"},
        include=["metadatas"],
    )

    langs = {}
    repos = {}
    for meta in results["metadatas"]:
        lang = meta.get("language", "unknown")
        repo = meta.get("repo", "unknown")
        langs[lang] = langs.get(lang, 0) + 1
        repos[repo] = repos.get(repo, 0) + 1

    lines = ["Languages:\n"]
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        lines.append(f"  {lang}: {count} chunks")

    lines.append("\nRepositories:\n")
    for repo, count in sorted(repos.items(), key=lambda x: -x[1]):
        lines.append(f"  {repo}: {count} chunks")

    return "\n".join(lines)


@mcp.tool()
def list_sources() -> str:
    """List all indexed sources in the Event Sourcing knowledge base."""
    collection = get_collection()
    results = collection.get(include=["metadatas"])

    sources = {}
    for meta in results["metadatas"]:
        key = meta["source"]
        if key not in sources:
            sources[key] = {
                "title": meta["title"],
                "type": meta["source_type"],
                "tags": meta.get("tags", ""),
                "chunks": 0,
            }
        sources[key]["chunks"] += 1

    lines = [f"Indexed Sources ({len(sources)} total):\n"]
    for source, info in sorted(sources.items(), key=lambda x: x[1]["type"]):
        lines.append(
            f"  [{info['type']}] {info['title']} ({info['chunks']} chunks) "
            f"tags: {info['tags']}\n    {source}"
        )

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()

