"""Fetch and extract content from web articles."""

import os
import re
import hashlib
import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ingested_sources", "web")


def url_to_filename(url: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]", "_", url)[:80]
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{slug}_{url_hash}.md"


def fetch_article(url: str, force: bool = False) -> dict | None:
    """Fetch a URL, extract main content, convert to markdown, cache locally.

    Returns dict with keys: url, content, title, cached_path
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cached_path = os.path.join(CACHE_DIR, url_to_filename(url))

    if not force and os.path.exists(cached_path):
        with open(cached_path, "r") as f:
            content = f.read()
        title = content.split("\n")[0].lstrip("# ").strip() if content else url
        return {"url": url, "content": content, "title": title, "cached_path": cached_path}

    try:
        headers = {"User-Agent": "EventSourcingKB/1.0 (knowledge-base indexer)"}
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [WARN] Failed to fetch {url}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove noise
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Try to find main content area
    main = (
        soup.find("article")
        or soup.find("main")
        or soup.find("div", class_=re.compile(r"content|post|article|entry", re.I))
        or soup.find("body")
    )

    if not main:
        print(f"  [WARN] No main content found for {url}")
        return None

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else url

    content_md = md(str(main), heading_style="ATX", strip=["img"])
    content_md = re.sub(r"\n{3,}", "\n\n", content_md).strip()

    # Prepend title and source
    full_content = f"# {title}\n\nSource: {url}\n\n{content_md}"

    with open(cached_path, "w") as f:
        f.write(full_content)

    return {"url": url, "content": full_content, "title": title, "cached_path": cached_path}


def fetch_all_articles(articles: list[dict], force: bool = False) -> list[dict]:
    results = []
    for article in articles:
        url = article["url"]
        print(f"  Fetching: {url}")
        result = fetch_article(url, force=force)
        if result:
            result["tags"] = article.get("tags", [])
            result["description"] = article.get("description", "")
            results.append(result)
    return results


if __name__ == "__main__":
    import argparse
    import yaml

    parser = argparse.ArgumentParser(description="Fetch and cache web articles listed in sources.yaml")
    parser.add_argument("--force", action="store_true", help="Re-fetch even if a cached copy already exists")
    args = parser.parse_args()

    sources_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sources.yaml")
    with open(sources_path) as f:
        sources = yaml.safe_load(f)

    articles = fetch_all_articles(sources.get("articles", []), force=args.force)
    print(f"\nFetched {len(articles)} articles")
