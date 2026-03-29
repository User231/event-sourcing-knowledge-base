#!/usr/bin/env python3
"""Index source code files from cloned GitHub repos into ChromaDB."""

import os
import hashlib
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CLONE_DIR = os.path.join(PROJECT_ROOT, "repos_cloned")
SOURCES_PATH = os.path.join(PROJECT_ROOT, "sources.yaml")

# Source file extensions to index (mapped to language names)
LANGUAGE_MAP = {
    ".cs": "csharp",
    ".java": "java",
    ".kt": "kotlin",
    ".py": "python",
    ".ts": "typescript",
    ".js": "javascript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".ex": "elixir",
    ".exs": "elixir",
    ".php": "php",
    ".go": "go",
    ".rb": "ruby",
    ".scala": "scala",
    ".fs": "fsharp",
    ".fsx": "fsharp",
}

# Directories to always skip
SKIP_DIRS = {
    ".git", "node_modules", "bin", "obj", ".vs", ".idea",
    "vendor", "build", "dist", "target", "out", "packages",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    "coverage", ".nyc_output", "artifacts",
}

# Skip test directories for cleaner results (tests are often boilerplate)
TEST_DIRS = {
    "test", "tests", "__tests__", "spec", "specs",
    "test_utils", "testing", "testutil",
}

# Maximum file size in bytes (skip large auto-generated files)
MAX_FILE_SIZE = 50_000  # 50KB

# Minimum file size (skip trivially small files)
MIN_FILE_SIZE = 100  # 100 bytes

# Code chunking config (larger than article chunks — code needs more context)
CODE_CHUNK_SIZE = 1500
CODE_CHUNK_OVERLAP = 300


def repo_to_dirname(url: str) -> str:
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}_{parts[-1]}"


def parse_repo_url(url: str) -> tuple[str, str]:
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def should_skip_dir(dirname: str, include_tests: bool = False) -> bool:
    """Check if a directory should be skipped."""
    if dirname in SKIP_DIRS:
        return True
    if not include_tests and dirname.lower() in TEST_DIRS:
        return True
    return False


def detect_language(filepath: str) -> str | None:
    """Detect language from file extension."""
    _, ext = os.path.splitext(filepath)
    return LANGUAGE_MAP.get(ext.lower())


def is_interesting_path(rel_path: str) -> bool:
    """Boost files in directories likely to have example/pattern code."""
    interesting = [
        "sample", "example", "demo", "tutorial",
        "src", "lib", "core", "domain",
        "aggregate", "event", "command", "projection",
        "snapshot", "saga", "process",
    ]
    path_lower = rel_path.lower()
    return any(part in path_lower for part in interesting)


def chunk_code(content: str, filepath: str, chunk_size: int = CODE_CHUNK_SIZE,
               overlap: int = CODE_CHUNK_OVERLAP) -> list[str]:
    """Split source code into chunks, respecting logical boundaries.

    Strategy:
    1. Try to split on class/namespace/module boundaries (double blank lines)
    2. Fall back to single blank line boundaries
    3. Last resort: fixed-size splitting
    """
    # Prepend file context header to first chunk
    file_header = f"// File: {filepath}\n\n"

    # Try splitting on double blank lines first (class boundaries)
    sections = content.split("\n\n\n")
    if len(sections) >= 3:
        blocks = sections
    else:
        # Fall back to single blank lines
        blocks = content.split("\n\n")

    chunks = []
    current_chunk = file_header

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        if len(current_chunk) + len(block) + 2 > chunk_size and len(current_chunk) > len(file_header):
            chunks.append(current_chunk.strip())
            # Keep overlap from end of current chunk
            overlap_text = current_chunk[-overlap:] if len(current_chunk) > overlap else ""
            current_chunk = f"// File: {filepath} (continued)\n\n{overlap_text}\n\n{block}"
        else:
            current_chunk = current_chunk + "\n\n" + block if current_chunk != file_header else file_header + block

    if current_chunk.strip() and len(current_chunk.strip()) > len(file_header):
        chunks.append(current_chunk.strip())

    return chunks


def collect_code_files(repo_dir: str, code_paths: list[str] | None = None,
                       include_tests: bool = False) -> list[dict]:
    """Walk a cloned repo and collect source code files.

    Args:
        repo_dir: Path to the cloned repo
        code_paths: Optional list of subdirectory prefixes to scope to
        include_tests: Whether to include test directories

    Returns:
        List of dicts with keys: filepath, rel_path, content, language
    """
    files = []

    for root, dirs, filenames in os.walk(repo_dir):
        # Filter out skip directories in-place (modifying dirs affects os.walk)
        dirs[:] = [d for d in dirs if not should_skip_dir(d, include_tests)]

        for filename in filenames:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, repo_dir)

            # Check if we should scope to specific paths
            if code_paths:
                if not any(rel_path.startswith(cp) for cp in code_paths):
                    continue

            # Check extension
            language = detect_language(filename)
            if language is None:
                # Also collect .md files in doc/example directories
                if filename.endswith(".md") and is_interesting_path(rel_path):
                    language = "markdown"
                else:
                    continue

            # Check file size
            try:
                file_size = os.path.getsize(filepath)
                if file_size > MAX_FILE_SIZE or file_size < MIN_FILE_SIZE:
                    continue
            except OSError:
                continue

            # Read content
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            # Skip files that are mostly auto-generated (heuristic)
            if content.startswith("// <auto-generated") or content.startswith("// This code was generated"):
                continue

            files.append({
                "filepath": filepath,
                "rel_path": rel_path,
                "content": content,
                "language": language,
            })

    return files


def load_code_docs(include_tests: bool = False) -> list[dict]:
    """Load and chunk all code files from cloned repos.

    Returns list of dicts ready for ChromaDB ingestion with keys:
        content, source, source_type, category, tags, title, language, file_path, repo
    """
    if not os.path.exists(CLONE_DIR):
        print("  [WARN] No cloned repos found. Run: python scripts/clone_repos.py")
        return []

    with open(SOURCES_PATH) as f:
        sources = yaml.safe_load(f)

    repo_configs = {}
    for repo in sources.get("github_repos", []):
        dirname = repo_to_dirname(repo["url"])
        repo_configs[dirname] = repo

    all_docs = []
    total_files = 0

    for dirname in sorted(os.listdir(CLONE_DIR)):
        repo_dir = os.path.join(CLONE_DIR, dirname)
        if not os.path.isdir(repo_dir):
            continue

        config = repo_configs.get(dirname, {})
        url = config.get("url", "")
        tags = config.get("tags", [])
        description = config.get("description", "")
        code_paths = config.get("code_paths")

        # Skip repos marked as clone: false
        if not config.get("clone", True):
            continue

        owner, repo_name = dirname.split("_", 1) if "_" in dirname else (dirname, "")
        repo_label = f"{owner}/{repo_name}"

        files = collect_code_files(repo_dir, code_paths=code_paths, include_tests=include_tests)
        total_files += len(files)
        print(f"  {repo_label}: {len(files)} source files")

        for file_info in files:
            chunks = chunk_code(file_info["content"], file_info["rel_path"])
            for i, chunk in enumerate(chunks):
                all_docs.append({
                    "content": chunk,
                    "source": f"{url}/blob/main/{file_info['rel_path']}" if url else file_info["filepath"],
                    "source_type": "github_code",
                    "category": "code_example",
                    "tags": tags + [file_info["language"]],
                    "title": f"{repo_label} — {file_info['rel_path']}",
                    "language": file_info["language"],
                    "file_path": file_info["rel_path"],
                    "repo": repo_label,
                    "chunk_index": i,
                })

    print(f"\n  Total: {total_files} source files → {len(all_docs)} code chunks")
    return all_docs


if __name__ == "__main__":
    """Standalone run: show stats about what would be indexed."""
    docs = load_code_docs()

    # Summary by repo
    repos = {}
    for doc in docs:
        repo = doc["repo"]
        repos[repo] = repos.get(repo, 0) + 1

    print(f"\nCode chunks by repo:")
    for repo, count in sorted(repos.items(), key=lambda x: -x[1]):
        print(f"  {repo}: {count} chunks")

    # Summary by language
    langs = {}
    for doc in docs:
        lang = doc["language"]
        langs[lang] = langs.get(lang, 0) + 1

    print(f"\nCode chunks by language:")
    for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
        print(f"  {lang}: {count} chunks")
