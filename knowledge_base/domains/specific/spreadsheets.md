# Spreadsheets — Aggregate & Stream Decomposition

What's distinctive about spreadsheets is that the "domain model" is *also* a programming environment: every cell can be a formula referencing other cells, and changing one cell ripples through a dependency graph that the system itself must maintain. Layer real-time multi-user editing on top and the textbook ES patterns (one stream per aggregate, optimistic concurrency, deterministic replay) collide with three forces simultaneously: an [unbounded edit history](../unbounded-and-infinite-streams.md), [concurrent operations](../unbounded-and-infinite-streams.md#a-collaborative-documents--every-keystrokeoperation-is-an-event) that must commute or be transformed, and a recomputation engine whose outputs must be reproducible from the same inputs.

This doc surveys what Google Sheets, Excel Online, Airtable, Smartsheet, Notion, Quip, EtherCalc, Coda, Rows, Causal, OnlyOffice, Collabora, and the relevant libraries (HyperFormula, SpreadJS, ShareDB) actually do. Names where known; tradeoffs explicit.

## 1. Aggregate boundaries used in practice

Two fundamentally different modeling stances dominate, and a third hybrid is emerging.


| Stance                     | Aggregate                                | Representative systems                                                    | Why                                                                                                                                                                                    |
| -------------------------- | ---------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Grid-as-document**       | Workbook (whole document)                | Excel Online, Google Sheets, EtherCalc, OnlyOffice, Collabora, SocialCalc | The grid is one object; cells exist by position; structural changes (row insert) mutate every reference. Concurrency handled by OT/LWW *inside* the aggregate, not by aggregate split. |
| **Row-as-record**          | Row / record (one per data row)          | Airtable, Smartsheet, Notion DBs, Coda                                    | Rows are first-class records with stable IDs. Position is a property, not identity. Cells are *fields* of the row record. Closer to a database than a grid.                            |
| **Dimensional / variable** | Variable × dimensions (sparse N-D array) | Causal, Rows.com (partly), Quantrix, Anaplan                              | The "cell" is `Variable[Product=P0, Country=C1, Month=M3]` — addressed by named dimensions rather than `A1`. Formulas operate on whole variables.                                      |


### Grid-as-document

The workbook is the consistency boundary. Within it:

- The **sheet** is rarely an aggregate of its own — it's a subtree of the workbook. Structural events (`SheetRenamed`, `SheetMoved`) mutate workbook-level state because formulas in *other* sheets reference it by name.
- The **cell** is too fine-grained to be its own aggregate: a single `RowInserted` would have to coordinate with potentially thousands of cell aggregates whose A1 references shift ([Excel recalculation](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation) notes this rebuilds the dependency tree wholesale).
- **Ranges** are not aggregates at all; they're query results / views over the cell grid. Named ranges are aggregate-scoped metadata (see [§7 Named ranges](#named-ranges)).

Why the workbook wins: a formula in `Sheet2!B5` referencing `Sheet1!A1:A100` means the consistency boundary *must* contain both sheets. The dependency graph is global. Excel's "external references" (cross-workbook links) are notorious precisely because they cross the natural aggregate boundary ([Excel Dependencies, Decision Models](https://www.decisionmodels.com/calcsecretsd.htm)).

**Contention**: in OT systems (Sheets, EtherCalc) the workbook is the OT document and concurrency is handled by transforming operations against each other. In LWW systems (Figma-style; Notion for most properties) each (object, property) is its own contention unit *within* the document aggregate ([How Figma's multiplayer technology works](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/)).

### Row-as-record (Airtable model)

Airtable's [in-memory database rewrite](https://medium.com/airtable-eng/rewriting-our-database-in-rust-f64e37a482ef) makes this explicit:

> Each base gets a dedicated worker process. Data for a given base is read into memory and operated on by a dedicated server… The database provides serializable, atomic transactions backed by MVCC; clustered and secondary indexes… transactional DDL, foreign-key constraints, unique constraints, and triggers.

So Airtable's *base* (the workbook equivalent) is the deployment / process boundary, but the *aggregate* within it is the row. Crucially, Airtable rejected both OT and CRDTs in favor of **incremental view maintenance**: "it computes how a write impacts each live query without re-executing the query from scratch, and produces a compact diff." That's a projection-update pattern, not a write-side concurrency pattern.


| Boundary         | What lives at this level                                                 |
| ---------------- | ------------------------------------------------------------------------ |
| **Base**         | Process / worker; schema; permissions; aggregate of tables               |
| **Table**        | Schema (columns, types); secondary indexes                               |
| **Row (record)** | Identity, lifecycle (created → updated → deleted); the natural aggregate |
| **Cell (field)** | Property of the row; not a separate aggregate                            |
| **View**         | Projection (filter + sort + grouping); read model                        |


Notion is the same pattern at the block layer: every block is identified by UUID with parent pointers ([The data model behind Notion's flexibility](https://www.notion.com/blog/data-model-behind-notion)). "Notion doesn't use OT or CRDT in production. Most things are last-write-wins" ([HN comment from a Notion engineer](https://news.ycombinator.com/item?id=37767739)).

### Dimensional / variable

Causal's escape from the cell model: variables are typed and multi-dimensional ([Scaling Causal's Spreadsheet Engine, sirupsen.com/causal](https://sirupsen.com/causal)).

> `Sales[Product=P0][Country=C1]` maps to a linear array index. Cells went from 88 bytes (formula + dependencies + parent variable pointer) to 32 bytes by separating storage into parallel arrays (struct-of-arrays).

The aggregate is the **variable** (or "calc node"). Formulas operate on whole variables, not cells. This collapses the cardinality problem: a 1-billion-cell map of `map[int]*Cell` becomes `[]float64` and the dependency graph has nodes per variable, not per cell.

### Tradeoffs


| Concern                                             | Grid-as-document                                           | Row-as-record                                                                       | Dimensional                                                                |
| --------------------------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Concurrent edits to different cells in the same row | Both touch the same aggregate; OT transforms               | Both touch the same aggregate row; needs field-level LWW or merge                   | Touch the same variable; per-cell index merge                              |
| Row insert at position N                            | Reference rewriting cascade across whole workbook          | Just a position field; no formula rewrite (formulas reference fields not positions) | Position has no meaning; dimensions are unordered or independently ordered |
| 1M-row dataset                                      | Storage is the workbook's problem; sparse storage required | Each row a tiny aggregate; natural sharding                                         | Stored as packed arrays                                                    |
| Formula referencing "everything in column C"        | `SUM(C:C)` — special range handling                        | `SUM({Amount})` — field reference, immune to row inserts                            | `SUM(Sales)` — variable reference                                          |


Vaughn Vernon's [Effective Aggregate Design](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf) "one transactional consistency boundary per aggregate" works cleanly for the row model and the variable model. For the grid model the consistency boundary is *the whole document*; the systems compensate by partitioning concurrency below the aggregate (per-property in Figma, per-operation in OT systems).

## 2. Stream-id naming patterns

The naming question depends on which stance you took in §1.

### Grid-as-document (operation log keyed by document)

```
workbook-{workbookId}                          # the canonical document stream
workbook-{workbookId}-ops                      # raw OT operations (high-frequency)
workbook-{workbookId}-{yyyyMMdd}               # daily-bucketed sub-stream (Sheets-style)
workbook-{workbookId}-snapshot-{version}       # periodic snapshots for fast load
session-{sessionId}                            # per-client session for OT state-space
revision-{workbookId}-{revisionId}             # named version history entries
```

The **operations stream** carries low-level grid mutations (`SetCellValue`, `InsertRow`, `MergeCells`). The **revisions stream** is the user-visible "version history" — periodic merges of the op stream into named snapshots. Google Sheets' [version history](https://www.ablebits.com/office-addins-blog/google-sheets-edit-history/) explicitly states: "the revisions for the file may occasionally be merged to save storage space… Google Sheets may optimize the storage space by either merging some older versions or deleting some of the oldest changes." That's log-compaction on the operation stream.

EtherCalc takes the simplest possible form: per-room command relay, where the spreadsheet ID is the room and there's effectively one stream per workbook executed sequentially by a sandboxed worker ([From SocialCalc to EtherCalc](https://aosabook.org/en/posa/from-socialcalc-to-ethercalc.html)).

### Row-as-record (per-row streams, plus schema)

```
base-{baseId}                                  # schema/process aggregate
table-{baseId}-{tableId}                       # schema-level (column adds, type changes)
row-{baseId}-{tableId}-{rowId}                 # the natural aggregate
view-{baseId}-{viewId}                         # projection definition (saved filter/sort)
formula-{baseId}-{tableId}-{columnId}          # computed-column definition
```

Notion's blocks are addressed by UUID at the document layer: `block-{uuid}` is the natural stream, with parent pointers reconstructed from a separate projection (see "snapshot-plus-log pattern" — "A versioning and history service records operation streams and periodic snapshots for undo, audit, and recovery" — [Notion data model post](https://www.notion.com/blog/data-model-behind-notion)).

### Dimensional

```
variable-{modelId}-{variableId}                # one stream per variable definition
dimension-{modelId}-{dimensionId}              # named dimensions
model-{modelId}                                # the workbook equivalent
cell-{modelId}-{variableId}-{dimensionTuple}   # rarely materialised; usually transient
```

Cells aren't streams — they're materialised values of `Variable × Dimensions` computed by the engine. The event log is at the variable / formula level.

## 3. Key events per aggregate

Events split into three categories that real systems treat distinctly: **value events** (cell content changed), **structural events** (rows/columns/sheets moved), and **operational events** (raw OT ops, rarely promoted to the domain stream).

### Value-level

```
CellValueSet              { sheet, a1Ref, oldValue, newValue, dataType }
CellFormulaSet            { sheet, a1Ref, formulaText, formulaAst, dataType }
CellFormulaResultComputed { sheet, a1Ref, computedValue, calcVersion, dependencies[] }
CellCleared               { sheet, a1Ref }
CellFormatChanged         { sheet, a1Ref, formatPatch }    # color, number format, font
CellNoteAdded             { sheet, a1Ref, authorId, text }
CellCommentAdded          { sheet, a1Ref, threadId, authorId, text }
CellValidationSet         { sheet, a1Ref, rule }            # dropdowns, date validators
ConditionalFormatApplied  { sheet, range, ruleId, condition, format }
```

The **format-vs-value distinction** is load-bearing. They have entirely different replay semantics: a formatting change is idempotent and commutative (mostly); a value change is not. Most real systems separate them on the wire (the [SpreadJS collaboration protocol](https://developer.mescius.com/spreadjs/docs/spreadjs-collaboration-server/spreadjs-sheets-collaboration/spreadjs-sheets-collaboration-add-on) classifies commands; OpenXML stores them in separate parts).

Crucially, `CellFormulaResultComputed` is usually **not persisted as a domain event** in OT/LWW systems — the computed value is derivable from the formula plus its precedents, so it's a projection. Excel persists it for *load-time speed* (so you can open a file without recalc), not for history. See `[calcChain.xml](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-calculation-chain)`: "if Excel does not find calcChain.xml upon opening a file, it will recalculate the formulas and re-create the calcChain.xml file" — the cached calc chain is disposable.

### Structural

```
SheetCreated              { workbookId, sheetId, name, index, dimensions }
SheetRenamed              { sheetId, oldName, newName }    # forces formula reference update
SheetMoved                { sheetId, fromIndex, toIndex }
SheetDeleted              { sheetId }                       # leaves #REF! errors in dependents
RowInserted               { sheet, atRow, count }           # shifts every A1 ref below
RowDeleted                { sheet, atRow, count }
ColumnInserted            { sheet, atColumn, count }
ColumnDeleted             { sheet, atColumn, count }
CellsMerged               { sheet, range }
RangeCut / RangePasted    { fromRange, toRange, options }   # moves with reference fix-up
```

**This is THE distinctive event class for spreadsheets.** A single `RowInserted` at row 5 of `Sheet1` requires:

1. Shifting every row ≥ 5 in `Sheet1` down by `count`.
2. Rewriting every A1 reference in *every formula in every sheet of the workbook* that pointed at a cell at or below row 5 of `Sheet1`. `=Sheet1!A5` becomes `=Sheet1!A6`. Ranges expand or shift accordingly.
3. Updating named ranges that overlap.
4. Updating conditional-formatting and data-validation ranges.
5. Marking every dependent of the touched cells dirty.

This is why most real systems internally store formulas in a position-relative form (R1C1 style or AST with relative offsets) precisely so a row insert doesn't require literally rewriting source text on every formula. R1C1's pitch is exactly this: "In A1 notation the formula `=$A2 * B$1` will change as you fill down or right, whereas its R1C1 equivalent `=RC1 * R1C` remains the same" ([Aspose Cells docs on R1C1](https://docs.aspose.com/cells/net/r1c1-reference-style-vs-a1/)).

In a row-as-record system this whole class of events collapses: there *is* no `RowInserted` reference cascade, because formulas reference *fields* (`{Amount}`), not positions. New row → new aggregate, no rewriting.

### Operational / OT-layer

```
CharInsertedInCellEditor  { sheet, a1Ref, position, char }   # mid-edit keystrokes
SelectionChanged          { userId, sheet, range }           # presence, not history
CursorMoved               { userId, sheet, a1Ref }
DragInProgress            { userId, fromRange, currentRange }
```

These exist in the OT/presence channel but are usually **never written to the durable event store**. They're ephemeral, transformed against concurrent ops, and discarded once the edit commits. Google Wave's classic OT design [whitepaper](https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html) is explicit that the operational stream is distinct from the document-history stream.

Coalescing rule: hundreds of `CharInsertedInCellEditor` collapse into one `CellValueSet` (or `CellFormulaSet`) on commit. That commit is the domain event.

## 4. Cross-aggregate processes & the formula dependency graph

The dependency graph is the *centerpiece* of any spreadsheet system. It's neither a write-side invariant of one aggregate nor a normal projection — it's an indexed read model that drives a saga (the recalculation cascade) on every value-event.

### Where the dependency graph lives

Three persistence stances seen in the wild:

1. **Rebuilt from formulas at load** — Excel's `calcChain.xml` is "not required. A calculation chain can be constructed in memory at load-time based on the formulas and their interdependence" ([OpenXML calc chain](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-calculation-chain)). The persisted version is purely a load-time optimization.
2. **Cached projection alongside the document** — HyperFormula keeps the dependency graph in memory as the canonical recomputation index; serialization includes "preserving the unique ids of the dependency graph nodes" ([HyperFormula discussion #1325](https://github.com/handsontable/hyperformula/discussions/1325)).
3. **Computed on every change, never persisted** — EtherCalc's sandboxed SocialCalc worker keeps the live graph in process RAM, persisting only the command log.

The graph itself is a **DAG** (formulas can't reference themselves except in iterative-calc mode). HyperFormula's [dependency graph doc](https://hyperformula.handsontable.com/docs/guide/dependency-graph.html):

> Each spreadsheet cell is represented by a separate node. Nodes X and Y are connected by a directed edge if and only if the formula in cell X includes the address of cell Y. If formulas in the spreadsheet include ranges, each range is represented by a separate node.

That **range-as-node** trick is critical. Naively, `SUM(A1:A1000)` creates 1000 edges. HyperFormula instead reuses overlapping ranges: "every time the engine encounters a range, say `B5:D20`, it checks if it has already considered the range which is one row shorter" — keeping the graph from being O(n²).

### Recompute as a saga

Conceptually, every value-event triggers a process:

```
CellValueSet { sheet=Sheet1, a1Ref=A1, newValue=42 }
     │
     ▼  [DependencyGraph projection lookup]
     │
DirtyCellsMarked { cells = transitive_dependents(A1) }
     │
     ▼  [Recalc engine; topologically ordered]
     │
For each dirty cell in topological order:
   CellFormulaResultComputed { a1Ref, computedValue, calcVersion }
     │
     ▼  [Side-effect: push to subscribers]
     │
ProjectionsUpdated → ChartsRefreshed → DependentNamedRangesRecomputed
```

In Excel ([recalculation docs](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation)): "When new data or new formulas are entered, Excel marks all the cells that depend on that new data as needing recalculation. Cells that are marked in this way are known as *dirty*. All direct and indirect dependents are marked as dirty so that if B1 depends on A1, and C1 depends on B1, when A1 is changed, both B1 and C1 are marked as dirty."

Whether the `FormulaResultComputed` is a real event in your store depends on the boundary you draw:

- **Internal projection update** in Excel / Sheets / EtherCalc — computed values are cached, not eventful.
- **Domain event** if downstream consumers (alerts, exports, sync to another system) need to react to a specific cell *result* changing rather than a formula changing.

Most real systems treat recompute as a side-effect of the value event, not as a separately persisted event. Sestoft's [Spreadsheet Implementation Technology](https://mitpress.mit.edu/9780262526647/spreadsheet-implementation-technology/) calls this the "support graph" and treats it as a derived structure used to compute the minimum set of cells to recalculate.

### Volatile functions

`NOW()`, `TODAY()`, `RAND()`, `RANDBETWEEN()`, `OFFSET()`, `INDIRECT()`, `INFO()`, `CELL()` are [volatile in Excel](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation): "Excel reevaluates cells that contain volatile functions, together with all dependents, every time that it recalculates."

In event-sourcing terms volatile functions break the **pure-projection** assumption: replaying the formula does not yield the same `CellFormulaResultComputed`. Real systems resolve this two ways:

- **Store the computed value** as part of the value event (Excel persists `<v>` in the cell XML alongside the formula).
- **Inject the "now" / RNG seed** as part of the recompute trigger — making the trigger itself the source of non-determinism rather than the formula.

The latter is the cleaner ES pattern: `RecalculationRequested { triggerTime, rngSeed }` and the resulting `CellFormulaResultComputed` is now deterministic given those two inputs.

### Cycle detection

[Excel docs](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation): "If a cell depends, directly or indirectly, on itself, Excel detects the circular reference and warns the user… In some cases, you might deliberately want this condition to exist. For example, you might want to run an iterative calculation."

Cycle detection is graph-traversal on the dependency DAG at edit-time. The classical algorithm: when adding an edge `(X → Y)`, check whether `Y` is already a transitive ancestor of `X`. Some systems do this incrementally (Pearce-Kelly online cycle detection); others do batch DFS on every recompute. Figma's tree case is structurally identical: "Figma's multiplayer servers reject parent property updates that would cause a cycle" ([Figma multiplayer](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/)).

When iterative calc is enabled, the cycle isn't an error — it's a fixed-point iteration. The recalc engine runs the cycle N times or until convergence.

### Cross-sheet & external references

- **Cross-sheet** (`=Sheet2!B5`): a single edge in the same workbook's graph. No special saga.
- **Cross-workbook / external** (`='[Other.xlsx]Sheet1'!A1`): the dependency graph has a node that lives in *another aggregate*. Three approaches:
  - **Snapshot at link time**: the cached value is stored; updating requires explicit refresh. Most desktop Excel.
  - **Live subscription**: a process-manager subscribes to changes in the source workbook and emits events into the target workbook. Excel Online's linked-workbook refresh; Smartsheet cross-sheet references.
  - **Forbidden**: Google Sheets uses `IMPORTRANGE()` which is async and explicitly batched; Airtable's "two-way syncing" is a [scheduled sync](https://support.airtable.com/docs/two-way-syncing-in-airtable), not a live link.

### Array formulas / dynamic arrays / spilled results

Excel's [dynamic arrays](https://support.microsoft.com/en-us/office/dynamic-array-formulas-and-spilled-array-behavior-205c6b06-03ba-4151-89a1-87a7eb36e531): "This is one of the fundamental changes to the Excel calc engine. Implicit intersection is no longer the default." A single `=SORT(D2:D11,1,-1)` in `F2` *spills* into `F2:F11`. The formula is owned by `F2`; `F3:F11` are *displayed* values projected from F2's result.

In events: the formula is `CellFormulaSet { F2, "=SORT(...)" }`, and the result is a `SpillRangeMaterialized { sourceCell: F2, materializedRange: F2:F11, values: [...] }`. The materialized range cells are not independent — any direct edit to `F5` becomes a `#SPILL!` blocker error.

### Formula storage: AST vs string vs both

Most modern engines store **both**:

- **Source text** (`"=SUM(A1:A10) + B1"`) — for round-tripping with .xlsx/.gsheet files and for user display.
- **AST** (parsed tree of operators, function calls, refs) — for evaluation and for reference rewriting on structural changes.

HyperFormula serializes the AST with stable node IDs; Excel serializes source text in `<f>` elements and rebuilds the AST at load. Reference rewriting on row/column insert is *much* easier on the AST (walk references, shift) than on source text (re-tokenize, re-emit).

## 5. Collaborative editing — OT, CRDT, and the pragmatic middle

This is where spreadsheets diverge from collaborative text editors in interesting ways. Three strategies dominate concurrent-edit handling, and the relevant tradeoffs matter for the rest of this section:

- **LWW** (last-write-wins) — concurrent writes to the same property: the later one replaces the earlier. Per-property granularity is essential; whole-document LWW is useless.
- **OT** (operational transform) — concurrent ops are transformed against each other so all clients converge regardless of arrival order. Used by Google Sheets / Docs / Excel Online.
- **CRDT** (conflict-free replicated data type) — data structures whose merge is mathematically guaranteed to converge without transforms or a central server.

For the full treatment of when each is the right choice and why, see [concepts/collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md). The rest of this section assumes you know the basic distinction and focuses on what's specific to spreadsheets.

### Why CRDTs are hard for grid spreadsheets specifically

The standard list/sequence CRDTs (Yjs's YArray, Automerge's list type, RGA, LSEQ) assume the document is **an ordered sequence whose positions are not referenced by other parts of the document**. In a spreadsheet none of that holds:

1. **The grid isn't a sequence.** It's a 2-D sparse map. A `RowInserted` at row 5 conceptually shifts all positions below — but in a positional-identifier CRDT, "position 6" gets a *new* identifier between two existing ones; existing positions don't move.
2. **Formulas reference positions, not identifiers.** `=A5` means "the cell at column A row 5", not "the cell with CRDT-identifier 0.4172". If row 5 stays the *same identifier* but is now visually at row 6 (because a row was inserted above), every formula referencing A5 now points at the wrong logical cell. Either you rewrite formulas (operational semantics on top of CRDT positions — defeating purity) or you give every cell a stable identity and break the A1 referencing model.
3. **Ranges are even worse.** `SUM(A1:A10)` would have to be a CRDT range from `posA1` to `posA10`, with all 8 cells between included. A concurrent insert "into" the range and a concurrent insert "outside" the range produce different intended results.

This is why no widely-used spreadsheet uses a sequence CRDT for its grid. The systems that *do* use CRDTs (or claim to) either:

- Use them only for **text inside one cell** (the cell-editor sub-model).
- Use a **map CRDT** keyed by (sheet, cellId) and treat positions as a separate ordering field (essentially the row-as-record stance again).
- Use property-level LWW on cell values plus deterministic conflict resolution on structure (Figma's approach generalized).

The reference-crdts repo by Joseph Gentle ([josephg/reference-crdts](https://github.com/josephg/reference-crdts)) gives clean implementations of the Yjs/Automerge list types; reading them makes clear how much they assume sequences-without-cross-reference.

### What Google Sheets does (and historically did)

Google Docs and (by extension) Sheets use **operational transformation** based on the Jupiter algorithm ([Wave OT whitepaper](https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html)):

> Jupiter in 1995 is the basis of Google Wave, and Google Wave OT is basically based on the algorithm given by the Jupiter System… In 2009 OT was adopted as a core technique behind the collaboration features in then-Google Wave and Google Docs.

In a Jupiter-style server architecture, the server is authoritative. Each client sends operations with a "based-on" revision; the server transforms incoming ops against any concurrent ops, then broadcasts the canonical transformed sequence. The operation taxonomy for Sheets includes: `SetCell`, `InsertRows`, `DeleteColumns`, `Move`, `Format`, etc., and OT transformation rules are defined per pair of op types (e.g., `InsertRow` vs `SetCell` — shift the SetCell target down if the SetCell row ≥ inserted-at row).

The relevant Google patents ([US7792788](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7792788), [US9460073](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9460073)) describe collaborative-spreadsheet OT directly.

### EtherCalc — sequential command relay, no transformation

EtherCalc's solution: don't transform, *serialize through the server* ([From SocialCalc to EtherCalc](https://aosabook.org/en/posa/from-socialcalc-to-ethercalc.html)).

> Clients send their locally executed commands and cursor movements to the server, which relays them to all other clients in the same room… The server executes its own state as it receives each command.

A sandboxed SocialCalc instance per room (~30KB RAM each) executes commands sequentially. There's no OT/CRDT — concurrency is resolved by linearization at the single-threaded worker. The cost: clients optimistically apply locally and may have to roll back if the server's order differs. The benefit: simplicity, and you get a clean per-room command log that's exactly the event stream.

### Airtable — incremental view maintenance, not OT/CRDT

[Airtable's Rust rewrite](https://medium.com/airtable-eng/rewriting-our-database-in-rust-f64e37a482ef) is explicit:

> Real-time collaboration: it computes how a write impacts each live query without re-executing the query from scratch, and produces a compact diff… serializable, atomic transactions backed by MVCC.

Because the aggregate is the row and transactions are serializable, there's no "merge two concurrent edits to the same row" CRDT problem — the second transaction sees the result of the first. The collaborative experience is delivered by **push diffs of materialized views** to subscribed clients, not by replicated mutable state on the client. This is the same shape as a [GraphQL subscription](https://www.apollographql.com/docs/router/executing-operations/subscription-overview/) over MVCC snapshots.

### Notion — server-authoritative LWW with operation streams

> Notion is "collaborative" and previously didn't use a CRDT for text; it's been all last-write-wins decided by the server… Notion is working on switching to CRDT for their texts.
> — Notion engineer on [HN](https://news.ycombinator.com/item?id=37767739)

Most properties are LWW; rich text inside a block is the only place where granular merging matters and is migrating to CRDTs.

### Figma's lesson, applied to spreadsheets

Figma rejected both OT and CRDTs in favor of **property-level LWW** ([madebyevan.com/figma](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/)):

> Two clients changing unrelated properties on the same object won't conflict, and two clients changing the same property on unrelated objects also won't conflict. A conflict happens when two clients change the same property on the same object, in which case the document will just end up with the last value that was sent to the server.

Applied to spreadsheets: per-cell, per-property LWW. Two users editing different cells: no conflict. Two users editing the same cell's value simultaneously: the server's last-received write wins. This is exactly how Notion DBs and most "spreadsheet-like" tools that aren't Google Sheets / Excel Online behave. It works because the conflict granularity (cell value) matches the user's mental model. It does *not* work for raw text input — `AB` + `BC` ends as one of the two, not `ABC`.

### Offline / local-first

Airtable's "data for a given base is read into memory… by a dedicated server" doesn't permit truly disconnected edits — clients reconcile via the worker. Figma's offline mode "downloads a fresh copy of the document, reapplies any offline edits on top of this latest state" — same shape: client-side op log, server-side authoritative merge. True CRDT-style offline-first (Automerge in `pkm-app` style) is rare in production spreadsheets precisely because of the reference-rewriting problem (§3).

### Undo/redo

In single-user spreadsheets undo is an inverse-event stack. In collaborative spreadsheets it gets harder ([Concurrent Undo Operations in Collaborative Environments via OT, Springer](https://link.springer.com/chapter/10.1007/978-3-540-30468-5_12)):

> Each user can make modifications and receive modifications from others, and the undo action should only undo the user's own operations, not those of others… If operations from other clients are received before the user's operation is undone, the user's undo may need to be transformed with the operations from other clients.

Practical shape: each user has a personal undo stack of *their own* operations; each undo is itself a new operation, transformed against everyone else's intervening ops, and broadcast. Figma's invariant: "if you undo a lot, copy something, and redo back to the present… the document should not change." HyperFormula keeps a per-session undo stack with a default 20-action limit ([undo-redo docs](https://hyperformula.handsontable.com/docs/guide/undo-redo.html)).

## 6. Real-world gotchas

### The sparse infinite grid

Excel exposes `1,048,576 × 16,384 = ~17 billion` cells per sheet. The overwhelming majority are empty. Real storage is sparse:

- `.xlsx` stores only cells with content ([the minimum viable XLSX reader](https://www.brendanlong.com/the-minimum-viable-xlsx-reader.html)): "Since XLSX is sparse, missing empty cells must be filled in [by readers]."
- Strings are deduplicated into `[sharedStrings.xml](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-shared-string-table)`: "Excel stores strings in one big shared string table… cells just hold a reference to the appropriate string."
- Formats are reference-counted into a style table; conditional formats are stored once per *rule*, not per cell.

In event sourcing terms: never persist `CellCreated` for every cell. Only mutated cells generate events. A "blank cell at A:1048576" doesn't exist until something is written to it.

### Reference rewriting on row/column insert/delete

Covered in §3 — this is the most consistent footgun across engines. The implementation pattern that wins:

1. Store formulas as AST with **relative references resolved at evaluation time**.
2. On `RowInserted(at=N, count=K)`, walk the dependency graph (not every formula in the workbook!) for nodes with references to rows ≥ N and rewrite them.
3. Update named ranges, conditional-format ranges, chart data ranges, data-validation ranges in the same transaction.
4. Mark dependents dirty.

Forgetting step 3 is how charts end up pointing at the wrong cells after a paste.

### Cross-sheet/cross-workbook references that break

- **Sheet renamed**: every formula `=Sheet1!A1` must become `=NewName!A1`. This is why `SheetRenamed` is a structural event in §3 — it cascades through formulas.
- **Sheet deleted**: dependents become `#REF!` errors. Some systems "tombstone" the deleted sheet so the formula can be recovered if undone; others hard-rewrite.
- **External workbook moved/renamed**: Excel's `[Other.xlsx]Sheet1` reference becomes unresolvable. The graph node still exists but its value is stale.

### Cell precedence / dependency cycles after a paste

Paste-from-another-workbook injects formulas with references to cells that may or may not exist in the destination. Possible outcomes:

- Formula references break (`#REF!`).
- Formula references resolve to *different* cells in the destination (silently wrong).
- A copy-paste creates a cycle that didn't exist in the source (because the destination already had a formula referencing the pasted-into range).

Excel's defense: rebuild the dependency tree on paste, run cycle detection, surface the warning. Sheets does the same.

### Undo/redo with concurrent editors

See §5. Specific gotcha: **history compaction** ([Google Sheets version history](https://www.ablebits.com/office-addins-blog/google-sheets-edit-history/) — older edits get merged or dropped) breaks the assumption that undo can walk arbitrarily far back. Production systems cap undo depth precisely because the operation log is compacted in the background.

### Add-ons / custom functions

Excel UDFs and Apps Script `onEdit` triggers run **as side effects**, not as native events:

- [Apps Script Lock service](https://developers.google.com/apps-script/reference/lock/lock): "When working with a spreadsheet, you should call SpreadsheetApp.flush() prior to releasing the lock, to commit all pending changes."
- Excel async UDFs ([recalc docs](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation)): "When a calculation encounters an asynchronous UDF, it saves the state of the current formula, starts the UDF and continues evaluating the rest of the cells. When the calculation finishes… Excel waits for the asynchronous functions to complete."

The async result eventually triggers another `CellFormulaResultComputed` — but the timing is non-deterministic. UDF outputs are not safe to replay.

### Edit conflict on the same cell

- **Sheets / Excel Online (OT)**: transform; usually last-write semantics on `SetCell` produce a single canonical value.
- **Figma / Notion (LWW)**: server's last received write wins; the loser's local optimistic update is rolled back.
- **EtherCalc**: server linearization decides; both edits applied in arrival order, second overwrites first.
- **Airtable (MVCC)**: serializable transactions; second commit must reread.

### Format vs value as typed events

Already noted in §3. Formats are typically **commutative and idempotent** (setting bold twice has the same effect; setting color and font are independent). Values are not. Separate event types let projections that only care about values ignore format churn entirely.

### Million-row sheets, conditional formatting on every cell

Conditional formatting rules apply to *ranges*, not cells. A rule `range=A:A, condition="value > 100"` does not generate 1M `CellFormatChanged` events — it's a single `ConditionalFormatApplied` event, and the format is computed at render time. Same for data validation.

Performance pain points in event sourcing terms:

- **Calc-chain churn**: each value change marks transitive dependents dirty. A bad spreadsheet can have one cell whose change dirties 100k others.
- **Multithreaded recalc** ([Excel multithreaded recalc](https://learn.microsoft.com/en-us/office/client-developer/excel/multithreaded-recalculation-in-excel)): independent branches of the DAG calculate in parallel. Causal's variable-level engine takes this further with SIMD vectorization across whole arrays ([Scaling Causal](https://sirupsen.com/causal)).

## 7. Sagas / cross-aggregate processes that show up

### Auto-save & version history

Auto-save is a process that batches recent events into named revisions:

```
EditCommitted (×N during a few seconds)
     ▼
DraftBatchClosed { revisionId, events: [...] }
     ▼
RevisionSnapshotted { revisionId, snapshotRef }
     ▼  [periodically]
OldRevisionsCompacted { mergedRevisionIds: [...] }
```

Google Sheets' [version history](https://www.ablebits.com/office-addins-blog/google-sheets-edit-history/): revisions are merged over time to save storage. Notion's "snapshot-plus-log pattern is a direct analog of write-ahead logging in databases and event sourcing in distributed systems… A versioning and history service records operation streams and periodic snapshots."

### Named ranges

A named range is a workbook-scoped or sheet-scoped alias for a range expression ([Excel named ranges](https://www.ablebits.com/office-addins-blog/2017/07/11/excel-name-named-range-define-use/)). Events:

```
NamedRangeDefined  { name, scope, rangeExpression }
NamedRangeRedefined { name, newRangeExpression }
NamedRangeDeleted  { name }    # dependents become #NAME?
```

Named ranges interact with structural events: `RowInserted` *inside* a named range expands it; *above* it shifts it; *outside* it leaves it alone. That's a saga on `RowInserted`.

### Import / paste from another sheet — the dependency graph migration problem

Paste of `B1:B10` containing `=A1+1`, `=A2+1`, ... `=A10+1` into a target. Two reasonable semantics:

- **Relative-reference paste**: formulas adjust based on the offset between source and target. `=A1+1` pasted at `D5` becomes `=C5+1`. This is the Excel default for non-anchored references.
- **Absolute paste**: formulas keep their original source references. `=A1+1` stays `=A1+1`, now in `D5`. Cross-workbook paste defaults this way.

Both require AST rewriting on paste, plus dependency-graph edges added, plus cycle re-check.

### Apps Script / macros mutating the sheet

These run as side-effects of user-triggered events but emit further user-equivalent events. A macro that writes 100 cells should ideally produce 100 `CellValueSet` events (so they can be undone) but be coalesced into a single user-visible undo step. Apps Script's `LockService` plus `SpreadsheetApp.flush()` is exactly the boundary marker: all events within one lock acquisition form one undo group.

## 8. Sources & case studies

### Foundational / academic

- Peter Sestoft — *[Spreadsheet Implementation Technology: Basics and Extensions](https://mitpress.mit.edu/9780262526647/spreadsheet-implementation-technology/)*, MIT Press 2014. The canonical reference. Defines the "support graph" recompute model and the Corecalc / Funcalc reference implementations.
- David A. Wheeler — [OpenFormula spec](https://docs.oasis-open.org/office/v1.2/OpenDocument-v1.2-part2.html) (now ISO 26300-2). What a formula language *means* across implementations.
- ISO/IEC 29500 (OpenXML) and the [OpenXML calculation chain docs](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-calculation-chain).
- David Nichols et al. — *[High-latency, low-bandwidth windowing in the Jupiter collaboration system](https://dl.acm.org/doi/10.1145/215585.215706)*. The Jupiter algorithm that Wave / Docs / Sheets generalized.

### Microsoft Excel

- [Excel Recalculation (Microsoft Learn)](https://learn.microsoft.com/en-us/office/client-developer/excel/excel-recalculation) — the canonical doc on dirty cells, calc chain, volatile functions, iterative calc.
- [Multithreaded recalculation in Excel](https://learn.microsoft.com/en-us/office/client-developer/excel/multithreaded-recalculation-in-excel).
- [Improving calculation performance](https://learn.microsoft.com/en-us/office/vba/excel/concepts/excel-performance/excel-improving-calculation-performance).
- [Dynamic array formulas and spilled array behavior](https://support.microsoft.com/en-us/office/dynamic-array-formulas-and-spilled-array-behavior-205c6b06-03ba-4151-89a1-87a7eb36e531).
- [SharedStringTable in OpenXML](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-shared-string-table).
- [Decision Models — Excel calc secrets](https://www.decisionmodels.com/calcsecretsd.htm).

### Google Sheets

- USPTO patents [US9460073](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/9460073) "Systems and methods for mutations and operational transforms in a collaborative spreadsheet environment" and [US7792788](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7792788) "Method and system for resolving conflicts operations in a collaborative editing environment".
- [Google Wave Operational Transformation whitepaper](https://svn.apache.org/repos/asf/incubator/wave/whitepapers/operational-transform/operational-transform.html).
- [Google Sheets system design walkthrough (educative)](https://www.educative.io/blog/google-sheets-system-design) — third-party, useful for architecture overview.
- [Google Sheets version history operation](https://www.ablebits.com/office-addins-blog/google-sheets-edit-history/).
- [Apps Script Lock Service](https://developers.google.com/apps-script/reference/lock/lock).

### Airtable / row-as-record systems

- Andrew Kumansley — [Rewriting Our Database in Rust](https://medium.com/airtable-eng/rewriting-our-database-in-rust-f64e37a482ef), Airtable Engineering Blog, March 2026. Single-tenant in-memory DB, MVCC, incremental view maintenance.
- [Airtable two-way syncing](https://support.airtable.com/docs/two-way-syncing-in-airtable).
- [Notion data model](https://www.notion.com/blog/data-model-behind-notion) — block model with parent pointers; LWW.
- [HN: Notion's collaborative model](https://news.ycombinator.com/item?id=37767739).
- [Smartsheet platform features](https://www.smartsheet.com/platform/features) — row-level collaboration model.

### EtherCalc / open source

- Audrey Tang — *[From SocialCalc to EtherCalc](https://aosabook.org/en/posa/from-socialcalc-to-ethercalc.html)*, AOSA *The Performance of Open Source Applications*. Sandboxed sequential workers, command-relay model.
- HyperFormula — [dependency graph](https://hyperformula.handsontable.com/docs/guide/dependency-graph.html), [undo-redo](https://hyperformula.handsontable.com/docs/guide/undo-redo.html), [GitHub](https://github.com/handsontable/hyperformula).
- [ShareDB (OT-JSON0)](https://github.com/share/sharedb) — the canonical open-source OT library.
- [OnlyOffice DocumentServer source](https://github.com/onlyoffice/documentserver).
- Collabora Online (LibreOffice in the browser) — [architecture overview](https://www.collaboraonline.com/comparing-collabora-with-onlyoffice/).
- ClosedXML — [formula evaluation deepwiki](https://deepwiki.com/ClosedXML/ClosedXML/3.1-formula-evaluation).

### CRDT / OT theory specific to collaborative editing

- Evan Wallace — [How Figma's multiplayer technology works](https://madebyevan.com/figma/how-figmas-multiplayer-technology-works/). Why property-level LWW beats OT/CRDT for object-graph documents.
- Joseph Gentle — [reference-crdts](https://github.com/josephg/reference-crdts). Minimal spec-compliant Yjs/Automerge list implementations; useful for seeing exactly what assumptions sequence CRDTs make.
- [Yjs docs](https://docs.yjs.dev/) and [Automerge](https://crdt.tech/implementations).
- [Eg-walker — *Collaborative Text Editing: Better, Faster, Smaller](https://arxiv.org/pdf/2409.14252)*. Newer CRDT efficient enough to compete with OT.
- [Concurrent Undo Operations in Collaborative Environments Using OT (Springer)](https://link.springer.com/chapter/10.1007/978-3-540-30468-5_12).

### Dimensional / next-gen engines

- Rishikesh Yadav (sirupsen) — [Scaling Causal's Spreadsheet Engine from Thousands to Billions of Cells: From Maps to Arrays](https://sirupsen.com/causal). Variable-level engine, struct-of-arrays, SIMD recompute.
- [Rows.com AI Spreadsheet Benchmark](https://rows.com/blog/post/ai-spreadsheet-benchmark) — context on Rows / Coda / Equals positioning.
- Coda — [Reference current rows with thisRow](https://help.coda.io/hc/en-us/articles/39555822109837-Reference-current-rows-in-formulas-with-thisRow) — what row-aware formulas look like vs A1.

### Practitioner writeups

- [SpreadJS — Introducing Real-Time Collaboration in JavaScript Spreadsheets](https://developer.mescius.com/blogs/introducing-real-time-collaboration-in-javascript-spreadsheets). Command-based collaboration in a commercial library.
- [Quip architecture tour (SD Times)](https://sdtimes.com/android/googles-bret-taylor-gives-tour-quips-architecture/) — atomic-unit document model.
- Oskar Dudycz — [Closing the Books](https://event-driven.io/en/closing_the_books_in_practice/). Period-bucketing applies to long-lived workbooks too: snapshot at fiscal-quarter end, truncate prior op-stream.
- [Verraes — Practical Event Sourcing](https://verraes.net/2014/03/practical-event-sourcing/). Background on event-vs-side-effect distinctions referenced throughout.
- See also the [collaborative documents section of unbounded-and-infinite-streams.md](../unbounded-and-infinite-streams.md#a-collaborative-documents--every-keystrokeoperation-is-an-event) for the broader class of "every keystroke is an event" problems this domain belongs to.

