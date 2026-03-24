#!/usr/bin/env python3
"""Ingest all knowledge sources into ChromaDB vector store."""

import os
import sys
import glob
import hashlib
import yaml
import chromadb
from chromadb.utils import embedding_functions

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(__file__))
from fetch_web import fetch_all_articles
from fetch_github import fetch_all_repos


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CHROMA_DIR = os.path.join(PROJECT_ROOT, "chroma_db")
COLLECTION_NAME = "event_sourcing_kb"

# Chunking config
CHUNK_SIZE = 1000       # chars per chunk
CHUNK_OVERLAP = 200     # overlap between chunks


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, respecting paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
            chunks.append(current_chunk.strip())
            # Keep overlap from end of current chunk
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else current_chunk
            current_chunk = overlap_text + "\n\n" + para
        else:
            current_chunk = current_chunk + "\n\n" + para if current_chunk else para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def make_doc_id(source: str, chunk_idx: int) -> str:
    source_hash = hashlib.md5(source.encode()).hexdigest()[:12]
    return f"{source_hash}_chunk_{chunk_idx}"


def load_markdown_files() -> list[dict]:
    """Load all .md files from knowledge_base/."""
    kb_dir = os.path.join(PROJECT_ROOT, "knowledge_base")
    docs = []
    for md_path in glob.glob(os.path.join(kb_dir, "**", "*.md"), recursive=True):
        with open(md_path, "r") as f:
            content = f.read()
        rel_path = os.path.relpath(md_path, PROJECT_ROOT)
        # Determine category from directory
        parts = rel_path.split(os.sep)
        category = parts[1] if len(parts) > 2 else "general"
        docs.append({
            "content": content,
            "source": rel_path,
            "source_type": "markdown",
            "category": category,
            "tags": [category],
            "title": os.path.basename(md_path).replace(".md", "").replace("-", " ").title(),
        })
    return docs


def ingest():
    print("=" * 60)
    print("Event Sourcing Knowledge Base — Ingestion")
    print("=" * 60)

    # Load sources config
    sources_path = os.path.join(PROJECT_ROOT, "sources.yaml")
    with open(sources_path) as f:
        sources = yaml.safe_load(f)

    all_docs = []

    # 1. Local markdown files
    print("\n[1/3] Loading local markdown files...")
    md_docs = load_markdown_files()
    print(f"  Found {len(md_docs)} markdown files")
    all_docs.extend(md_docs)

    # 2. Web articles
    print("\n[2/3] Fetching web articles...")
    articles = fetch_all_articles(sources.get("articles", []))
    for article in articles:
        all_docs.append({
            "content": article["content"],
            "source": article["url"],
            "source_type": "web_article",
            "category": "article",
            "tags": article.get("tags", []),
            "title": article.get("title", article["url"]),
        })
    print(f"  Fetched {len(articles)} articles")

    # 3. GitHub repos
    print("\n[3/3] Fetching GitHub repositories...")
    repos = fetch_all_repos(sources.get("github_repos", []))
    for repo in repos:
        all_docs.append({
            "content": repo["content"],
            "source": repo["url"],
            "source_type": "github_repo",
            "category": "library",
            "tags": repo.get("tags", []),
            "title": repo.get("title", repo["url"]),
        })
    print(f"  Fetched {len(repos)} repos")

    # Chunk all documents
    print(f"\nChunking {len(all_docs)} documents...")
    all_chunks = []
    all_metadatas = []
    all_ids = []

    for doc in all_docs:
        chunks = chunk_text(doc["content"])
        for i, chunk in enumerate(chunks):
            doc_id = make_doc_id(doc["source"], i)
            all_chunks.append(chunk)
            all_metadatas.append({
                "source": doc["source"],
                "source_type": doc["source_type"],
                "category": doc["category"],
                "tags": ",".join(doc.get("tags", [])),
                "title": doc["title"],
                "chunk_index": i,
                "total_chunks": len(chunks),
            })
            all_ids.append(doc_id)

    print(f"  Total chunks: {len(all_chunks)}")

    # Initialize ChromaDB with sentence-transformer embeddings
    print("\nInitializing ChromaDB...")
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    client = chromadb.PersistentClient(path=CHROMA_DIR)

    # Delete existing collection if it exists (fresh ingest)
    try:
        client.delete_collection(COLLECTION_NAME)
        print("  Cleared existing collection")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"description": "Event Sourcing knowledge base"},
    )

    # Add in batches (ChromaDB recommends batches of ~5000)
    batch_size = 500
    for i in range(0, len(all_chunks), batch_size):
        end = min(i + batch_size, len(all_chunks))
        collection.add(
            documents=all_chunks[i:end],
            metadatas=all_metadatas[i:end],
            ids=all_ids[i:end],
        )
        print(f"  Indexed chunks {i+1}–{end}")

    print(f"\n{'=' * 60}")
    print(f"Done! Indexed {len(all_chunks)} chunks from {len(all_docs)} sources.")
    print(f"Vector DB stored at: {CHROMA_DIR}")
    print(f"\nRun queries with:")
    print(f"  python scripts/query.py \"your question here\"")
    print(f"{'=' * 60}")

    # Print source summary
    print("\nIndexed sources:")
    source_types = {}
    for doc in all_docs:
        st = doc["source_type"]
        source_types[st] = source_types.get(st, 0) + 1
    for st, count in source_types.items():
        print(f"  {st}: {count}")


if __name__ == "__main__":
    ingest()
