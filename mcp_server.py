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
