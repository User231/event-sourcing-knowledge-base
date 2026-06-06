# Version Control Systems as Event Stores

> Git is event sourcing where the event store is a DAG, not a log.

A commit is an immutable, content-addressed event referencing its parent(s). A branch is a moving pointer into that DAG. A merge is a commit with two parents. A rebase rewrites history — which classical ES forbids — and it works in Git precisely because content addressing means the rebased commits are **new objects**, not edits to old ones. The old objects persist; what changed is which ref points where.

This doc is for ES practitioners who already know Git. It uses Git, Mercurial, SVN, Fossil, Jujutsu (jj), Pijul, Sapling/Mononoke, Darcs, and Perforce as a comparative lens on three questions classical ES doesn't answer well:

- What if your aggregate's history is not totally ordered?
- What if you need to merge two divergent histories of the same aggregate?
- What if "rebasing" an aggregate — emitting a new derived history that supersedes the old — were a legitimate operation?

For where this sits in the broader taxonomy, see [archetype E in unbounded-and-infinite-streams.md](../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories).

## 1. The basic mapping and aggregate boundaries

| ES concept | Git equivalent | Notes |
| --- | --- | --- |
| **Event** | Commit object | Immutable, content-addressed, references parent(s). New parents → new SHA → new event. |
| **Event payload** | Tree + commit metadata | The tree is *state at this event*, not a diff — Git stores snapshots, not patches. |
| **Aggregate root pointer** | Ref (`refs/heads/main`, tags) | Mutable pointer into the immutable DAG. |
| **Expected version** | The ref's current SHA | `git push` is literally CAS on a ref. See §6. |
| **Event log of operations** | Reflog (`.git/logs/...`) | *Secondary* append-only log of ref movements; the object DB itself is unordered. |
| **Projection / read model** | Checked-out working tree | Materialised state derived from a commit's tree. |
| **Snapshot** | Packfile | Many objects compressed into one delta-encoded archive — see §7. |
| **Idempotency key** | The content hash itself | Re-applying an identical change produces the same SHA. The store deduplicates structurally. |
| **Aggregate** | (Repository, ref) pair | Two refs share storage; no duplication. |
| **Uncommitted events** | Working tree + `.git/index` | See [uncommitted-events.md](../../implementation-patterns/uncommitted-events.md). |

The mental shift: in classical ES, **stream identity** is given (`account-{id}`) and **event identity** is its position. In Git, **event identity** is the content hash and **stream identity** is just a mutable label pointing into the DAG. Refs are cheap; events are expensive (immutable, deduplicated) — opposite weight distribution from a per-aggregate log.

The closest analogue to a classical ES *aggregate* is the **(repository, ref)** pair. Two consequences: the aggregate's history is the set of commits **reachable from the ref**, not a totally ordered list (`git log` linearises for display, but a merge gives the history parallel ancestors); and two aggregates (refs) **share storage** — `feature-x` and `main` share every commit before their fork point. The "stream-per-aggregate" intuition would duplicate; Git deduplicates structurally because events are content-addressed.

Fossil makes this most overt: a Fossil repository is literally a SQLite file containing an immutable timeline of "artifacts" — commits, wiki edits, tickets, forum posts ([Fossil concepts](https://fossil-scm.org/home/doc/trunk/www/concepts.wiki)). Tickets are *just another event type* in the same store — the most explicit "VCS as event store" design in production.

## 2. Stream-id naming if you modelled a VCS in classical ES terms

```
repo-{repoId}                          # repository-level events (creation, perms, archive)
repo-{repoId}-refs                     # every ref move (mirrors the reflog)
branch-{repoId}-{branchName}           # one stream per branch (derived from refs stream)
commit-{commitSha}                     # one stream per commit (content-addressed)
tree-{treeSha} / blob-{blobSha}        # ditto for trees and blobs
op-{repoId}                            # operation log á la Jujutsu — every action, including undos
```

`commit-{sha}` is **content-addressed**, not auto-incremented: same input → same stream-id → already exists → idempotent insert. Rare in classical ES, where stream-ids are usually surrogate UUIDs. `branch-{repoId}-{branchName}` is the natural "aggregate stream" but is **derived** from the refs stream: move the ref → the branch's history changes without appending or removing any event. Closer to a *materialised query* than a stream. `op-{repoId}` is Jujutsu's contribution — an audit log *of* the event store rather than the event store itself ([jj op log docs](https://jj-vcs.github.io/jj/latest/operation-log/)).

Sapling/Mononoke push further: the server-side store doesn't ship the whole DAG; clients fetch on demand. Streams materialise lazily at each consumer ([Sapling overview](https://sapling-scm.com/docs/scale/overview/)).

## 3. DAG vs log — why merge commits break the linear stream model

Classical ES streams are totally ordered. Optimistic concurrency hangs off this: `expectedVersion = N` is comparable, monotonic. In Git, the history of a ref is a **DAG**. A merge commit has two parents. There's no global "position 47" — there's a partial order over commits induced by the parent relation.

- **Vector-clock-shaped concurrency.** Two branches diverging from a common ancestor are concurrent in the Lamport sense. The merge commit names both parents explicitly, encoding the resolution. Same problem as [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md), different vocabulary.
- **`git log` is a topological linearisation.** `--first-parent`, `--date-order`, `--topo-order` show different valid orderings.
- **"Stream version" stops being a scalar.** The closest analogue is `expectedSha` — a content-hash CAS.

Classical ES assumes a **chain**; Git is a **DAG that projects to a chain only when you pick a refinement**. Mercurial, Fossil, Sapling, jj share the DAG model. SVN and Perforce are exceptions — strictly linear with globally-numbered revisions/changelists. Linearity is what makes Perforce's "submit number" globally meaningful; the DAG is what makes distributed development work.

## 4. Patches that commute — Pijul, Darcs, and the CRDT view of VCS

[Pijul](https://pijul.org/) and [Darcs](https://darcs.net/) take the opposite stance from Git: a commit is **a patch**, not a snapshot, and patches can be reordered when they don't depend on each other. Pijul's docs are explicit:

> Pijul implements a conflict-free replicated datatype (CRDT): indeed, we're just adding vertices and edges to a graph, or mapping edge labels which we know exist because of dependencies. — [Pijul model](https://pijul.org/model/)

In the vocabulary of [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md):

| VCS family | Strategy | Conflict primitive | Order sensitivity |
| --- | --- | --- | --- |
| Git / Mercurial / Sapling / Fossil | **Snapshot + 3-way merge** | Merge commit with two parents; `<<<<<<<` markers | Ancestry matters; non-fast-forward requires explicit merge |
| Pijul | **Commutative patches (CRDT)** | A patch is a set of graph edits; independent patches commute | Clones with the same patch set converge regardless of arrival order |
| Darcs | **Patch theory with commutation** | Patches have identity, context, effect; conflicts surface as "merger" patches | Reorderable when independent |
| Jujutsu | Snapshot + 3-way merge, **conflicts as first-class objects** | A commit may carry an unresolved conflict and still propagate | Order matters; conflicts can persist across rebases |
| SVN | Linear, last-writer-wins-at-rebase | Working-copy merge | Strictly linear repository revisions |
| Perforce | Linear, server-arbitrated | Pre-submit merge required | Strictly linear changelist numbers |

The ES lesson from Pijul/Darcs is the one collaborative-text editors learned years ago: **if your events are commutative, merge becomes trivial.** `BalanceIncremented{amount: 10}` and `BalanceIncremented{amount: 5}` commute; `BalanceSet{value: 100}` events do not. The work of "is this domain commutative?" determines whether you can have a CRDT-style event store ([Local-first software, Ink & Switch](https://www.inkandswitch.com/local-first/)).

The wrinkle: patches commute **under conditions** — `add-line-3` depends on `add-file-foo`. The dependency model is part of the data. Same problem as [spreadsheets.md §4](spreadsheets.md#4-cross-aggregate-processes--the-formula-dependency-graph).

## 5. History rewriting — what classical ES forbids

Classical ES is dogmatic: events are immutable; you never edit history. Git's `rebase`, `squash`, `amend`, `filter-branch`, `git replace`, [BFG](https://rtyley.github.io/bfg-repo-cleaner/) all rewrite history. So how is Git not violating the rule? It isn't — the trick is indirection:

- The **objects** are immutable. Once written, the content hash is identity; nothing edits them.
- The **refs** are not immutable; they're just pointers.
- A "rebase" creates *new* commit objects with new SHAs and moves the ref. Old commits become unreachable (orphaned) but persist until GC (§7).

In ES terms: **a rebase is a saga that emits a new derived aggregate** plus a ref update. The original aggregate's stream is untouched. After GC, orphaned commits are truncated — exactly the "snapshot + drop old events" pattern, except the snapshot is a forward replay onto a new base.

| Git operation | ES analogue |
| --- | --- |
| `git commit --amend` | Append a corrected event chain; update ref. Old commit becomes unreachable. |
| `git rebase --onto` | Replay events onto a different base; emit a new chain. Original stays in store. |
| `git rebase -i` (squash, fixup) | Compaction — collapse N events into 1. Same shape as Kafka log compaction or closing-the-books summary events. |
| `git filter-repo` | Mass rewrite — re-derive history with a transformation. The "redact PII while keeping audit" pattern. |
| `git replace` | Aliasing: substitute commit A for B at projection time without rewriting either. A view that lies about the underlying log. |

**Jujutsu's contribution.** Because jj records every operation in its [operation log](https://jj-vcs.github.io/jj/latest/operation-log/), rebase is just another op-log entry. You can `jj undo` it, revisit prior states with `jj op restore`. The rewriting is itself event-sourced:

> jj undoes the last operation. This is similar to git reset, but jj's operation log gives it a clean undo for almost every operation, including complex ones like rebase. — [jj-vcs README](https://github.com/jj-vcs/jj)

jj has *two* event stores stacked: the immutable Git object DB underneath, and the immutable operation log on top. User-facing "undo" lives in the second layer; the first never mutates. The pattern ES can borrow: **if you need rewriting semantics, don't mutate the event log — add a higher-level event log of operations on the event log.** The reflog is Git's primitive version; jj's op-log is the principled version.

## 6. Optimistic concurrency in Git — `push` is compare-and-swap on a ref

The cleanest analogy in the doc. From [git-push docs](https://git-scm.com/docs/git-push):

> `--force-with-lease=<refname>:<expect>` protects all remote refs by requiring their current value to be the same as <expect>.

`--force-with-lease=refs/heads/main:abc123` is *literally* "set `refs/heads/main` from `abc123` to my new SHA, atomically; fail if it's not at `abc123`". That is the textbook `expectedVersion` pattern from [implementation-patterns/optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md), with the version as a content hash rather than an integer.

What this gets you that integer versions don't:

- **The version is also the content.** Two versions can be compared without a central authority. No ABA problem — the hash includes the parent chain.
- **Multi-aggregate atomic CAS.** `git push --atomic` updates several refs as one operation ([Git 2.4 release notes](https://github.blog/open-source/git/git-2-4-atomic-pushes-push-to-deploy-and-more/)) — "all these refs go from their expected SHAs to these new SHAs, or none of them move." Classical ES rarely supports this; Git treats it as table stakes.
- **Idempotent retry.** Re-pushing the same commit content produces the same SHA — the operation is hash-keyed at every layer.

What this *doesn't* give you: a monotonic per-aggregate event count. You can't say "this branch has 47 events" meaningfully in a DAG. Sapling/Mononoke's globalrevs reintroduce a monotonic per-server commit number specifically for tooling that wants one.

## 7. Garbage collection and packfiles — Git as a compactable event store

Git's object DB starts as "loose" objects — one file per SHA. As it grows it compacts into packfiles ([Pro Git §10.4](https://git-scm.com/book/en/v2/Git-Internals-Packfiles)). Two compaction stories mapping onto two ES patterns:

- **Packfiles** are delta compression of immutable objects. Equivalent: storing N events as a single compressed segment (EventStoreDB chunks, Kafka segment files). Events remain logically separate; storage is shared.
- **`git gc --prune`** removes objects unreachable from any ref *and* older than the grace period. Equivalent: dropping events past a retention window when no projection or pointer can reach them. Genuinely lossy.

The interesting wrinkle: **Git's reachability gives it free retention semantics.** A commit survives as long as some pointer (ref, tag, reflog entry, transitive ancestor) can reach it. The reflog's expiry (default 90 days) is what eventually lets orphaned commits disappear. Classical ES has no reachability concept; retention is an explicit per-stream policy.

Sapling/Mononoke take this further with **bonsai changesets** (internal commit representation independent of Git/Mercurial wire format) plus **derived data** projections (file history, blame) computed on demand and cached ([Mononoke README](https://github.com/facebook/sapling/blob/main/eden/mononoke/README.md)). The aggregate identity (commit) is canonical; projections are recomputable and disposable — the snapshot-vs-event-log split a mature ES system enforces.

## 8. Conflict resolution, submodules, and monorepos

Every snapshot-based VCS uses **3-way merge**: find the common ancestor `A`, compute diffs `A→B` and `A→C`, apply both to `A`, surface anything irreconcilable as textual conflict. The ES analogue:

```
Replicas X and Y diverged from common state S0.
X applied [e1, e2] → S_X.  Y applied [f1, f2, f3] → S_Y.

3-way merge over events:
  1. Find common ancestor S0 (last common event in the event DAG).
  2. Replay X's new events on Y → check for invariant violations.
  3. On conflict: surface as a Conflict event → escalate to a human or policy.
  4. Emit a Merge event with two parents, encoding the chosen resolution.
```

What snapshot VCSs lose that patch-theory VCSs don't: a 3-way merge in Git is based on **content** at the three points, not on the operations that produced them. If two sequences ended at the same content, the merge can't tell them apart. Darcs and Pijul *can* — they retain patch identities. The classical OT/CRDT divide ([collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md)) playing out at the VCS layer. Jujutsu's **first-class conflicts** are the pragmatic middle: a commit may carry an unresolved conflict and still propagate — in ES terms, an event carrying "unresolved" state forward (a quasi-CRDT *pending* event) with resolution as a separate later event. Most ES systems insist an event represents a *resolved* fact; jj relaxes that.

**Submodules ([Pro Git §7.11](https://git-scm.com/book/en/v2/Git-Tools-Submodules)) are aggregates that contain aggregates.** The parent's tree stores a SHA pointing into the child's object DB. Parent events reference specific child versions — like "an order references customer at customer-version-12". Updating the child does not automatically update the parent: cross-aggregate consistency is **explicit and eventual**, and per-aggregate optimistic concurrency of the child doesn't compose into a transactional update of the parent. Same problem as multi-aggregate sagas in [multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md).

Google's and Meta's monorepos take the opposite stance: there is **one aggregate** at scale, and the consistency primitive is the whole-tree commit. Mononoke is the server-side store that scales this; EdenFS gives virtual checkouts so clients don't materialise the whole tree ([Sapling overview](https://sapling-scm.com/docs/scale/overview/)). Trade-off: every commit is a global event; per-team write contention forces queueing. Same trade-off as banking's one giant ledger stream vs. per-account streams — see [banking-and-finance.md §5](banking-and-finance.md#5-double-entry-ledger-treatment).

## 9. Lessons ES can borrow from Git

- **Content-addressed events.** Event identity = `hash(payload + parentId)`. Duplicate writes collapse for free; the store deduplicates structurally. IPFS and Mononoke do this. Replaces per-stream idempotency-key mechanics with a property of the storage layer.
- **An op-log on top of the event log** (Jujutsu). Every command/saga emission becomes an entry in a parallel operation log. Clean audit-of-actions layer that doesn't pollute the domain log; gives "undo" sensible system-level meaning.
- **Branch-as-tentative-history for what-if scenarios.** A branch is a cheap, named alternative future. ES analogue: the [uncommitted-events pattern](../../implementation-patterns/uncommitted-events.md) raised to a first-class artifact — a *named* uncommitted event chain you can hand off, review, and either merge or discard. Useful for scenario modelling: "what would year-end look like if these draft journal entries posted?"
- **Tags as named signed immutable checkpoints.** Most ES systems have snapshots; few have *named, signed* ones as first-class citizens.
- **GC by reachability rather than retention policy.** Track references that need to reach an event; let events go when nothing reaches them. Survives changes in projection requirements better than "drop events older than N years".
- **Refs as cheap aggregate aliases.** Cheap mutable pointers into an immutable DAG let you model "the official customer view of this order" and "the support team's view" as separate aggregates sharing storage.

## 10. What Git does that classical ES forbids

| Git practice | Rule violated | Why Git gets away with it |
| --- | --- | --- |
| **`git rebase`** | "Never rewrite history" | Rewritten commits are *new objects*; old ones remain until GC. Aggregate identity (the ref) is rebound; underlying events are not edited. |
| **`git push --force`** | "Don't bypass optimistic-concurrency rejection" | Force-push *is* a CAS — one that always succeeds. Permitted but socially policed (protected branches, hooks). |
| **`git gc --prune`** | "Never delete events" | Only unreachable events, only after a grace period. The dropped events are objects no aggregate can reach. |
| **`git replace`** | "An event has one canonical identity" | Replacement is a *projection-time* alias; original is still in the store. |
| **`git filter-repo`** | "Mass history rewrites are forbidden" | Used to redact secrets, GDPR PII, strip large binaries. Equivalent to ES's crypto-shredding. |
| **Reflog auto-expiry (90d)** | "Audit log retention is forever" | Reflog is *local* audit only; immutable commits remain in the object DB or on a remote. |
| **First-class conflict commits (jj)** | "An event represents a resolved fact" | The conflict *is* the fact; resolution is a later commit. |

The pattern: Git is comfortable with deletion *of unreachable derived data* and rewriting *via creation of new immutable objects*. It is uncomfortable with mutation of an existing object — content addressing makes that impossible. Classical ES forbids deletion but allows mutation of projections. The two draw the immutability line in different places.

## 11. Gotchas

- **Shallow clones (`--depth=N`)** truncate history at the client. The aggregate locally has no events older than depth N. The "stream is logically infinite but locally bounded" pattern.
- **Partial clones (`--filter=blob:none`)** materialise commits without their tree contents until needed. State projections load lazily. Used heavily by Mononoke clients and monorepo workflows.
- **Git LFS / VFS for Git** keep large blobs out of the main object DB. ES view: "event payload too large; store external reference, resolve on read." Pitfall: the external store has different retention from Git; the two can drift.
- **Ref divergence across remotes (multi-master)** is the everyday case. Two clones both have `refs/heads/main` pointing at different SHAs after offline work. No global truth; convention says one remote is canonical but Git doesn't enforce. The merge-semantics problem of [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md), every `git pull`.
- **`git replace` is invisible.** Silently substitutes commits at projection time, with no in-history record. Audit story relies on tooling outside Git itself.
- **`pre-receive` hook rejections.** The server can reject pushes for arbitrary policy reasons. An event-store-layer invariant rejection rather than aggregate-layer.
- **Detached HEAD** is editing the aggregate without a named pointer pointing at it. Commits exist in the object DB but no ref reaches them; immediately GC-eligible. ES analogue: appending events to a stream-id you forgot to register.
- **`git fsck`** walks the DAG and validates parent chains, blob references, signatures. ES analogue: schema/integrity checks across a long event log. Most ES systems have nothing as thorough.
- **Force-push to a published branch destroys collaborators' local work.** They had the old SHA; the new ref points elsewhere; their local commits are unreachable from `origin/main`. Recovery: the local reflog. Lesson: **destructive operations on shared aggregates need explicit consent** — Git's protected branches are the social-engineering layer that makes the technical CAS sane.
- **Submodule pointer staleness.** Parent pinned child at SHA `X`; that SHA was force-pushed away on the child remote; parent points at a no-longer-fetchable commit. Pure cross-aggregate consistency-rot.

## 12. Where Git is used *as* an event store in production

- **Dolt — Git for SQL data** ([dolthub/dolt](https://github.com/dolthub/dolt)). A relational database where commits version tables instead of files. `dolt branch`, `dolt merge`, `dolt diff` between database states. Event store = Git-like object DB; projection = materialised SQL view. Schema migrations are commits; data corrections are commits; bisecting a regression in a financial report becomes literal `git bisect`. Doltgres extends to PostgreSQL semantics.
- **GitOps (Flux, ArgoCD)** — the cluster's desired state lives in a Git repo; the operator reconciles actual against desired. Every change is a commit; every rollback is `git revert` (a new commit, not a mutation). Git history *is* the audit log for production changes. ArgoCD's application-event stream is a secondary projection; Git is the source of truth ([Flux concepts](https://fluxcd.io/flux/concepts/), [ArgoCD docs](https://argo-cd.readthedocs.io/)).
- **Fossil-as-issue-tracker** — Fossil's "artifacts" include tickets, wiki edits, and forum posts in the same append-only timeline as commits. A single event store for code + project metadata.
- **NixOS / Guix** — system configuration is content-addressed via Nix store paths; rebuilds project an aggregate at a new revision. Not Git directly, same content-addressed event-store philosophy.
- **etcd / Consul KV with audit log** — revision-numbered KV store where every revision is an event; you can read state at any revision. Closer to classical ES (linear revisions, single-master) than Git.
- **`pass` (unix password manager)** — a Git repo of GPG-encrypted files. Every credential change is a commit; audit log is Git history; rollback is a checkout. ES with a CLI.
- **Static-site generators with Git-backed content** (Hugo + Decap CMS, Jekyll on GitHub Pages) — content edits are commits; projection is the generated site. The cleanest "small-scale ES with no infrastructure" recipe.
- **IPFS / IPLD** generalises Git's content-addressed object DB to a global peer-to-peer object store. Filecoin commits IPFS roots to a blockchain — see sibling [smart-contracts-and-blockchain.md](smart-contracts-and-blockchain.md) for the same DAG-like ledger pattern.

Dolt is the most direct claim: it event-sources a SQL database using Git's data model, and operational DBA tasks (audit, rollback, diff, branching for what-if) become natural rather than bolted-on. That's the whole pitch for ES at the application layer, transplanted to the data layer.

## 13. Sources

**Core internals** — *Pro Git*, Chacon & Straub: [Git Internals](https://git-scm.com/book/en/v2/Git-Internals-Git-Objects), [Packfiles](https://git-scm.com/book/en/v2/Git-Internals-Packfiles), [Maintenance and Data Recovery](https://git-scm.com/book/en/v2/Git-Internals-Maintenance-and-Data-Recovery). [git-push](https://git-scm.com/docs/git-push); [Git 2.4 — atomic pushes](https://github.blog/open-source/git/git-2-4-atomic-pushes-push-to-deploy-and-more/). Linus Torvalds — [Git Tech Talk (Google 2007)](https://www.youtube.com/watch?v=4XpnKHJAok8).

**Sapling / Mononoke / EdenFS** — [Sapling docs](https://sapling-scm.com/docs/introduction/); [Sapling on GitHub](https://github.com/facebook/sapling); [Mononoke README](https://github.com/facebook/sapling/blob/main/eden/mononoke/README.md); [LWN — Meta's Sapling system](https://lwn.net/Articles/915104/).

**Jujutsu (jj)** — [jj-vcs/jj](https://github.com/jj-vcs/jj); [Operation log](https://jj-vcs.github.io/jj/latest/operation-log/); [Martin von Zweigbergk interview](https://zencastr.com/z/ubwYpb-f).

**Pijul / Darcs (patch theory)** — [Pijul theory](https://pijul.org/manual/theory.html); [Pijul model](https://pijul.org/model/); [A Categorical Theory of Patches — Mimram & Di Giusto](https://arxiv.org/pdf/1311.3903); [Darcs Theory of Patches — Roundy](https://www.cs.tufts.edu/~nr/cs257/archive/david-roundy/Theory%20of%20patches.html); [Wikibook on Darcs patch theory](https://en.wikibooks.org/wiki/Understanding_Darcs/Patch_theory).

**Fossil / Perforce / VFS for Git** — [Fossil concepts](https://fossil-scm.org/home/doc/trunk/www/concepts.wiki); [Thoughts on the Design of Fossil (R. Hipp)](https://fossil-scm.org/home/doc/trunk/www/theory1.wiki); [Perforce architecture](https://www.perforce.com/manuals/p4sag/); [Microsoft VFS for Git](https://github.com/microsoft/VFSForGit).

**Git as event store in production** — [DoltHub — Git for Data](https://docs.dolthub.com/introduction/getting-started/git-for-data); [Flux GitOps Toolkit](https://fluxcd.io/flux/concepts/); [ArgoCD docs](https://argo-cd.readthedocs.io/); [pass](https://www.passwordstore.org/); [Consul KV revisions](https://developer.hashicorp.com/consul/docs/dynamic-app-config/kv).

**CRDTs & merge theory** — [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md); [Local-first software, Ink & Switch](https://www.inkandswitch.com/local-first/).

**Adjacent docs** — [unbounded-and-infinite-streams.md §E](../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories); [smart-contracts-and-blockchain.md](smart-contracts-and-blockchain.md); [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md); [optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md); [uncommitted-events.md](../../implementation-patterns/uncommitted-events.md).
