# Collaborative Editing — OT vs CRDT vs LWW

Three strategies for "what happens when two users make concurrent edits to the same document?". They show up wherever multiple writers touch shared state without a single serialising lock: collaborative documents, chat history merge, distributed databases, offline-first apps, multiplayer games.

Listed roughly in order of complexity and power: **LWW** (last-write-wins), **OT** (operational transform), **CRDT** (conflict-free replicated data type).

## LWW — Last-Write-Wins

The simplest strategy. When two writes to the same field arrive, the later one (by some ordering — usually the server's receive order, sometimes a Lamport timestamp) replaces the earlier one. The earlier write is discarded.

```
T=0  Alice sets cell A1 = "Hello"     (sent to server)
T=1  Bob sets cell A1 = "Hi"          (sent to server)
T=2  Server receives Alice's write    -> A1 = "Hello"
T=3  Server receives Bob's write      -> A1 = "Hi"    (Alice's value lost)
```

**Granularity matters.** "Whole document LWW" is useless — Alice editing cell A1 would clobber Bob's edit to Z99. Real systems do **per-property LWW**: each (object, property) is its own conflict unit.

> Two clients changing unrelated properties on the same object won't conflict, and two clients changing the same property on unrelated objects also won't conflict. A conflict happens when two clients change the same property on the same object.
> — Figma, [How multiplayer technology works](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/)

**Used by**: Figma (almost everything), Notion ([explicit about this](https://news.ycombinator.com/item?id=37767739) — most blocks are LWW; CRDTs only for rich text), most non-Sheets/Excel spreadsheet tools at cell granularity, Cassandra and DynamoDB at the cell/column level.

**Where it fails**: rich text. If Alice types "AB" and Bob types "BC" at the same paragraph at the same time, LWW gives you `"AB"` or `"BC"`, never `"ABC"`. Each user's letters were a distinct intent that needed to merge. LWW doesn't merge — it picks.

## OT — Operational Transform

When two operations from different clients touch overlapping state, **transform one of them so it makes sense after the other was applied**. Both operations end up applied, both intents preserved, all clients converge to the same state regardless of arrival order.

```
Initial state: "ABC"

Alice does: insert(pos=0, "X")    -> local state "XABC"
Bob   does: insert(pos=3, "Y")    -> local state "ABCY"

Both ops broadcast. Each client applies the other's op after transforming it
against the ops it has already applied locally:

Alice's view applies Bob's op:
   Alice's local state is "XABC" (length 4)
   Bob's pos=3 is still correct because Alice's insert was at pos=0
   -> "XABCY"

Bob's view applies Alice's op:
   Bob's local state is "ABCY"
   Alice's pos=0 stays at the start
   -> "XABCY"

Both converge.
```

The hard part: for *every pair* of operation types you need a `transform(op1, op2)` function such that applying `op1` then `transform(op2, op1)` ends in the same state as applying `op2` then `transform(op1, op2)` (the **TP1 property**). The number of pairs grows quadratically with operation types — `insert × insert`, `insert × delete`, `delete × delete`, `format × format`, `format × insert` … Implementing transform functions correctly is famously fiddly — the academic literature has many published OT algorithms that turned out to have edge-case bugs.

**Used by**: Google Docs, Google Sheets, Google Wave (where the modern OT story started — [Wave whitepaper](https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html)), Excel Online, EtherCalc (simpler — no transform needed because operations are serialised through one worker per room), ShareDB, OnlyOffice.

**Why it's used for rich text**: preserves both users' character-level intents.

**Tradeoffs**: requires a central server to assign canonical operation order (the **Jupiter algorithm** — clients send ops to server, server transforms and rebroadcasts). Truly peer-to-peer OT is much harder.

## CRDT — Conflict-free Replicated Data Type

Data structures whose merge function is mathematically guaranteed to converge regardless of operation order, without needing transforms or a central server. Each operation produces a state that can be merged with any other state, deterministically.

```
A character in a sequence CRDT doesn't have a position 3 — it has a unique
identifier (often a fractional index between its neighbors, or a path in a
tree, or a Lamport-stamped pair). Insertions add new identifiers; deletes
tombstone them.

Alice inserts X with id=(1.5, alice)  between chars at 1 and 2
Bob   inserts Y with id=(1.7, bob)    between chars at 1 and 2

When merged, both identifiers exist. The total order over (fractional, peerId)
is well-defined, so both clients see X before Y (or vice versa) deterministically.

There's no "transform" — the identifiers themselves carry the information needed
to place each character relative to every other character.
```

Two big families:
- **State-based (CvRDTs)**: each replica holds full state; merging two states uses a join function (a lattice meet/join). Heavy but conceptually simple.
- **Operation-based (CmRDTs)**: replicas exchange operations; operations must be commutative.

**Used by**: Yjs, Automerge, Y-CRDT, Riak, Apple Notes (between devices), iCloud, Figma's *text-inside-a-shape* (Figma uses LWW elsewhere but CRDT for rich text). The [Eg-walker paper](https://arxiv.org/pdf/2409.14252) shows newer CRDTs competitive with OT on performance.

**Where it shines**: peer-to-peer / local-first apps. No central server needed. Offline edits merge cleanly when devices reconnect — this is why Automerge powers a lot of the local-first movement.

**Tradeoffs for grid-shaped documents (e.g., spreadsheets)**: bad fit. CRDTs assume the position-of-a-thing is part of the thing's identity. But in spreadsheets, **formulas reference positions** — `=A1+B1` cares that A1 is at column 1 row 1. Insert a row above A1 and the formula must shift. That's structural rewriting of references, which doesn't fit CRDT merge semantics. See [spreadsheets.md §5](../domains/spreadsheets.md) for the full discussion.

## When each is the right choice

| Approach | Right for | Wrong for |
|---|---|---|
| **LWW** | Object-graph documents (Figma, Notion blocks), per-cell spreadsheet values, settings, anything where "whose write wins" is acceptable | Rich text; any case where two simultaneous writes both convey real information that needs to merge |
| **OT** | Rich text, ordered sequences, grid-mutation streams in spreadsheets — anywhere a central server can assign canonical order and intent-preservation matters | Peer-to-peer / offline-first with no server arbiter |
| **CRDT** | Local-first / offline-first / peer-to-peer apps; distributed databases needing eventual consistency without a coordinator | Spreadsheet grids with formula references; situations where bandwidth/memory overhead of CRDT metadata is unacceptable; cases where simple "whose write wins" is the desired semantic |

## Relationship to event sourcing

All three strategies are about **how concurrent writes converge**. Event sourcing is about **how state is derived from a log of writes**. They're orthogonal — every collab system is some combination:

- An ES system can use LWW per (aggregate, field): the events are still appended, but a projection picks the last-by-timestamp.
- OT systems append operations to a log (effectively an event store) and replay them deterministically — Google Wave / Sheets are recognisably event-sourced under the hood, with the transform step happening at apply time.
- CRDT systems are event-sourced by nature: every operation is an immutable event, the merge function is the projection.

The choice matters most where the **event itself** needs to encode merge intent. A `CellSet{cell: A1, value: "Hello", at: T}` event with LWW is trivial — projection takes the max-timestamp. A `TextInsert{pos: 3, char: "X"}` event needs OT or CRDT semantics baked into how the event is interpreted, because `pos: 3` only makes sense relative to some prior state.

## Common pitfalls

- **Mistaking LWW for "no merging".** LWW *does* merge — at the property level. Whole-object LWW is what's useless. Always specify granularity.
- **Reaching for CRDTs because they sound principled.** Most teams don't have a peer-to-peer / offline-first requirement. LWW + a central server is simpler and matches user mental models for object-graph documents (this is Figma's argument).
- **Mixing OT and CRDT in one system without care.** They make different assumptions about operation identity and ordering; bridging them at the protocol level requires real work.
- **Choosing the merge strategy before knowing the data shape.** Rich text needs OT or CRDT. Object graphs work well with LWW. Spreadsheet grids with formula references need OT (with explicit reference-rewriting on structural ops) or you give up on collaborative structural changes.
- **Underestimating the implementation cost of OT.** "Just transform operations" hides a quadratic explosion of operation-pair transform functions and an academic literature full of edge cases. Reach for a battle-tested library (ShareDB, Y-OT) rather than rolling your own.

## Where these show up in this knowledge base

- [domains/spreadsheets.md](../domains/spreadsheets.md) — §5 covers OT/CRDT/LWW choice for the grid-as-document, row-as-record, and dimensional stances. The most thorough domain treatment.
- [domains/unbounded-and-infinite-streams.md §A](../domains/unbounded-and-infinite-streams.md#a-collaborative-documents--every-keystrokeoperation-is-an-event) — collaborative documents as an archetype where classical ES doesn't fit and CRDTs/OT take over.

## Foundational references

- Evan Wallace — [How Figma's multiplayer technology works](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/). The clearest "why per-property LWW beats OT/CRDT for object graphs" writeup.
- Google Wave OT whitepaper — [operational-transform.html](https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html). The canonical statement of the Jupiter algorithm and TP1.
- David Nichols et al. — [High-latency, low-bandwidth windowing in the Jupiter collaboration system](https://dl.acm.org/doi/10.1145/215585.215706). The Jupiter paper that Wave / Docs / Sheets generalised.
- Joseph Gentle — [reference-crdts](https://github.com/josephg/reference-crdts). Minimal spec-compliant Yjs/Automerge sequence implementations; useful to see exactly what assumptions sequence CRDTs make.
- Martin Kleppmann et al. — [Local-first software](https://www.inkandswitch.com/local-first/). The case for CRDTs and peer-to-peer over central-server collaboration.
- Eg-walker — [Collaborative Text Editing: Better, Faster, Smaller](https://arxiv.org/pdf/2409.14252). Newer CRDT performance competitive with OT.
- [Concurrent Undo Operations in Collaborative Environments via OT (Springer)](https://link.springer.com/chapter/10.1007/978-3-540-30468-5_12). Undo in collab systems — surprisingly subtle.
- [crdt.tech](https://crdt.tech/) — index of CRDT implementations and papers.
- [Yjs docs](https://docs.yjs.dev/) and [Automerge](https://automerge.org/) — the two most widely used CRDT libraries.
- [ShareDB](https://github.com/share/sharedb) — canonical open-source OT library (JSON0 operations).
