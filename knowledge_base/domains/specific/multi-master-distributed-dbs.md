# Multi-Master / Distributed Databases as Event Stores

Classical ES assumes a **single serialiser per stream**: every append goes through one logical writer that enforces `expectedVersion`, increments a counter, and produces a totally ordered log. Multi-master DBs — Cassandra, ScyllaDB, DynamoDB, CockroachDB, Spanner, YugabyteDB, FoundationDB, Riak, Couchbase, MongoDB sharded, TiDB, Kafka — solve the same "concurrent writes to shared state" problem with **completely different primitives**: no single serialiser, no `expectedVersion`, no central log. Each node accepts writes; reconciliation happens by gossip, quorum, consensus per shard, or CRDT merge.

This doc covers what changes when the substrate underneath your event store is one of these — both when you build ES *on top of* a multi-master DB, and when you treat the DB's *internal replication log* as the event stream (CDC).

Related: [unbounded-and-infinite-streams.md §E](../unbounded-and-infinite-streams.md#e-branching--non-linear-histories) on branching histories; [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md) for the LWW/OT/CRDT primitives; [optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md) for the `expectedVersion` contract these DBs do or don't preserve.

## 1. Every multi-master DB is already event-sourced under the hood

Strip the CRUD veneer off any distributed DB and you find machinery indistinguishable from an event store:

| ES primitive | What the DB calls it |
|---|---|
| Append-only log | Commit log (Cassandra), WAL (Postgres/Cockroach), oplog (Mongo), Raft log (Cockroach/Yugabyte), Kafka topic-partition |
| Stream / aggregate | Partition key + clustering key (Cassandra), row + version (Cockroach), document + CAS (Couchbase), key + vector clock (Riak), tablet (Yugabyte) |
| Event | Mutation (Cassandra cell), Raft log entry, MVCC row version, CRDT operation, Kafka record |
| Subscription / catch-up | Change feed (Cockroach), Debezium, DynamoDB Streams, Couchbase DCP, Kafka consumer group |
| Optimistic concurrency | `IF NOT EXISTS` / `IF version=?` (Cassandra LWT), DynamoDB `ConditionExpression`, Couchbase CAS, FoundationDB OCC read-conflict-range |

The internal log is real and observable: Debezium reads Postgres WAL / MySQL binlog / Mongo oplog; DynamoDB Streams expose item mutations; Cassandra has CDC log files; CockroachDB has `CHANGEFEED FOR TABLE`. The substrate of a "CRUD database" is an event log — the API just doesn't let you append events directly with stream semantics.

This is what makes multi-master DBs attractive as ES substrates and treacherous in equal measure. You inherit a battle-tested replicated log, but the contract it exposes (CRUD with conflict resolution) is not the contract ES needs (append-with-version against a single serialiser).

## 2. The five flavors of distributed DB

| Flavor | Examples | Conflict resolution | ES guarantee you can build |
|---|---|---|---|
| **Single-leader** | Postgres streaming, MySQL async, Mongo primary, EventStoreDB cluster | None — replicas catch up from one leader | Classic `expectedVersion` on the leader |
| **Leaderless quorum (Dynamo-style)** | Cassandra, ScyllaDB, DynamoDB, Riak, Voldemort | LWW by timestamp; or siblings / CRDT (Riak) | Per-partition LWT/Paxos for `expectedVersion`; expensive |
| **Consensus-per-shard (Raft/Paxos)** | CockroachDB, YugabyteDB, Spanner, TiDB, etcd, Consul | Strong (single leader per range, log-replicated) | True linearizable per stream; `expectedVersion` works naturally |
| **CRDT-native** | Riak DT, AntidoteDB, Redis Enterprise CRDB, SoundCloud Roshi | Mathematical merge (counter, set, register, map) | Counters / sets converge; aggregates needing invariants don't |
| **Log-as-database** | Kafka, Pulsar, AWS Kinesis, Redpanda | Partition order is the only order | Kafka *is* an event log; one stream per partition or many per partition |

The flavor decides which ES patterns are available. Leaderless quorum cannot give cheap `expectedVersion`; consensus-per-shard can. CRDT-native gives mergeable counters but cannot enforce "balance ≥ 0". Kafka gives a perfect log per partition but no random-access by stream id.

## 3. Aggregate boundaries when the DB is the substrate

Classical ES aggregate boundary is a *transactional consistency boundary* — one stream, one optimistic lock, one append point ([Vernon — Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf)). On a multi-master DB this maps onto **one partition key per aggregate**, because the partition is the only place the DB will give you any transactional primitive at all.

| DB | Per-aggregate primitive | Cross-aggregate primitive |
|---|---|---|
| Cassandra / Scylla | LWT (Paxos) per partition | None — multi-partition LWT batches not supported |
| DynamoDB | `ConditionExpression` on item; `TransactWriteItems` ≤100 items | `TransactWriteItems` same region, cost/latency penalty |
| Cockroach / Yugabyte / Spanner | Distributed SQL txn across any rows | Same — 2PC, HLC clock skew |
| FoundationDB | Strict-serializable txn ≤10MB / ≤5s, across any keys | Same — single-resolver makes cross-key the normal case |
| Riak DT | Per-key CRDT operation | None — CRDTs converge, they don't transact |
| Kafka | Per-partition order; transactional writes across partitions in one producer | Cross-partition only inside one Kafka cluster; no read isolation |
| Couchbase | Per-document CAS | Multi-document ACID in 7.0+ within a cluster |

**Rule of thumb**: choose `partition-key = streamId` and never let a single command touch two partition keys. Crossing partitions means either (a) a distributed transaction at 2–3× latency (Cockroach/Spanner/FDB), (b) lost atomicity (Cassandra/Riak/Kafka without producer transactions), or (c) the full saga / process manager treatment regardless of the DB (see [multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md)).

The danger is subtle: a Cassandra LWT *looks* like `expectedVersion` and works correctly inside one partition, but a developer who batches LWTs across partitions believing they're transactional will silently get partial commits. The DB will not stop them.

## 4. Stream-id naming when DB partitioning is the substrate

Stream id and partition key collapse into the same identifier:

```
# Cassandra / DynamoDB / Scylla — partition key = stream id
PRIMARY KEY ((stream_id), version)            # version is clustering key, ordered

# Kafka — topic + key; key hashes to a partition
topic: account-events;  key: account-{accountId}    # all events for one account in one partition

# Cockroach / Yugabyte — primary key is the stream + sequence
PRIMARY KEY (stream_id, version)              # range-partitioned; one range owns the stream

# Riak — bucket = stream type, key = stream id; CRDT map per key
bucket: accounts; key: account-{accountId}
```

**The hot-partition trap** is the same problem [banking-and-finance.md §2 high-contention accounts](banking-and-finance.md#2-stream-id-naming-patterns) warns about, visible at a different layer. A single fee-accumulator stream becomes a single Cassandra partition, hashes to a single Dynamo shard, lands in a single Kafka partition — and that node sees 100% of the traffic. Mitigations:

- **Sub-stream by time bucket**: `account-{id}-{yyyyMMddHH}` — Dudycz's "closing the books" ([event-driven.io](https://event-driven.io/en/closing_the_books_in_practice/)) expressed as partition keys instead of stream ids.
- **Composite key with a salt**: `(account-{id}-{shard0..N}, version)`, reproject across shards.
- **Cassandra wide-row anti-pattern**: never make the partition key monotonic (a day, an event type); you get one hot partition per day. See [Aphyr — The trouble with timestamps](https://aphyr.com/posts/299-the-trouble-with-timestamps).
- **Kafka partition count = aggregate parallelism**: increasing it later requires re-keying; over-provision rather than re-partition.

## 5. Conflict resolution mapped to OT / CRDT / LWW

The mechanism each flavor uses to reconcile concurrent writes is the same taxonomy collaborative-editing systems use. See [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md) for the full primitives.

| Mechanism | DBs that use it | ES impact |
|---|---|---|
| **LWW by wall-clock timestamp** | Cassandra, ScyllaDB, DynamoDB (per-attribute), Couchbase XDCR | Two concurrent appends with same `expectedVersion` both succeed in their region; on merge, one event is **silently dropped** |
| **LWW by HLC** | CockroachDB, YugabyteDB, Mongo recent, Couchbase 7.6+ (HLV) | Same as above but causal violations less likely; still loses one write |
| **Vector clocks / DVVs** | Riak (default since 2.0), Voldemort | Application must resolve siblings; not transparent — you write merge code |
| **CRDT operation merge** | Riak DT, AntidoteDB, Redis CRDB | Counter/set/register aggregates merge cleanly; invariants like "balance ≥ 0" can't be enforced |
| **Single-leader log order** | Postgres, Mongo primary, Kafka per-partition | True `expectedVersion`; loss of leader = brief unavailability (CAP: C over A) |
| **Raft/Paxos per shard** | Cockroach, Yugabyte, Spanner, TiDB, FoundationDB (single resolver) | True `expectedVersion`; cross-shard txn pays 2PC latency |

LWW is the default substrate semantics for the four most-deployed multi-master DBs (Cassandra, DynamoDB, Couchbase XDCR, Mongo eventual reads), and **LWW is incompatible with naïve ES**. Two concurrent `WithdrawalPosted` events with the same `expectedVersion = 7` both succeed at version 7 in different regions; the LWW merge picks one timestamp and discards the other event. The "drop" is silent — no error, no sibling, no log line. This is the canonical failure mode and the core argument in [Kleppmann — A Critique of the CAP Theorem](https://arxiv.org/abs/1509.05393).

## 6. CDC: the DB-write log AS the event stream

The alternative framing: don't build ES on top of the DB — let the DB's existing replication log *be* your event stream. **Change Data Capture** turns row inserts/updates/deletes into a Kafka topic. Debezium reads Postgres WAL, MySQL binlog, Mongo oplog, SQL Server CDC tables, and emits one Kafka record per row mutation.

Trade-offs:
- **Pro**: zero application change; the DB and the stream cannot disagree because there's literally one log.
- **Con**: events are CRUD-shaped (`UserUpdated{before, after}`), not domain-shaped (`EmailChanged{reason}`). Downstream consumers reverse-engineer intent from diffs.
- **Con**: source-schema migrations cascade into stream-schema breakage.

The **outbox pattern** is the bridge. Application writes both business state and a domain event into the same DB transaction, into an `outbox` table. Debezium tails the outbox and publishes (domain-shaped) events to Kafka. The dual-write problem dissolves: the DB transaction commits both rows or neither.

```
INSERT INTO accounts (id, balance) VALUES (...)         -- business state
INSERT INTO outbox (aggregate_id, type, payload, version)
  VALUES ('account-42', 'WithdrawalPosted', '{...}', 8) -- domain event
COMMIT                                                  -- atomic
                ↓ Debezium tails outbox
            Kafka topic: account-events
```

[Morling — Reliable Microservices Data Exchange](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/), [Debezium Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html), [Decodable — Revisiting the Outbox Pattern](https://www.decodable.co/blog/revisiting-the-outbox-pattern). Modern variants (Materialize, RisingWave) treat the CDC stream itself as a materialised-view input.

## 7. Optimistic concurrency in multi-master

The classical contract — `append(streamId, expectedVersion, events)` rejects on version mismatch — has analogues in every multi-master DB, but cost and semantics differ. See [optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md) for the canonical contract.

```cql
-- Cassandra LWT (Paxos)
INSERT INTO events (stream_id, version, payload) VALUES ('account-42', 8, ?)
  IF NOT EXISTS;                                        -- 4-round Paxos per write
```
```js
// DynamoDB conditional write
await ddb.put({ TableName: 'events',
  Item: { stream_id: 'account-42', version: 8, payload },
  ConditionExpression: 'attribute_not_exists(version)'  // single-region linearizable
})
```
```sql
-- Cockroach / Spanner / Yugabyte — vanilla SQL; Raft underneath gives real linearizability
INSERT INTO events (stream_id, version, payload) VALUES ('account-42', 8, $1);
```

| DB | Concurrency primitive | Latency vs normal write | Cross-region |
|---|---|---|---|
| Cassandra LWT | Paxos (4-round; v2 ≈ 2-round uncontended) | 4–10× slower | Cross-DC depends on `SERIAL` |
| DynamoDB `ConditionExpression` | Item-level CAS | ≈1× | Single-region by default; Global Tables are LWW |
| Cockroach / Yugabyte / Spanner | Raft commit + serializable txn | 2–3× normal, geo-distributed | Linearizable inside one cluster |
| Couchbase CAS | Per-document; no Paxos | ≈1× | XDCR is LWW |
| Riak DT | None — CRDTs replace it | n/a | Eventually converges; no rejection |
| Kafka | Idempotent producer + transactions | ≈1× | Per-partition only |

DynamoDB and Couchbase forms look cheapest because they *only* hold within one region. Turn on Global Tables / XDCR and the `Condition` check passes locally while the conflicting write from another region wins-or-loses by LWW timestamp. **Optimistic concurrency on a multi-master DB is regional, not global, unless you've paid for consensus.**

## 8. Cross-region multi-master is its own problem

Multi-master *within* a DC is solvable (Raft/Paxos shards). Multi-master *across* regions is a different problem: speed-of-light latency makes synchronous consensus painful (50ms London↔Frankfurt RTT is the floor on every write), so most operators pick async replication and accept LWW or CRDT merge across regions even with Raft inside a region. CockroachDB's [`SURVIVE REGION FAILURE`](https://www.cockroachlabs.com/docs/stable/multiregion-overview.html) makes the cost explicit. Spanner pays it with TrueTime. Cassandra and Dynamo Global Tables sidestep it with LWW. See sibling `multi-region-replication.md` (when written) for the full treatment.

## 9. Kafka as event-store substrate

Kafka is the awkward middle case: it *is* a distributed log, partitioned and replicated; it has linearizable order within a partition; it has idempotent producers and producer transactions. But it is not random-access by stream id, and a topic is not an "aggregate stream" in the EventStoreDB sense.

Two distinct patterns dominate:

**(a) Kafka IS the event store (Confluent / ksqlDB pattern).** One topic per aggregate type (`accounts`, `orders`), aggregate id as the message key. All events for one aggregate land in one partition, ordered. Reads use Kafka Streams or ksqlDB to materialise current state into a RocksDB-backed state store on each node ([Confluent — Is Kafka a Database? With ksqlDB](https://www.confluent.io/blog/is-kafka-a-database-with-ksqldb/)). Optimistic concurrency is implemented either by a single-writer process per partition (no contention possible) or by idempotent-producer + transactional outbox. The trap: no native indexed lookup of "give me all events for stream X" — you scan the partition. The state store is the only practical read path. See [Eugene Khyst — ksqldb-event-sourcing](https://github.com/eugene-khyst/ksqldb-event-souring).

**(b) Kafka is the transport, a real ES store is the system of record.** Application appends to EventStoreDB / Marten / message-db with proper `expectedVersion`; an outbox/CDC pipeline relays them to Kafka for downstream consumers ([EventStoreDB vs Kafka — Domain Centric](https://domaincentric.net/blog/eventstoredb-vs-kafka)). Concurrency is enforced by the ES store; Kafka does fanout. The more common production shape because it keeps the strong contract.

Pattern (a) is what Walmart's real-time inventory does at 500M events/day ([Confluent — Walmart inventory](https://www.confluent.io/blog/walmart-real-time-inventory-management-using-kafka/)): Kafka holds the log, Kafka Streams + Cassandra hold projections. Pattern (b) is what most fintech / hotel / e-commerce shops do.

## 10. Pitfalls of LWW for ES

Cassandra-style LWW interacts badly with ES in ways that are silent and only visible months later in audit replay:

- **Same-millisecond conflicts**: Cassandra timestamps are microseconds, but `System.currentTimeMillis()` is ms; two events from the same client in the same ms collide and one wins by tiebreaker, not user intent. Use the driver's monotonic timestamp generator.
- **Clock skew across application nodes**: client-generated timestamps can travel backwards. An event at T=100 from node A and T=99 from skewed node B projects as if B happened first. [Aphyr — The trouble with timestamps](https://aphyr.com/posts/299-the-trouble-with-timestamps) is the definitive treatment.
- **Wide-row anti-pattern**: `(eventType, day)` as partition key creates one hot partition per day. Fix: composite keys with a salt or hashed bucket.
- **Tombstones from event deletion**: never delete events. Cassandra tombstones from "fixing" bad events create read-amplification and eventual `TombstoneOverwhelmingException` in scans.
- **Read-repair changes history during replay**: replaying a stream via `SELECT *` during catch-up can trigger read-repair that rewrites timestamps; depending on consistency level, the same stream "from the past" can differ between two replays.

**LWW silently drops events, and ES requires events are never silently dropped.** Either accept it (the events that survived are the truth — fine for some collab/CRDT-shaped domains) or pay for LWT / consensus / single-leader.

## 11. DB-backed ES vs DB-as-ES

| | DB-backed ES (EventStoreDB / Marten / message-db on Postgres) | DB-as-ES (events directly to Cassandra / DynamoDB / Kafka) |
|---|---|---|
| Append API | `append(streamId, expectedVersion, events)` — first-class | `INSERT … IF NOT EXISTS` / `ConditionExpression` — reimplemented per project |
| Per-stream reads | Indexed by streamId — fast | Indexed by partition key — fast if you partition right |
| Catch-up subscriptions | Native (`$all`, persistent subscriptions) | Built on CDC / DynamoDB Streams / Kafka consumers |
| Optimistic concurrency | Built in | LWT / CAS / Raft txn per stream — per-DB syntax |
| Cross-region | Vendor feature (clustering, Postgres logical replication) | Inherited from the DB (Global Tables, XDCR, multi-region clusters) |
| Lock-in / portability | Higher (vendor schema) | Lower; you own the schema |
| Wins when | Throughput per-stream is modest; want batteries-included ES | You already operate the DB at scale and need ES at the same scale |

[Marten optimistic concurrency](https://martendb.io/documents/concurrency.html), [message-db on Postgres](https://github.com/message-db/message-db), [Eventide on Postgres vs EventStore](https://medium.com/eventide-project/which-backend-database-to-use-with-eventide-postgres-or-event-store-c510360871b4), [Postgres ES reference](https://github.com/eugene-khyst/postgresql-event-sourcing).

## 12. Real production patterns

| Company | Substrate | Notes |
|---|---|---|
| Netflix (Downloads) | Cassandra | Snapshots + replay; chosen for scalability over native ES features ([InfoQ — Scaling ES for Netflix Downloads](https://www.infoq.com/presentations/netflix-scale-event-sourcing/)) |
| Walmart (Inventory) | Kafka + Cassandra | 500M events/day; Kafka Streams primary, Cassandra holds projections ([Confluent — Walmart inventory](https://www.confluent.io/blog/walmart-real-time-inventory-management-using-kafka/)) |
| Monzo | Cassandra + Kafka | Multi-currency ledger reconciled against settlement account ([Monzo — Processing payments safely at scale](https://monzo.com/blog/2022/02/08/processing-payments-safely-at-scale)) |
| Revolut | In-house ES on Postgres | Per-aggregate version, no Kafka ([Architecture of a Neobank](https://news.abnasia.org/blog/posts/en-architecture-of-a-neobank-revolut-3689)) |
| Sky / many others | Postgres + Marten / message-db | Single-leader Postgres with `expectedVersion`; outbox to Kafka for fanout |
| Klarna | Kafka-centric | Heavy Kafka Streams / KTable usage as projection substrate |
| Modern Treasury | Postgres | Optimistic locking in the API ([Designing Ledgers with Optimistic Locking](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking)) |
| The Mill Adventure | DynamoDB | ES at scale on DynamoDB conditional writes ([AWS blog](https://aws.amazon.com/blogs/architecture/how-the-mill-adventure-implemented-event-sourcing-at-scale-using-dynamodb/)) |
| Many fintech | Cockroach / Spanner | Multi-region linearizable; `expectedVersion` semantics like Postgres but geo-distributed |

The pattern: **single-leader stores (Postgres / EventStoreDB) for high-invariant domains (banking, hotel, e-commerce orders); multi-master stores (Cassandra / Kafka / DynamoDB) for high-throughput projection/log domains (telemetry, retail-scale inventory, devices) and for systems that have scaled past one Postgres**. When [banking-and-finance.md](banking-and-finance.md) talks about TigerBeetle and distributed ledgers, it's the same pivot — at the throughput where one stream's optimistic lock becomes the bottleneck, you change substrates.

## 13. Gotchas

- **Timestamp resolution & clock skew**: ms-granularity client clocks lose collision tiebreakers. Use HLCs where supported (Cockroach, Yugabyte, Mongo, Couchbase 7.6+), or a driver-side monotonic timestamp generator. NTP is necessary but not sufficient; TrueTime is the only system that bounds skew with hardware.
- **Partition imbalance**: any monotonic partition key (timestamp, sequence, alphabetical ids) creates hot partitions. Salt, bucket, hash-prefix.
- **Cross-partition reads**: in Cassandra a `SELECT … WHERE stream_id IN (...)` scatter-gathers; in DynamoDB a `Query` is per-partition. Replays needing "all events ordered globally" are linear in cluster size — pre-compute a projection.
- **GDPR & immutable replicas**: replicas are by definition copies, so "right to be forgotten" deletion fans out to every replica and every CDC consumer downstream. Standard answer is crypto-shredding (encrypt PII with a per-subject key, delete the key) — works on every substrate. See [unbounded-and-infinite-streams.md §D](../unbounded-and-infinite-streams.md#d-lifetime-records-that-never-naturally-close).
- **Cost of LWT**: a Cassandra LWT is 4× a normal write (Paxos v2 ≈ 2×). On hot streams this is back to the same bottleneck classical ES has. The bottleneck doesn't disappear when you change DBs — it moves.
- **Jepsen reports**: the only honest way to find out which DBs deliver their consistency claims. [MongoDB 4.2.6](https://jepsen.io/analyses/mongodb-4.2.6) failed snapshot isolation even at strongest concerns; [Cassandra LWTs](https://jepsen.io/analyses/cassandra-lwts) have had Paxos linearizability violations; CockroachDB has fixed stale-read bugs. Read the report for the DB before adopting it as your ES substrate.
- **Schema evolution and CDC**: source-table schema changes propagate into CDC streams; downstream consumers see field renames as add+remove. Use the outbox pattern to keep the *event* schema decoupled from the *table* schema.
- **Multi-region writes look strong, are LWW**: DynamoDB Global Tables, Cassandra multi-DC, Couchbase XDCR all silently degrade `ConditionExpression` / LWT semantics to LWW across regions. Always check whether the concurrency primitive is regional or global.
- **PACELC** ([Abadi](http://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf)): CAP only covers behaviour during partitions; the tradeoff that governs every-day writes is consistency-vs-latency Else. ES'd on a leaderless quorum means *every* append pays one or the other.

## 14. Hybrid Logical Clocks — the modern answer for cross-master ordering

HLCs (Kulkarni, Demirbas et al., 2014) are the compromise between wall-clock timestamps (cheap, lose causality) and Lamport clocks (preserve causality, drift arbitrarily from wall time). An HLC is a 64-bit timestamp = physical-component + logical-counter; when two events have causal dependency the logical counter advances; when they don't, the physical part stays close to NTP time.

This is the basis of consistent multi-master ordering in CockroachDB ([HLC timestamps](https://www.cockroachlabs.com/glossary/distributed-db/hybrid-logical-clock-hlc-timestamps/)), YugabyteDB ([Distributed Transactions](https://docs.yugabyte.com/stable/architecture/transactions/transactions-overview/)), MongoDB (since causally consistent sessions), and Couchbase 7.6+'s Hybrid Logical Vector. For an ES substrate, HLC means **two concurrent appends to the same stream from different regions are deterministically ordered, and the ordering is causal-consistent with wall-clock intuition**. It does not by itself solve `expectedVersion` (you still need Raft/Paxos/LWT to *reject* the loser) but it makes LWW dramatically safer where you must use it.

For ES on Cassandra/Dynamo without HLC native support, projects can carry HLCs in the event payload itself — the substrate stays oblivious; the *application* uses HLC to break ties and detect causal violations on replay.

## Sources

- **Dynamo paper** — Vogels et al., [Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf). Architectural ancestor of Cassandra, Riak, Voldemort.
- **Spanner** — [Google's Globally-Distributed Database](https://research.google/pubs/spanner-googles-globally-distributed-database/).
- **CockroachDB** — [The Resilient Geo-Distributed SQL Database](https://rcs.uwaterloo.ca/~ali/cs854-f23/papers/cockroachdb.pdf).
- **FoundationDB** — [paper](https://www.foundationdb.org/files/fdb-paper.pdf); [How FoundationDB works](https://uvdn7.github.io/notes-on-the-foundationdb-paper/).
- **Cassandra LWT** — [AxonOps — Paxos v2 and LWT](https://axonops.com/blog/paxos-v2-and-lightweight-transactions/); [DataStax LWT docs](https://docs.datastax.com/en/cassandra-oss/3.0/cassandra/dml/dmlLtwtTransactions.html).
- **Riak CRDTs** — [Distributed Data Types](https://docs.riak.com/riak/kv/2.2.3/learn/concepts/crdts/index.html); [Vector Clocks Revisited Pt 2 (DVVs)](https://riak.com/posts/technical/vector-clocks-revisited-part-2-dotted-version-vectors/index.html).
- **Couchbase XDCR** — [XDCR Conflict Resolution](https://docs.couchbase.com/server/current/learn/clusters-and-availability/xdcr-conflict-resolution.html); HLV in 7.6+.
- **DynamoDB ES** — [The Mill Adventure on DynamoDB at scale](https://aws.amazon.com/blogs/architecture/how-the-mill-adventure-implemented-event-sourcing-at-scale-using-dynamodb/); [DynamoDB conditional writes for ES](https://blog.fkan.se/net/dynamodb-as-an-event-store/).
- **Kafka as ES** — [EventStoreDB vs Kafka](https://domaincentric.net/blog/eventstoredb-vs-kafka); [ksqlDB event sourcing reference](https://github.com/eugene-khyst/ksqldb-event-souring); [Is Kafka a Database? With ksqlDB](https://www.confluent.io/blog/is-kafka-a-database-with-ksqldb/).
- **Debezium / CDC** — [Debezium architecture](https://debezium.io/documentation/reference/stable/architecture.html); [Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html); [Morling — Reliable Microservices Data Exchange](https://debezium.io/blog/2019/02/19/reliable-microservices-data-exchange-with-the-outbox-pattern/); [Decodable — Revisiting the Outbox Pattern](https://www.decodable.co/blog/revisiting-the-outbox-pattern).
- **PACELC** — Abadi, [Consistency Tradeoffs in Modern Distributed Database System Design](http://www.cs.umd.edu/~abadi/papers/abadi-pacelc.pdf).
- **Kleppmann** — [A Critique of the CAP Theorem](https://arxiv.org/abs/1509.05393); *Designing Data-Intensive Applications* chapters 5 and 9.
- **HLC paper** — Kulkarni, Demirbas et al., [Logical Physical Clocks and Consistent Snapshots in Globally Distributed Databases](https://cse.buffalo.edu/tech-reports/2014-04.pdf).
- **Jepsen** — [jepsen.io/analyses](https://jepsen.io/analyses) — the only honest source for whether a DB delivers its claimed consistency model.
- **Aphyr** — [The trouble with timestamps](https://aphyr.com/posts/299-the-trouble-with-timestamps); [Strong consistency models](https://aphyr.com/posts/313-strong-consistency-models).
- **Netflix on Cassandra ES** — [Scaling Event Sourcing for Netflix Downloads](https://www.infoq.com/presentations/netflix-scale-event-sourcing/); [CDC for Distributed Databases @ Netflix](https://www.infoq.com/presentations/netflix-cdc-events-cassandra/).
- **Walmart on Kafka+Cassandra** — [How Walmart Uses Apache Kafka for Real-Time Replenishment](https://www.confluent.io/blog/how-walmart-uses-kafka-for-real-time-omnichannel-replenishment/).
