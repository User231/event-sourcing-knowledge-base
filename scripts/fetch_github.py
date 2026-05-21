"""Fetch README and docs from GitHub repositories."""

import os
import re
import hashlib
import requests


CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ingested_sources", "github")

# Files to look for in repos (in priority order)
DOC_FILES = ["README.md", "readme.md", "docs/README.md", "CONTRIBUTING.md"]


def repo_to_dirname(url: str) -> str:
    # https://github.com/owner/repo -> owner_repo
    parts = url.rstrip("/").split("/")
    slug = f"{parts[-2]}_{parts[-1]}"
    return slug


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from GitHub URL."""
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def fetch_raw_file(owner: str, repo: str, filepath: str) -> str | None:
    """Fetch a file from GitHub's raw content CDN."""
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/{filepath}"
    try:
        resp = requests.get(raw_url, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def fetch_repo_info(owner: str, repo: str) -> dict | None:
    """Fetch basic repo info from GitHub API (no auth needed for public repos)."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        resp = requests.get(api_url, timeout=15, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def fetch_github_repo(url: str, description: str = "", force: bool = False) -> dict | None:
    """Fetch README and key docs from a GitHub repo, cache locally.

    Returns dict with keys: url, content, title, cached_path
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    owner, repo = parse_github_url(url)
    cache_dir = os.path.join(CACHE_DIR, repo_to_dirname(url))
    cached_path = os.path.join(cache_dir, "combined.md")

    if not force and os.path.exists(cached_path):
        with open(cached_path, "r") as f:
            content = f.read()
        return {"url": url, "content": content, "title": f"{owner}/{repo}", "cached_path": cached_path}

    os.makedirs(cache_dir, exist_ok=True)

    # Fetch repo info
    info = fetch_repo_info(owner, repo)
    repo_description = ""
    stars = 0
    language = ""
    if info:
        repo_description = info.get("description", "") or ""
        stars = info.get("stargazers_count", 0)
        language = info.get("language", "") or ""

    # Fetch doc files
    collected_docs = []
    for filepath in DOC_FILES:
        content = fetch_raw_file(owner, repo, filepath)
        if content:
            collected_docs.append((filepath, content))

    if not collected_docs:
        print(f"  [WARN] No docs found for {url}")
        return None

    # Build combined document
    header = f"""# {owner}/{repo}

- **URL**: {url}
- **Description**: {description or repo_description}
- **Stars**: {stars}
- **Primary Language**: {language}

---

"""
    combined = header
    for filepath, content in collected_docs:
        combined += f"\n\n## File: {filepath}\n\n{content}\n"

    # Truncate very long docs (keep first ~15k chars)
    if len(combined) > 15000:
        combined = combined[:15000] + "\n\n[... truncated for indexing ...]"

    with open(cached_path, "w") as f:
        f.write(combined)

    return {"url": url, "content": combined, "title": f"{owner}/{repo}", "cached_path": cached_path}


def fetch_all_repos(repos: list[dict], force: bool = False) -> list[dict]:
    results = []
    for repo in repos:
        url = repo["url"]
        print(f"  Fetching: {url}")
        result = fetch_github_repo(url, description=repo.get("description", ""), force=force)
        if result:
            result["tags"] = repo.get("tags", [])
            result["description"] = repo.get("description", "")
            results.append(result)
    return results


if __name__ == "__main__":
    import yaml

    sources_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources.yaml")
    with open(sources_path) as f:
        sources = yaml.safe_load(f)

    repos = fetch_all_repos(sources.get("github_repos", []))
    print(f"\nFetched {len(repos)} repos")
