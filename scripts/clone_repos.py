#!/usr/bin/env python3
"""Clone GitHub repositories listed in sources.yaml for code indexing."""

import os
import subprocess
import sys
import yaml


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
CLONE_DIR = os.path.join(PROJECT_ROOT, "repos_cloned")
SOURCES_PATH = os.path.join(PROJECT_ROOT, "sources.yaml")


def repo_to_dirname(url: str) -> str:
    """https://github.com/owner/repo -> owner_repo"""
    parts = url.rstrip("/").split("/")
    return f"{parts[-2]}_{parts[-1]}"


def clone_repo(url: str, target_dir: str, force: bool = False) -> bool:
    """Shallow-clone a repo. Returns True on success."""
    if os.path.exists(target_dir) and not force:
        print(f"  ✓ Already cloned: {os.path.basename(target_dir)}")
        return True

    if os.path.exists(target_dir) and force:
        print(f"  ↻ Re-cloning: {os.path.basename(target_dir)}")
        subprocess.run(["rm", "-rf", target_dir], check=True)

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", url, target_dir],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  ✓ Cloned: {os.path.basename(target_dir)}")
            return True
        else:
            print(f"  ✗ Failed: {os.path.basename(target_dir)}: {result.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout: {os.path.basename(target_dir)}")
        return False
    except Exception as e:
        print(f"  ✗ Error: {os.path.basename(target_dir)}: {e}")
        return False


def pull_repo(target_dir: str) -> bool:
    """Pull latest changes for an already-cloned repo."""
    try:
        result = subprocess.run(
            ["git", "-C", target_dir, "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print(f"  ✓ Updated: {os.path.basename(target_dir)}")
            return True
        else:
            print(f"  ✗ Pull failed: {os.path.basename(target_dir)}: {result.stderr.strip()}")
            return False
    except Exception as e:
        print(f"  ✗ Pull error: {os.path.basename(target_dir)}: {e}")
        return False


def clone_all(force: bool = False, pull: bool = False):
    """Clone all repos from sources.yaml that have clone enabled."""
    os.makedirs(CLONE_DIR, exist_ok=True)

    with open(SOURCES_PATH) as f:
        sources = yaml.safe_load(f)

    repos = sources.get("github_repos", [])

    # Filter out repos with clone: false
    clone_repos = [r for r in repos if r.get("clone", True)]
    skip_repos = [r for r in repos if not r.get("clone", True)]

    print("=" * 60)
    print("Event Sourcing KB — Clone GitHub Repositories")
    print("=" * 60)
    print(f"\nRepos to clone: {len(clone_repos)}")
    if skip_repos:
        print(f"Repos skipped (clone: false): {len(skip_repos)}")
        for r in skip_repos:
            print(f"  - {r['url']}")

    print()

    success = 0
    failed = 0
    for repo in clone_repos:
        url = repo["url"]
        dirname = repo_to_dirname(url)
        target_dir = os.path.join(CLONE_DIR, dirname)

        if pull and os.path.exists(target_dir):
            if pull_repo(target_dir):
                success += 1
            else:
                failed += 1
        else:
            if clone_repo(url, target_dir, force=force):
                success += 1
            else:
                failed += 1

    print(f"\n{'=' * 60}")
    print(f"Done! Success: {success}, Failed: {failed}")
    print(f"Cloned repos stored at: {CLONE_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clone GitHub repos for code indexing")
    parser.add_argument("--force", action="store_true", help="Re-clone all repos (delete and re-clone)")
    parser.add_argument("--pull", action="store_true", help="Pull latest changes for already-cloned repos")
    args = parser.parse_args()

    clone_all(force=args.force, pull=args.pull)
