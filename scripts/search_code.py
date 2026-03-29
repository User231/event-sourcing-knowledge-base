#!/usr/bin/env python3
"""Search for code examples in the Event Sourcing knowledge base."""

import os
import sys
import argparse
import chromadb
from chromadb.utils import embedding_functions
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "event_sourcing_kb"

TOP_K = 10  # More results for code search

# Map language names to Rich syntax lexer names
LEXER_MAP = {
    "csharp": "csharp",
    "java": "java",
    "kotlin": "kotlin",
    "python": "python",
    "typescript": "typescript",
    "javascript": "javascript",
    "rust": "rust",
    "elixir": "elixir",
    "php": "php",
    "go": "go",
    "ruby": "ruby",
    "scala": "scala",
    "fsharp": "fsharp",
    "markdown": "markdown",
}

console = Console()


def get_collection():
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    client = chromadb.PersistentClient(path=CHROMA_DIR)
    return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)


def search_code(query: str, top_k: int = TOP_K, language: str | None = None,
                repo: str | None = None, tag: str | None = None) -> list[dict]:
    """Search for code examples matching the query.

    Filters to source_type='github_code' and optionally by language/repo/tag.
    """
    collection = get_collection()

    # Build where filter — must be github_code
    where_conditions = [{"source_type": "github_code"}]

    if language:
        where_conditions.append({"language": language})

    if tag:
        where_conditions.append({"tags": {"$contains": tag}})

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
        console.print(f"[red]Search error: {e}[/red]")
        console.print("[dim]Have you run ingestion? python scripts/ingest.py[/dim]")
        return []

    hits = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        hits.append({
            "content": doc,
            "source": meta.get("source", ""),
            "title": meta.get("title", ""),
            "language": meta.get("language", ""),
            "file_path": meta.get("file_path", ""),
            "repo": meta.get("repo", ""),
            "tags": meta.get("tags", ""),
            "distance": dist,
        })

    return hits


def display_results(hits: list[dict], query: str):
    """Display code search results with syntax highlighting."""
    if not hits:
        console.print("[yellow]No code examples found. Try a different query.[/yellow]")
        console.print("[dim]Tip: Run 'python scripts/clone_repos.py' and 'python scripts/ingest.py' first.[/dim]")
        return

    console.print(Panel(
        f"[bold]Code Search Results for:[/bold] {query}\n"
        f"[dim]Found {len(hits)} relevant code snippets[/dim]",
        border_style="blue",
    ))

    for i, hit in enumerate(hits):
        # Header
        lang = hit["language"]
        lexer = LEXER_MAP.get(lang, "text")
        relevance = 1 - hit["distance"]  # Convert distance to similarity

        header = Text()
        header.append(f"[{i+1}] ", style="bold yellow")
        header.append(hit["title"], style="bold")
        header.append(f"  ({lang})", style="dim")
        header.append(f"  relevance: {relevance:.1%}", style="dim green")

        console.print()
        console.print(header)

        # Source URL
        if hit["source"]:
            console.print(f"    [dim]→ {hit['source']}[/dim]")

        # Code snippet with syntax highlighting
        console.print()
        try:
            syntax = Syntax(
                hit["content"],
                lexer,
                theme="monokai",
                line_numbers=False,
                word_wrap=True,
                padding=(0, 1),
            )
            console.print(syntax)
        except Exception:
            console.print(hit["content"])

        console.print("─" * min(console.width, 80), style="dim")


def list_languages():
    """Show all languages available in indexed code."""
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

    console.print("\n[bold]Indexed Code — Languages:[/bold]")
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        console.print(f"  {lang:15s} {count} chunks")

    console.print("\n[bold]Indexed Code — Repositories:[/bold]")
    for repo, count in sorted(repos.items(), key=lambda x: -x[1]):
        console.print(f"  {repo:45s} {count} chunks")


def main():
    parser = argparse.ArgumentParser(
        description="Search for event sourcing code examples",
        epilog="""Examples:
  %(prog)s "restoring aggregate state from snapshot"
  %(prog)s --language csharp "event upcasting"
  %(prog)s --repo oskardudycz "projecting events to read model"
  %(prog)s --tag python "aggregate root implementation"
  %(prog)s --list-languages""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="What to search for")
    parser.add_argument("--language", "-l", help="Filter by language (e.g., csharp, python, typescript)")
    parser.add_argument("--repo", "-r", help="Filter by repo (partial match, e.g., 'oskardudycz')")
    parser.add_argument("--tag", "-t", help="Filter by tag")
    parser.add_argument("--top", "-k", type=int, default=TOP_K, help=f"Number of results (default: {TOP_K})")
    parser.add_argument("--list-languages", action="store_true", help="List available languages and repos")
    args = parser.parse_args()

    if args.list_languages:
        list_languages()
        return

    if not args.query:
        parser.print_help()
        return

    hits = search_code(
        args.query,
        top_k=args.top,
        language=args.language,
        repo=args.repo,
        tag=args.tag,
    )
    display_results(hits, args.query)


if __name__ == "__main__":
    main()
