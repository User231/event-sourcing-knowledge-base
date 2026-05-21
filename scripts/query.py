#!/usr/bin/env python3
"""Query the Event Sourcing knowledge base using RAG + Claude."""

import os
import sys
import argparse
import chromadb
from chromadb.utils import embedding_functions
from anthropic import Anthropic
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "event_sourcing_kb"

TOP_K = 8  # Number of chunks to retrieve

SYSTEM_PROMPT = """You are an expert assistant for event sourcing architecture.
You answer questions using ONLY the provided context from the knowledge base.
If the context doesn't contain enough information, say so honestly and suggest what the user could add to the knowledge base.

Rules:
- Be specific and practical. Give code examples when relevant.
- Reference specific libraries, frameworks, or patterns by name.
- If comparing options, use a structured format.
- When context includes GitHub repo information, reference the repo URL.
- If the question is about a language/framework not well covered, acknowledge the gap.
- Always cite which source(s) your answer draws from.
"""

console = Console()


def get_collection():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def retrieve(collection, query: str, top_k: int = TOP_K, filter_tag: str | None = None):
    """Retrieve the most relevant chunks for a query."""
    where_filter = None
    if filter_tag:
        where_filter = {"tags": {"$contains": filter_tag}}

    results = collection.query(
        query_texts=[query],
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "content": doc,
            "source": meta["source"],
            "source_type": meta["source_type"],
            "title": meta["title"],
            "tags": meta.get("tags", ""),
            "distance": dist,
        })
    return chunks


def build_context(chunks: list[dict]) -> str:
    """Format retrieved chunks into context for the LLM."""
    context_parts = []
    seen_sources = set()
    for i, chunk in enumerate(chunks):
        source_label = chunk["source"]
        if source_label not in seen_sources:
            seen_sources.add(source_label)
        context_parts.append(
            f"--- Source [{i+1}]: {chunk['title']} ({chunk['source_type']})\n"
            f"    URL/Path: {source_label}\n"
            f"    Tags: {chunk['tags']}\n\n"
            f"{chunk['content']}\n"
        )
    return "\n".join(context_parts)


def ask(query: str, filter_tag: str | None = None, show_sources: bool = True, interactive: bool = False):
    """Run a RAG query against the knowledge base."""
    collection = get_collection()

    # Retrieve relevant chunks
    chunks = retrieve(collection, query, filter_tag=filter_tag)

    if not chunks:
        console.print("[red]No relevant chunks found. Try a different query or re-run ingestion.[/red]")
        return

    if show_sources:
        console.print(Panel(
            "\n".join(f"  [{i+1}] {c['title']} ({c['source_type']}) — distance: {c['distance']:.3f}"
                      for i, c in enumerate(chunks)),
            title="Retrieved Sources",
            border_style="dim",
        ))

    # Build prompt
    context = build_context(chunks)
    user_message = f"""Context from the Event Sourcing Knowledge Base:

{context}

---

Question: {query}

Answer based on the context above. Cite sources by their number [1], [2], etc."""

    # Call Claude
    client = Anthropic()
    console.print("\n[bold]Answer:[/bold]\n")

    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        full_response = ""
        for text in stream.text_stream:
            full_response += text
            sys.stdout.write(text)
            sys.stdout.flush()

    print("\n")
    return full_response


def list_sources():
    """Show all indexed sources."""
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

    console.print(f"\n[bold]Indexed Sources ({len(sources)} total):[/bold]\n")
    for source, info in sorted(sources.items(), key=lambda x: x[1]["type"]):
        console.print(
            f"  [{info['type']:12s}] {info['title']}"
            f"  ({info['chunks']} chunks)  tags: {info['tags']}"
        )
        console.print(f"               {source}", style="dim")


def interactive_mode():
    """Run an interactive query session."""
    console.print(Panel(
        "[bold]Event Sourcing Knowledge Base[/bold]\n\n"
        "Ask questions about event sourcing architecture.\n"
        "Type 'quit' or 'exit' to stop.\n"
        "Type 'sources' to list indexed sources.\n"
        "Prefix with 'tag:python ' to filter by tag.",
        border_style="blue",
    ))

    while True:
        try:
            query = console.input("\n[bold blue]Q:[/bold blue] ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            break
        if query.lower() == "sources":
            list_sources()
            continue

        # Check for tag filter
        filter_tag = None
        if query.startswith("tag:"):
            parts = query.split(" ", 1)
            filter_tag = parts[0][4:]
            query = parts[1] if len(parts) > 1 else ""
            if not query:
                console.print("[yellow]Please provide a question after the tag filter.[/yellow]")
                continue
            console.print(f"  [dim]Filtering by tag: {filter_tag}[/dim]")

        ask(query, filter_tag=filter_tag, interactive=True)


def main():
    parser = argparse.ArgumentParser(description="Query the Event Sourcing knowledge base")
    parser.add_argument("query", nargs="?", help="Question to ask (omit for interactive mode)")
    parser.add_argument("--list-sources", action="store_true", help="List all indexed sources")
    parser.add_argument("--filter-tag", type=str, help="Filter results by tag")
    parser.add_argument("--no-sources", action="store_true", help="Hide source list in output")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    args = parser.parse_args()

    if args.list_sources:
        list_sources()
        return

    if args.interactive or args.query is None:
        interactive_mode()
        return

    ask(args.query, filter_tag=args.filter_tag, show_sources=not args.no_sources)


if __name__ == "__main__":
    main()
