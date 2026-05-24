# Multi-Region Replication for Event-Sourced Systems

Single-region ES is comfortable: one append-only log, one optimistic-lock authority, one clock-ish thing, one regulator. Cross a region boundary and every assumption becomes negotiable. This is the practical playbook — when to pick single-writer / region-pinned / true multi-master, and what each costs once the wire is 80–200 ms long.

Deployment-level companion to substrate-level [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md) and policy-level [federated-systems.md](federated-systems.md). For why histories stop being linear, see [unbounded-and-infinite-streams.md §E](../unbounded-and-infinite-streams.md#e-branching--non-linear-histories).

## 1. The latency tax

Every cross-region quorum write pays at least one RTT to the furthest member. The numbers don't move:

| Path | Typical RTT | Effect |
|---|---|---|
| Within AZ | 0.5–2 ms | Free |
| Cross-AZ same region | 1–2 ms | Standard 3-AZ quorum |
| US-East ↔ US-West | 60–80 ms | Quorum write ≈ 80 ms min |
| EU ↔ US-East | 80–100 ms | Cross-Atlantic quorum dominates p99 |
| EU ↔ APAC | 150–250 ms | Synchronous quorum unusable for OLTP |

A 200 ms cross-region quorum means **5 writes/second is your single-row ceiling** — the [Spanner / paxos](https://cloud.google.com/blog/products/databases/strict-serializability-and-external-consistency-in-spanner) tax. Even [Aurora Global Database](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database.html) only manages "typically < 1s" replication lag, floored by physics. Bottom line: **the moment your hot path needs synchronous cross-region ack, you've lost.**

## 2. Three architectural shapes

| Shape | Writes | Failover | Conflict model | Good for |
|---|---|---|---|---|
| **Single-writer, replica regions** | One region only | Hard — promote a replica, expect data loss | None | Strong consistency, low write rate |
| **Region-pinned aggregates** | Aggregate's home region only | Per-region only | None on hot path; cross-region via sagas | Most line-of-business systems |
| **True active/active with merge** | Any region | Trivial; another region keeps serving | LWW, CRDT, domain resolver | Counters, presence, carts, collab edits |

### 2.1 Single-writer, replica regions

One region is authoritative; others read-only. Examples: [Aurora Global Database](https://aws.amazon.com/blogs/database/cross-region-disaster-recovery-using-amazon-aurora-global-database-for-amazon-aurora-postgresql/) (one primary + up to 5 fast-replicas, sub-second replication); [EventStoreDB with a remote follower](https://discuss.eventstore.com/t/replicating-events-across-datacenters/300) or `Event Store Replicator`; Postgres + Marten with [logical replication](https://event-driven.io/en/push_based_outbox_pattern_with_postgres_logical_replication/). ES fits naturally — log is the replication unit, position monotonic, no conflicts. The complication is **failover**:

```
RegionPromoted     { promotedRegion, demotedRegion, lastReplicatedPosition, lostEventCount }
RegionDemoted      { demotedRegion, at, reason: 'planned' | 'unplanned' }
WriteResumed       { region, atPosition }
```

A **planned switchover** ([Aurora terminology](https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/aurora-global-database-disaster-recovery.html)) drains writes, lets replication catch up, promotes — RPO 0. An **unplanned failover** promotes immediately, accepting non-zero RPO. Either way the promoted region must drain its outbox before resuming writes, or aggregate versions collide with events still trapped in the old primary.

### 2.2 Region-pinned aggregates (the dominant pattern)

Every aggregate has one home region. Writes go there; reads anywhere via async replication. This is the [Shopify Pods pattern](https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale) — "A pod is active in only one region at a time, and its non-active counterpart serves as a failover mechanism." Also exactly how [Cloudflare Durable Objects](https://developers.cloudflare.com/durable-objects/) work — globally addressable but pinned ("Durable Objects do not currently change locations after they are created"), with [jurisdiction constraints](https://developers.cloudflare.com/data-localization/how-to/durable-objects/) for regulatory boundaries.

The pattern dodges every hard distributed-systems problem on the write path: per-stream optimistic concurrency stays intact, cross-region traffic is async replication for read models. The cost moves to the **routing layer** — every command must be steered to the home region.

### 2.3 True active/active with merge

Both regions accept writes for the same aggregate; conflicts merge later. Only safe with a deterministic loser ([DynamoDB Global Tables LWW](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/V2globaltables_HowItWorks.html): "the modification with the latest internal timestamp") or a structural merge function ([Netflix's Cassandra active/active](https://medium.com/netflix-techblog/active-active-for-multi-regional-resiliency-c47719f6685b)). The stream is no longer linear — it's a DAG, and projections must converge over a merge. Use only where semantics agree: carts, counters, presence — *not* ledger balances, *not* hard invariants. See [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md).

## 3. Choosing the home region

Pinning is effectively irreversible — re-homing is a migration. Drivers:

| Driver | Pin key | Examples |
|---|---|---|
| **User's country** | `customer.countryCode` → region | DE-KYC customer → EU |
| **Regulatory jurisdiction** | GDPR / CCPA / APPI / LGPD | EU PII must not leave EU per [Schrems II](https://www.sovy.com/blog/schrems-ii/) |
| **Latency to actor** | source latency | Mobile-first apps where p99 dominates UX |
| **Tenant location** | `tenant.region` | [Shopify Pods](https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale) — each shop pinned to a pod-in-region |
| **Counterparty pairing** | `min(payer.region, payee.region)` | Cross-border payment: which side owns the saga? |

The routing layer is `(aggregateType, aggregateId) → homeRegion`. Implementations: a globally-replicated routing table (textbook [CockroachDB `GLOBAL` table](https://www.cockroachlabs.com/docs/stable/multiregion-overview)); a stream-id prefix encoding the region; or DNS-based (one hostname per region, like [DynamoDB Global Tables' regional endpoints](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GlobalTables.html)). Mis-routed commands either forward or reject (`WrongRegion{aggregateId, expectedRegion, observedRegion}`) — reject is safer; silent forwarding hides latency.

## 4. Stream-id naming with region encoded

Region as a first-class part of the key is the simplest, most debuggable choice:

```
eu-account-{id}                              # write region encoded in the prefix
us-account-{id}
apac-customer-{id}
eu-de-account-{id}                           # region + sub-region for residency drilldown
{region}-{aggregate}-{id}-{period}           # combined with closing-the-books
```

Routing is grep-able in dead-letter queues; subscription filters (`eu-*`) expose topology; id collisions across regions become structurally impossible. Cost: re-homing renames the stream — a migration, which is the right cost for a deliberate operation.

## 5. Cross-region sagas

A saga spanning regions inherits cross-region latency per hop. The 80–200 ms RTT becomes the *floor* on saga step time; failure mode shifts from "step failed" to "step took too long":

```
TransferInitiated     { transferId, fromAccountId: eu-account-A, toAccountId: us-account-B, amount }
DebitRequested        { transferId, region: eu }                # local
DebitPosted           { transferId, ledgerEntryId, region: eu }
CreditRequested       { transferId, region: us }                # CROSS-REGION — 80–100 ms min
CreditPosted          { transferId, ledgerEntryId, region: us }
TransferCompleted     { transferId, completedAt }
```

**Outbox pattern with cross-region delivery is mandatory** — never call the remote region synchronously from a command handler. Local saga step persists `CreditRequested` to outbox; async relay delivers it; destination appends `CreditPosted` and replicates back. See [multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md). The multi-region twist: every relay hop crosses an unreliable link.

**Timeouts must be region-aware.** A 30 s single-region timeout needs minutes across an ocean with retries. Otherwise the saga "times out" while the remote step is still executing — duplicate `Credit` attempts, which is why every event needs a globally-unique `idempotencyKey` (§14).

**Saga ownership.** One region owns the state machine (usually the initiator's); the other is a participant. Two regions running the same saga for the same `transferId` is the multi-region split-brain.

## 6. Replicated vs region-local projections

Projections almost always need to be region-local even when events replicate globally: read latency (Tokyo UI reading a US projection is 150+ ms); schema independence; compliance (a region-local projection cannot leak PII to a non-compliant jurisdiction).

The **redundant projection per region** pattern: each region runs identical projection logic against a regionally-mirrored copy of the event log. Projections are deterministic, so identical inputs produce identical outputs — but only after replication settles. Until then a US-side projection of an EU aggregate is `N ms` stale.

**Beware side-effecting projections.** Running them in every region triggers N-fold side effects. Either make side-effecting projections leader-elected to one region (Marten's [HotCold daemon mode](https://martendb.io/events/projections/) does this within a single cluster; multi-region needs an external coordinator), or split: state per region, side effects gated by a single-region executor.

## 7. Optimistic concurrency across regions

`expectedVersion` (see [optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md)) composes only when one aggregate has one authoritative version counter. Once two regions can both increment it, the abstraction collapses:

```
T=0      EU loads version=3, appends E4   -> version=4 locally
T=0      US loads version=3, appends E4'  -> version=4 locally
T=200ms  Replication: both regions see version=5 ... with DIFFERENT E4 events.
```

Region-pinned aggregates (§2.2) sidestep this. For true active/active:

- **Hybrid Logical Clocks (HLC)** — 64-bit `(physical_ms, logical_counter, nodeId)`. Used by [CockroachDB](https://www.cockroachlabs.com/glossary/distributed-db/hybrid-logical-clock-hlc-timestamps/) and [MongoDB](http://muratbuffalo.blogspot.com/2024/04/implementation-of-cluster-wide-logical-clock-and-causal-consistency-in-mongodb.html) as the universal event-ordering key. NTP-bounded, no special hardware. Replaces `expectedVersion` with `expectedHLC < currentMaxHLC` — monotonic but not enough alone to detect logical conflicts.
- **Vector clocks per aggregate** — one counter per writing region: `{eu: 4, us: 4}`. Conflicting writes detectable (both wrote from `{eu: 3, us: 3}`); merge function resolves. Bounded overhead for ES.
- **Calvin-style deterministic ordering** — every region appends to a globally pre-ordered log; deterministic apply assigns a canonical version. [FaunaDB's transaction engine](https://fauna.com/blog/inside-faunas-distributed-transaction-engine-dte): "in Calvin, clock skew has no impact on correctness." Cost: every transaction pays one cross-region log-append latency.
- **TrueTime** ([Spanner](https://docs.cloud.google.com/spanner/docs/true-time-external-consistency)) — atomic clocks + GPS plus ~7 ms `commit-wait` to guarantee global timestamp uniqueness. Strictly serializable; only inside Google's network (or [Spanner Omni](https://cloud.google.com/products/spanner/omni) as software-defined alternative).

In practice: pin first; HLC for ordering where pinning isn't possible; vector clocks or Calvin only when you cannot pin (true peer-to-peer collab).

## 8. Conflict resolution at merge

When two regions concurrently wrote the same aggregate and replication brings them together, *something* must reconcile. Strategies map onto [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md):

| Strategy | What it does | When it fits |
|---|---|---|
| **LWW** | Compare HLC / wall-clock; later wins | Idempotent settings, presence, last-known-location |
| **Per-field LWW** | Each field independently (Figma-style) | Object-graph documents, profile updates |
| **CRDT merge** | Operations commute; both apply | Counters, sets, multi-cursor edits, carts |
| **Domain merge** | Custom resolver in code | Inventory across regions, partial-overlap cases |
| **Manual / human** | Conflicts produce an event needing intervention | Anything with regulatory or financial consequence |

**Materialise the merge as an event** to preserve audit trail:

```
RegionalConflictDetected {
  conflictId, aggregateId,
  candidateA: { region, hlc, eventIds[], summary },
  candidateB: { region, hlc, eventIds[], summary },
  strategy: 'lww' | 'crdt' | 'domain' | 'manual', detectedAt
}
RegionalConflictResolved {
  conflictId, aggregateId,
  winner: { region, eventIds[] },
  loser:  { region, eventIds[], dispositionEvent },   # what we emitted to nullify the loser
  resolvedBy: 'auto' | 'operator:{id}', reason
}
```

Loser's events are *not deleted* — that breaks ES immutability. The merge emits compensating events (e.g. `BalanceCorrectedToWinningRegion{delta}`) so projections converge. Loser events stay in their region's log as historical truth: "this is what region X believed happened, before merge."

## 9. Data residency / GDPR — partition by jurisdiction first

Post-[Schrems II](https://securityboulevard.com/2026/04/schrems-ii-and-the-future-of-cross-border-data-transfers/) reality: personal-data events must not flow freely across jurisdictions. EU PII stays in EU; CCPA, APPI, LGPD, PDPA all add constraints.

This inverts the modelling order: **draw regulatory boundaries first, then put aggregates inside them.** Treating regulatory zones as an afterthought is how teams end up with a class-action and a rewrite. Three usable patterns:

- **Strict partitioning** — EU events live in EU stores, replicated only to EU. Cross-jurisdiction reads go through an API that strips PII at the boundary. Simplest, most defensible.
- **Pseudonymous global replica + region-local key vault** — events replicate globally with PII encrypted; key lives only in home region. Non-home regions see ciphertext, can aggregate on opaque ids but cannot read PII. **Crypto-shredding** extended across regions: when the user invokes erasure, the EU key is deleted and ciphertext everywhere becomes permanently unreadable. See [ecommerce-and-retail.md](ecommerce-and-retail.md).
- **Event split** — `OrderPlaced{orderId, region}` replicates globally (skeletal); paired `OrderPersonalDetails{orderId, name, address, ...}` stays region-local. PII projections run only at home; analytical projections work everywhere off the skeletal stream.

The right-to-erasure event must be appendable in the home region without cross-region coordination. A request that requires quorum across regions can fail when the network fails — and "we couldn't process your erasure because US-East was down" is not a defence.

## 10. Failover & RPO/RTO

Async replication has non-zero RPO. Questions to answer up front:

| Question | What drives the answer |
|---|---|
| Max acceptable RPO? | Regulator, customer SLA. Banking often "0 for committed"; SaaS often seconds |
| Max acceptable RTO? | [Aurora unplanned failover: minutes](https://aws.amazon.com/blogs/database/cross-region-disaster-recovery-using-amazon-aurora-global-database-for-amazon-aurora-postgresql/); DynamoDB Global Tables MREC: immediate |
| In-flight events when primary dies? | Durable buffer in front of replication link, or accept the loss |
| Who decides? | Operator, auto health-check, cross-region quorum vote? |
| How do you fail back? | Reverse replication; reconcile divergent writes; promote original primary |

The buffer-in-front-of-replication pattern: primary writes to a local durable queue *before* acknowledging the client; replication agent drains the queue to the secondary. If the primary dies, the queue is the recovery state. Combine with explicit `EventReplicationConfirmed{eventId, fromRegion, toRegion, confirmedAt}` so each region reports lag in real time.

**Manual cutover procedures must be rehearsed.** A failover never practised will fail. Runbook: drain outbox, freeze writes, confirm replication is caught up (or accept RPO), promote, re-point routing, validate, resume. Netflix's Chaos Kong exists for exactly this.

## 11. Kafka multi-region patterns

The three [Confluent-classified topologies](https://www.confluent.io/blog/kafka-cross-data-center-replication-decision-playbook/), translated to ES:

| Topology | What it is | ES suitability |
|---|---|---|
| **Stretched cluster** | One logical cluster across DCs with low-latency links (< 50 ms); `min.insync.replicas` spans regions | Strong consistency; only works inside one continent with dedicated networking |
| **Active/passive (DR)** | One cluster handles traffic; [MirrorMaker 2](https://kafka.apache.org/41/operations/geo-replication-cross-cluster-data-mirroring/) async-replicates to a passive cluster | Single-writer-region ES (§2.1). MM2 ships `MirrorCheckpointConnector` for offset translation; consumers handle the discontinuity |
| **Active/active (bidirectional)** | Both clusters accept writes, MM2 replicates both ways with topic renaming (`us.orders` ↔ `eu.orders`) to prevent loops | Region-pinned aggregates (§2.2) — each region writes its own prefix |

[Confluent Cluster Linking](https://www.confluent.io/learn/kafka-mirrormaker/) is the same idea with native offset preservation — consumer offset migration on failover is trivial. MM2 needs offset translation; Cluster Linking does not. Greenfield on Confluent → Cluster Linking; otherwise MM2.

**The active/active pitfall is the replication loop**: event from A replicates to B, then B back to A. MM2 prevents this by topic-renaming (`{sourceClusterAlias}.{topicName}`); your application must handle renamed topics consistently. Same `event-{id}` arriving in `eu.orders` and `us.eu.orders` is the same event — dedup must recognise it.

## 12. EventStoreDB clusters and Marten / Postgres logical replication

**EventStoreDB / KurrentDB** uses a 2n+1 quorum cluster within a region ([source](https://developers.eventstore.com/server/v21.10/cluster.html)). Cross-region options:

- **Stretched cluster across low-latency DCs** — only viable when the link is < 30 ms and reliable; the election protocol assumes synchronous quorum.
- **Cluster + remote follower (non-promotable clone)** — a single node outside the quorum that streams everything; warm read-only secondary.
- **Event Store Replicator / GeoReplica** — separate cluster fed asynchronously; can be promoted but you accept the lag-window RPO. Bidirectional setups need explicit application-level filtering to avoid loops.

**Marten on Postgres** practitioners typically use Postgres native [logical replication](https://www.postgresql.org/docs/current/logical-replication.html) to ship `mt_events` (and any projection tables you want region-local) to a secondary region. The async daemon ([Marten HotCold mode](https://martendb.io/events/projections/)) runs only in the active region — on failover the new primary's daemon picks up from the last replicated `seq_id`. Same pitfalls as Kafka: loops in bidirectional setups, offset translation across promoted secondaries.

## 13. Real production architectures

| Company | Pattern | Substrate | Notes |
|---|---|---|---|
| **Netflix** | True active/active across regions; Cassandra ring spans regions | [Cassandra multi-DC async](https://medium.com/netflix-techblog/active-active-for-multi-regional-resiliency-c47719f6685b); EVCache with cross-region invalidation via SQS | Yury Izrailevsky: "redirect traffic if an entire region goes down." Traffic regularly shifted between US-East / US-West / EU for chaos testing |
| **Stripe** | Region-pinned account model; each account has a primary region | Mongo + bespoke; [Online Migrations at Scale](https://stripe.com/blog/online-migrations) describes the careful staging that re-homing accounts demands | Cross-border payments are sagas across pinned accounts |
| **Shopify** | [Pods](https://shopify.engineering/a-pods-architecture-to-allow-shopify-to-scale): "a pod is active in only one region at a time, and its non-active counterpart serves as a failover mechanism" | MySQL sharded into pods; "Sorting Hat" load-balancer routes by pod | Direct mapping onto region-pinned aggregates: each shop pinned to a pod-in-region |
| **Cloudflare** | One Durable Object per "aggregate", pinned to the region of first request | [Durable Objects](https://developers.cloudflare.com/durable-objects/) on the edge | Jurisdiction constraints force EU / FedRAMP boundaries while keeping global addressability |
| **Adyen / Wise** | Region-pinned customer accounts; sagas span pinned aggregates | Bespoke; Postgres + Kafka | Same pattern as Stripe |
| **Fauna** | True multi-region active/active with deterministic ordering | [Calvin protocol](https://fauna.com/blog/distributed-consistency-at-scale-spanner-vs-calvin) | Globally pre-ordered log replaces both `expectedVersion` and clock-based ordering |
| **Spanner-backed apps** | Strongly consistent multi-region writes | Spanner with TrueTime + Paxos | Pays per-write quorum latency for strict serializability |

The pattern: **the largest production systems all chose region pinning, not global multi-master.** Netflix is the prominent exception, and accepts LWW on a substrate (Cassandra) designed for it. Banking and payments converge on pinning; collab and presence converge on CRDT/LWW. Synchronous multi-region quorum (Spanner, CockroachDB GLOBAL tables) is reserved for read-mostly reference data, not the hot path.

## 14. Gotchas

- **Clock skew.** NTP-bounded drift is typically < 100 ms but spikes. Any `eventTimestamp` is at best approximate; use HLCs where ordering matters. Spanner's ~7 ms `commit-wait` ([TrueTime docs](https://docs.cloud.google.com/spanner/docs/true-time-external-consistency)) guarantees no two timestamps are out of order — every other system lives with the slop.

- **Asymmetric replication lag.** A→B might lag 200 ms; B→A might lag 1.5 s when B's outbound link is congested. Monitor lag *per direction*, not as a single number.

- **Replication loops.** Event from A replicates to B, B re-replicates to A, infinite loop. Defences: tag every event with `originRegion` and filter on ingress; topic renaming (MM2); tombstone/heartbeat events. *Test* this — the single most common multi-region bug.

- **Globally-unique idempotency keys.** A per-region `idempotencyKey` namespace breaks the moment two regions both generate `key-42`. Use UUIDs or region-prefixed (`eu:txn-2026-05-24-abc`). Dedup window must outlast cross-region replication lag.

- **Aggregate IDs.** Same rule: `account-{auto-increment}` works in one region, breaks in two. UUIDs, ULIDs, or region-prefixed Snowflake IDs.

- **Schema evolution across regions.** Roll out V2 in EU; US still emits/reads V1. Every cross-region projection must tolerate both versions for the full deployment window — days, not minutes. Versioned events (`OrderPlacedV2`) + upcaster in every consumer is the safe baseline.

- **Cross-region transfer compliance.** GDPR Art 44+ requires lawful basis for EU→non-EU transfers. SCCs + encryption-in-transit/at-rest are baseline; for sensitive data the [key-in-EU pattern](https://hazercloud.com/gdpr/) (encrypted bytes can leave, key cannot) is defensible. Schrems II's bar: would the destination jurisdiction's intelligence services have lawful access?

- **Operational.** Egress fees can dominate replication cost — a chatty event stream replicated across continents is a budget item. Different IAM domains, observability stacks, regional KMS endpoints. Cross-region tracing requires propagating trace IDs across the async boundary.

- **"Region of record" for audit.** When a regulator asks "show me everything you knew about user X on day Y", which region's log is canonical? Answer this *before* you need it. Usually the home region's, but you must also prove no replica diverged.

- **Backfills and replays.** A replay of `eu-*` streams from position 0 runs in EU, fine. But the resulting projection's side effects (emails, webhook callbacks) must be region-aware — a webhook to a US customer is a cross-region call. Plan replays as region-bounded operations.

## Cross-references

- [unbounded-and-infinite-streams.md §E — Branching / non-linear histories](../unbounded-and-infinite-streams.md#e-branching--non-linear-histories) — the taxonomy this doc lives under
- [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md) — sibling; substrate-level deep dive on Cassandra / DynamoDB / CockroachDB
- [federated-systems.md](federated-systems.md) — sibling; federation is multi-region taken to organisational extreme
- [../../concepts/collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md) — merge strategies in detail (LWW / OT / CRDT)
- [../../implementation-patterns/optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md) — why `expectedVersion` doesn't compose across regions
- [../../implementation-patterns/multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md) — saga shape; multi-region adds latency-as-failure-mode
- [../../implementation-patterns/subscriber-failure-strategies.md](../../implementation-patterns/subscriber-failure-strategies.md) — projection resilience, doubly important with replication lag
- [banking-and-finance.md](banking-and-finance.md) — cross-region transfer examples
- [ecommerce-and-retail.md](ecommerce-and-retail.md) — GDPR section, crypto-shredding patterns
