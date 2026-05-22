# Project Structure

```
event-sourcing-knowlege-base/                  # (note: "knowlege" — typo in repo name, intentional)
├── CLAUDE.md                                  # Project-level rules for Claude (use Serena + Codegraph proactively)
├── README.md                                  # Human-facing docs
├── sources.yaml                               # Manifest of articles + github_repos to fetch/clone
├── requirements.txt                           # Python deps for scripts/
├── .flake8                                    # max-line-length = 200 (only configured lint rule)
├── .gitignore                                 # .venv/, __pycache__/, *.pyc, .DS_Store, .obsidian
├── .mcp.json                                  # Wires up serena + codegraph MCP servers
├── .serena/project.yml                        # Serena: languages, ignored_paths, etc.
├── .codegraph/                                # Codegraph index + config (gitignored / ignored by Serena)
│   └── config.json                            # include/exclude globs for the graph
├── .venv/                                     # Local uv-managed virtualenv (gitignored)
│
├── scripts/                                   # First-party Python scripts (only real code in repo)
│   ├── clone_repos.py                         # Shallow-clone repos in sources.yaml
│   ├── fetch_web.py                           # Fetch articles → Markdown cache
│   └── fetch_github.py                        # Fetch GitHub READMEs → Markdown cache
│
├── knowledge_base/                            # Committed Markdown notes
│   ├── concepts/
│   ├── implementation-patterns/
│   ├── patterns/
│   ├── libraries/
│   └── languages/
│
├── ingested_sources/                          # Committed fetched caches
│   ├── web/                                   # *.md per article (slug + md5 hash)
│   └── github/<owner>_<repo>/combined.md      # README + key docs per repo
│
└── repos_cloned/                              # Local-only full clones (NOT committed)
    ├── AxonFramework_AxonFramework/
    ├── JasperFx_marten/
    ├── NickTsitlakidis_event-nest/
    ├── castore-dev_castore/
    ├── commanded_commanded/
    ├── eventuous_eventuous/
    ├── ocoda_event-sourcing/
    ├── oskardudycz_EventSourcing.JVM/
    ├── oskardudycz_EventSourcing.NetCore/
    ├── oskardudycz_EventSourcing.NodeJS/
    ├── prooph_event-store/
    ├── pyeventsourcing_eventsourcing/
    └── thalo-rs_thalo/
```

## Where to look for what
- **"How is this repo wired up?"** → `README.md`, `.mcp.json`, `.serena/project.yml`, `.codegraph/config.json`.
- **"What sources are tracked?"** → `sources.yaml` is the single source of truth.
- **"How does a fetch script work?"** → 3 small scripts in `scripts/`, ~150 LOC each, follow the same shape: read `sources.yaml`, iterate, write to a cache dir, skip if exists unless `--force`.
- **"Where is concept/library X documented?"** → first try `knowledge_base/`, then `ingested_sources/`, then `repos_cloned/`.
- **"Where is symbol/API X implemented in library Y?"** → Codegraph (`codegraph_context`/`codegraph_search`) on `repos_cloned/<owner>_<repo>/...`, or Serena's `find_symbol`.

## Naming convention for clones/caches
GitHub `https://github.com/<owner>/<repo>` is mapped to dir name `<owner>_<repo>` by both `scripts/clone_repos.py:repo_to_dirname` and `scripts/fetch_github.py:repo_to_dirname` (duplicate helpers — intentional, not yet refactored).
