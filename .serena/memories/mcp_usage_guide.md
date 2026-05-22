# MCP Usage Guide for This Repo

`CLAUDE.md` requires proactive use of Serena and Codegraph. This memo records *when* to reach for each so you don't fall back to grep/Read.

## Decision shortcuts

| Question | Tool of choice |
|---|---|
| "Where is symbol X defined / declared?" | `codegraph_search` (fastest), or Serena `find_symbol` for symbolic context |
| "What's the deal with feature/area Y?" | `codegraph_context` (composes search + node + callers + callees) |
| "What calls this function?" | `codegraph_callers` |
| "What does this function call?" | `codegraph_callees` |
| "Blast radius if I change this?" | `codegraph_impact` |
| "Show me the source of this symbol." | `codegraph_node`, or Serena `find_symbol` with `include_body=True` |
| "Survey several related symbols at once." | `codegraph_explore` (one capped call beats many `Read`s) |
| "What files are in directory X?" | `codegraph_files` or Serena `list_dir` |
| "Edit this method's body." | Serena `replace_symbol_body` (NOT built-in Edit, which Serena will refuse after a Serena read) |
| "Edit a few lines inside a method." | Serena `replace_content` (regex/string replacement) |
| "Insert a new top-level function." | Serena `insert_after_symbol` / `insert_before_symbol` |
| "Rename a symbol everywhere." | Serena `rename_symbol` |
| "Find all callers/usages of X (for refactor)." | Serena `find_referencing_symbols` (gives code snippets too) |

## Where each MCP shines in this repo
- **Codegraph** is especially valuable across `repos_cloned/` — 13+ libraries in 7 languages would be slow to grep. Always prefer it for "where is X in library Y" questions.
- **Serena** is the right tool when you actually need to *read or edit* a symbol body in `scripts/` or anywhere in the cloned repos, or to find references for a planned refactor.

## Things to remember
- Codegraph reads are sub-millisecond but the file watcher lags writes by ~1s — if you just edited a file and a query looks stale, wait briefly or re-run.
- Serena's tool descriptions enforce: after a Serena read, the built-in `Edit` tool will be rejected; you must use Serena's symbolic editing tools (`replace_symbol_body`, `replace_content`, `insert_*_symbol`).
- Line numbers Serena returns are **0-based**. Built-in `Read` returns 1-based numbers. Don't mix.
- For a one-off targeted question, ~2–3 Codegraph calls usually suffice; avoid spawning sub-agents to do exploration that Codegraph already indexed.
