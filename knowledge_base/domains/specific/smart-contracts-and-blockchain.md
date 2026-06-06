# Smart Contracts & Blockchain as Event Stores

A blockchain is the most extreme event store ever built: a single global, distributed, append-only, cryptographically-linked log replicated across thousands of mutually-distrusting nodes, with consensus-driven write admission and no central operator. Every pattern classical ES practitioners know — optimistic concurrency, replay, snapshots, projections, subscriber failure, compensation — has a counterpart, stretched into adversarial multi-master territory. This is a field guide for ES engineers reading blockchain literature: what each concept maps to, where the lessons transfer, and where blockchain is a category error rather than an upgrade.

The archetype-E framing (branching / non-linear histories) is in [../cross-cutting/unbounded-and-infinite-streams.md](../cross-cutting/unbounded-and-infinite-streams.md). This doc is the concrete walkthrough.

## 1. The basic mapping

| Blockchain concept | Event-sourcing analogue |
|---|---|
| Block | Atomic batch of events at one logical timestamp |
| Transaction | Command + resulting event(s) bundled as one append-unit |
| Smart-contract emitted log (`emit Transfer(...)`) | Domain event on an aggregate stream |
| Contract address | Stream-id / aggregate-id |
| World state (balances, storage slots) | Materialised projection over the full log |
| State root (Merkle Patricia Trie root) | Cryptographic hash of the projection-at-block-N — a verifiable snapshot |
| Full node | Replica that replays the entire log |
| Light client | Projection consumer that trusts state roots without replaying |
| Indexer (The Graph, Subsquid) | Projection engine producing custom read models |
| Mempool | Command queue |
| Block proposer / sequencer | Single-writer coordinator inside one consensus round |
| Consensus (PoW / PoS / BFT) | Distributed agreement on the next `expectedVersion` |
| Reorg | Subscriber sees a tail of events un-happen, then re-happen differently |
| Hard fork | Schema migration requiring all replicas to upgrade |
| Finality | "Safe to project" watermark |
| Gas | Per-event admission cost / backpressure |

The single most important transfer of intuition: a Solidity `event Foo(...)` declaration **is** an event-sourcing event. `emit` is `appendToStream`. The block log of all `emit`s is the event store. Everything else — `eth_getLogs`, The Graph, Goldsky Mirror — is a projection-builder over that log. The Ethereum yellow paper makes this explicit: events are stored separately from state because they are append-only history; state is the derived projection.

## 2. Aggregate boundaries — three competing models

Blockchain protocols have spent fifteen years arguing over the right aggregate decomposition. Three live answers, each with a different ES tradeoff:

| Model | Chains | Aggregate primitive | Concurrency story |
|---|---|---|---|
| **UTXO** | Bitcoin, Cardano, Litecoin | One unspent output (`txid:vout`) — single-use, never mutated, only consumed | Two txs cannot spend the same UTXO → conflict on inputs, not on a global lock |
| **Account** | Ethereum, BSC, Avalanche, Polygon | Address with mutable `balance`, `nonce`, `storage` | Sequential `nonce` per account = per-aggregate optimistic concurrency |
| **Object / Resource** | Sui, Aptos, Move chains | Typed object with an owner; resources cannot be copied or silently dropped | Disjoint-object txs execute in parallel without consensus (Sui's "owned-object" fast path) |

Bitcoin's UTXO model is the closest blockchain analogue to what TigerBeetle does for hot accounts (see [banking-and-finance.md](banking-and-finance.md)): replace the mutable balance with a flat stream of immutable postings, derive the balance. Ethereum took the other path and pays for it with sequential per-account nonces that bottleneck on hot accounts.

Sui's Move object model is the most ES-friendly: each object has a unique id, owner, lifecycle, and per-object event log. Txs touching disjoint objects skip global consensus and use only reliable broadcast — the "different aggregate, no coordination" pattern at protocol level. Solana's [Sealevel runtime](https://solana.com/news/sealevel---parallel-processing-thousands-of-smart-contracts) reaches the same parallelism via a different door: every tx declares its read/write account set upfront, and the runtime schedules disjoint sets across cores.

## 3. Stream-id naming in the blockchain analogy

```
contract-{address}              # all events emitted by a single contract — the canonical aggregate stream
contract-{address}-{eventSig}   # one stream per event topic; how indexers subscribe
account-{address}               # mutations to an EOA's balance/nonce (Ethereum)
utxo-{txid}-{vout}              # Bitcoin: each UTXO is a one-event stream (born + consumed)
object-{objectId}               # Sui: per-object aggregate with explicit version
block-{height}                  # all events in a block — the global epoch stream
tx-{hash}                       # all logs from one transaction (commits/aborts atomically)
token-{contract}-{tokenId}      # ERC-721/1155 NFT — natural aggregate per token
```

A Graph subgraph manifest is literally "subscribe to stream `contract-{address}`, filter on `eventSig`, project into entity X" — same shape as an EventStoreDB persistent subscription, with a manifest file instead of a `SubscribeToStream` call.

## 4. Optimistic concurrency at planetary scale

Classical ES optimistic concurrency: "I read at version 17 and want to append; reject if the stream is now at 18." See [../../implementation-patterns/optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md).

Blockchain consensus is the same pattern at planetary scale:

- The "stream" is the chain. The "current version" is the latest block hash (content-addressed `expectedVersion`). An "append" is a proposed next block. A "conflict" is two proposers racing on the same parent.
- The "lock" is replaced by a consensus protocol — Nakamoto (probabilistic longest-chain), Tendermint BFT (deterministic two-thirds supermajority), LMD-GHOST + Casper FFG (Ethereum's Gasper), Tower BFT (Solana).

Per-account `nonce` is the inner per-aggregate concurrency layer: a tx with `nonce=42` is rejected if the account is at `nonce=43`. Ethereum stacks **two** concurrency layers: inner per-account nonce ordering (classical per-stream `expectedVersion`), and outer chain-level consensus on which block of nonce-ordered batches won the race. A failed inner check (wrong nonce, gas) is a rejected command — no event. A failed outer check (your block lost) is the same wire of events being re-played from a different proposer's batch — see reorgs.

## 5. Re-orgs as compensation

A reorganisation happens when a chain briefly considered canonical is replaced by a longer/heavier/finalised alternative. From an indexer's perspective:

```
T+0   block 1000 seen; indexer projects events e1, e2, e3
T+1   block 1001a built on 1000; e4, e5 projected
T+2   block 1001b (different parent hash, same height) wins consensus
      => UNAPPLY e4, e5
      => APPLY the new 1001b's events: e4', e5'  (possibly entirely different events!)
```

This is the **adversarial form** of the subscriber-failure pattern in [../../implementation-patterns/subscriber-failure-strategies.md](../../implementation-patterns/subscriber-failure-strategies.md). Classical ES projections can assume monotonic forward replay; blockchain projections must assume a tail of N blocks is **mutable history**. Every production indexer does one of:

- **Wait for finality**: don't project until the block is N confirmations deep (Bitcoin: 6 ≈ 1 hour; exchange-grade 30+).
- **Reversible projections**: keep per-block diffs so reverts are mechanical (Goldsky's [Mirror pipelines](https://goldsky.com/products/mirror) are reorg-aware; The Graph's `unapply` step processes block-handler reverts).
- **Reorg-tolerant read models**: project optimistically, surface "confirmed vs pending" and let the consumer choose.

The compensating-events principle from classical ES — "never delete; append a reversing event" — bends here. Inside the chain nothing is deleted; orphaned blocks just stop being canonical. But your **projection** must be rebuildable from a different prefix of the same log. Git-reset semantics applied to a live projection.

## 6. Finality — when can a projection trust an event?

| Finality model | Examples | "Safe to project" rule |
|---|---|---|
| **Probabilistic** | Bitcoin, Dogecoin, PoW | Wait N confirmations; reorg risk decreases exponentially, never to zero |
| **Deterministic BFT** | Tendermint / Cosmos, Algorand, Aptos | Final when two-thirds of validators sign; no reorg without breaking the protocol |
| **Hybrid PoS + finality gadget** | Ethereum post-Merge (Gasper) | Slot blocks are tip; justified checkpoints finalised after one more justified epoch — ~12.8 min |
| **Optimistic with challenge window** | Optimism, Arbitrum, Base | Sequenced instantly; L1-final only after the 7-day fraud-proof window |
| **Validity-proof** | zkSync, Starknet, Polygon zkEVM | L1-final when the validity proof verifies on L1 (minutes to hours) |

This is the blockchain concept with no clean classical-ES analogue: in regular ES, an event is "final" the moment `appendToStream` returns. On a blockchain there are *grades* of finality, and a projection must pick its grade based on value at risk. NFT marketplace: maybe 1 confirm. Exchange crediting a deposit: 30+ on Bitcoin or full finality on Ethereum. Rollup-to-rollup bridge: the entire 7-day window. The Ethereum [Gasper docs](https://ethereum.org/developers/docs/consensus-mechanisms/pos/gasper/): "blocks deeper than 2 epochs are considered finalized" — that is the projection-watermark for canonical L1.

## 7. Indexers as projection engines

The Graph, Subsquid, Goldsky, Alchemy Subgraphs, Covalent, and Envio all do the same job: subscribe to one or more contract event streams, run user-defined mapping code on each event, write the output to a queryable store. **Exactly** what every ES projection framework does (EventStoreDB catch-up subscriptions, Marten async daemon, Axon tracking event processors) — only over a public adversarial log.

| Indexer | Differentiator |
|---|---|
| **The Graph** | Decentralised network of indexers staking GRT; subgraph = manifest + GraphQL schema + AssemblyScript mappings; the default |
| **Subsquid** | Pulls from a decentralised "datalake" of pre-indexed blocks rather than RPC; batch-oriented squids optimised for historical backfills |
| **Goldsky** | Hosted subgraphs + Mirror pipelines streaming to external Postgres/Snowflake/Kafka; explicit reorg-handling |
| **Alchemy Subgraphs** (née Satsuma) | Drop-in compatible with The Graph; SLA'd hosted infrastructure |
| **Envio** | TypeScript-first hyperindexer; lower indexing latency |
| **Covalent** | Pre-built "unified API" indexes — generic projection rather than per-app subgraph |

A subgraph manifest is structurally identical to a projection registration:

```yaml
# subgraph.yaml — sketch
dataSources:
  - kind: ethereum
    source:
      address: "0xA0b86...EB48"     # stream we're subscribing to (USDC)
      abi: ERC20
      startBlock: 6082465           # subscription checkpoint
    mapping:
      eventHandlers:
        - event: Transfer(indexed address, indexed address, uint256)
          handler: handleTransfer    # the projector function
        - event: Approval(indexed address, indexed address, uint256)
          handler: handleApproval
```

In ES terms: register a catch-up subscription on stream `contract-0xA0b86...EB48` from checkpoint 6082465, with handlers for two event types. See [../../implementation-patterns/subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md).

## 8. Smart-contract events — the event shape

Solidity `event` declarations are user-defined event types. `emit` is the append. The on-wire encoding splits into **topics** (up to 4, indexed for filtering, hashed into the block's bloom filter) and **data** (ABI-encoded, not indexed). Topic 0 is the keccak256 of the event signature; topics 1-3 are user-marked `indexed` parameters.

```solidity
// canonical ERC-20 event — the most-emitted event in human history
event Transfer(address indexed from, address indexed to, uint256 value);
emit Transfer(msg.sender, recipient, amount);
```

```
Log {
  address:  0xA0b86...EB48                  # contract that emitted (stream-id)
  topics:   [ keccak256("Transfer(address,address,uint256)"),
              0x000...sender,
              0x000...recipient ]
  data:     0x...00000000000000000003e8     # uint256 = 1000
  blockNumber: 19450123
  blockHash:   0xabc...                     # mutable until finality (reorgs!)
  logIndex:    7
}
```

Load-bearing details ES engineers usually miss:

- Up to **3 indexed parameters** per event (topic 0 reserved for the signature). Indexed = filterable via the block-header bloom; non-indexed = retrievable only by full log read. Each indexed param costs ~375 extra gas — events have an explicit cost-per-byte classical ES does not.
- Logs are scoped to the **transaction receipt**, not contract storage. They live in the receipts Merkle root, not the state root. Two different roots commit two different things: state (current) and history (events).
- If the transaction reverts, all its logs are discarded — atomic batch, no half-events.
- Contract-emitted events and transaction receipts are **not the same**. `eth_getTransactionReceipt` returns status, gas used, contract-deployed address, plus the logs. ES projections typically consume only the logs.

## 9. Snapshots & state roots

In classical ES a snapshot is a serialised aggregate state cached so you can replay only events since the snapshot — optimisation, not source of truth.

On Ethereum the **Merkle Patricia Trie** root in each block header is a snapshot of the entire world state, committed cryptographically. Two properties classical snapshots don't have: **verifiable** (anyone can prove a specific account had a specific balance at block N via a Merkle proof against the published root, no trust needed) and **diffable** (state at N+1 differs from N by exactly the writes in N+1; the trie makes proving the difference cheap).

This is what **light clients** consume. A light client doesn't replay events. It downloads block headers (`stateRoot`, `transactionsRoot`, `receiptsRoot`), trusts the consensus rule for canonical-chain choice, then queries full nodes for Merkle proofs against the roots. In ES terms: a light client is a projection consumer that trusts a cryptographic snapshot and never touches the underlying log — analogous to a downstream service reading a periodically-published summary event without subscribing (Verraes's [Summary Event pattern](https://verraes.net/2019/05/patterns-for-decoupling-distsys-summary-event/)). Cosmos SDK uses an IAVL tree for the same role; Solana has no merkleised state by default — proofs are weaker, hence the lighter light-client story.

## 10. Throughput, hot aggregates, rollups

Monolithic L1s are rate-limited by global serialisation: Ethereum mainnet is one logical stream with ~15 TPS sustained. The planetary-scale version of TigerBeetle's hot-account problem — except the "hot account" is **the entire chain**.

The industry's response mirrors the ES pattern "shard the logical stream into many physical streams":

- **Optimistic rollups** (Optimism, Arbitrum, Base): a sequencer batches thousands of L2 txs and posts one compressed batch to L1 as a calldata or EIP-4844 blob. One L1 "event" = N L2 events — summary-event pattern at protocol level.
- **Validity (zk) rollups** (zkSync, Starknet, Polygon zkEVM): same batching plus a zk proof of correct execution — mathematical finality.
- **App-chains** (Cosmos zones, Polkadot parachains, Avalanche subnets): one bounded context per chain. Aggregate-boundary partitioning at the infrastructure layer — the most ES-shaped scaling strategy.
- **Sharding** (Ethereum's danksharding, Near): partition state across parallel chains with a coordination layer.
- **Account abstraction bundling** ([EIP-4337](https://eips.ethereum.org/EIPS/eip-4337)): a bundler packs many `UserOperation`s into one L1 tx to the singleton `EntryPoint` — N user commands → 1 chain-level batch.

Each is "the hot stream is too hot, partition it" at a different layer.

## 11. Determinism is required

Classical ES has a soft rule: events must produce deterministic state, because replay must reach the same answer on any replica. Most teams discover this only after a projection diverges from a `Random.nextInt()` or `LocalDateTime.now()`.

Blockchain enforces this at the protocol level. EVM, Solana's SVM, MoveVM, CosmWasm all forbid non-determinism: no system clock (only block timestamp), no network I/O, no random unless seeded from a deterministic source (block hash, VRF), strict gas accounting so execution terminates identically. Any non-determinism causes replicas to compute different state roots and fail consensus.

For ES practitioners: **if your event handler is non-deterministic, your projection is not a projection — it's a side-channel.** Blockchain makes the failure visible immediately (chain halts) instead of after six months of silently divergent reports.

## 12. What blockchain forbids that classical ES allows

| Operation | Classical ES | Blockchain |
|---|---|---|
| Delete an event | Possible (crypto-shredding, GDPR `Forgotten`) | Forbidden; chain is the regulatory record itself |
| Change an event schema | Versioning + upcasters | Hard fork — coordinated upgrade of every node |
| Rewrite history | Operator with restore + replay | Impossible without >50% of validators (even then, only outside finality) |
| Single-tenant operator decisions | Default | Impossible — every change is a consensus event |
| Selective replay (one tenant only) | Routine | Impossible — all replicas replay everything |
| Per-customer retention policies | Standard | None — the chain is forever |

The privacy-vs-immutability conflict is the sharpest version of a tension classical ES already has — see [`../cross-cutting/compliance-pii-and-immutability.md`](../cross-cutting/compliance-pii-and-immutability.md) for the cross-domain four-strategy taxonomy (crypto-shred / tombstone / tokenise / rewrite) and the regulatory regimes that drive each. On-chain answers: **crypto-shredding** (store ciphertext on-chain, hold the key off-chain, destroy the key to "forget" — recognised by EU data-protection authorities as effective erasure); **zkSNARKs / zkSTARKs** (prove a fact without revealing the underlying data); **shielded pools** (Tornado Cash, Zcash, Aztec — privacy by breaking the link between addresses, at the cost of complicating audit).

## 13. Where blockchain is genuinely useful as ES inspiration

- **Ledger systems with adversarial multi-master**: cross-organisation settlement (RippleNet, [Hyperledger Fabric channels](https://hyperledger-fabric.readthedocs.io/en/latest/fabric_model.html)) where no single party can be trusted to own the event store. Fabric is the closest enterprise analog: a permissioned blockchain where ordering nodes provide consensus and peer nodes maintain per-channel ledgers — "shared event store across N organisations" with classical KYC.
- **Audit logs needing third-party verifiability**: anchor your event-log Merkle root to a public chain (Bitcoin via OpenTimestamps, Ethereum via one hash tx per hour). Cheap external non-repudiation without exposing underlying events.
- **Supply-chain provenance**: when the audit trail must survive any one party going bust or hostile — IBM Food Trust, TradeLens, MediLedger. Trust assumption: no one party controls history.
- **Land titles / civic registries**: long-running immutable records where data lifetime exceeds operator lifetime (archetype D in [../cross-cutting/unbounded-and-infinite-streams.md](../cross-cutting/unbounded-and-infinite-streams.md)).

The test: **is the trust model "no single operator"?** If yes, blockchain's overhead justifies itself. If no, you're paying for a property you don't need.

## 14. Where blockchain is the wrong tool

Most enterprise ES use cases. Diagnostic checklist:

- Single legal entity is the source of truth → Postgres + ES, not a chain.
- Read latency budget under 1 s → on-chain reads are slow; indexers add 1-30 s of lag.
- Schema churns weekly → hard forks don't happen weekly.
- Per-user data privacy obligations → fight the immutability instead of leaning into it.
- Sustained throughput above ~1000 TPS on one logical aggregate → not on L1.
- No external counterparty needs to verify anything → no one cares about your state root.

Most "blockchain for X" pitches fail this checklist. A boring Postgres event store with periodic Merkle anchors to a public chain — if you genuinely need external verifiability — gets 95% of the audit value at 1% of the operational cost. Kurrent/EventStoreDB, Marten, Axon, and relational ES patterns remain the correct default; the chain is for the residual "no single trusted party" requirement.

## 15. Gotchas

- **Gas is rate-limit-as-economics.** Every event costs gas to emit; dapp authors design event shapes around gas, not domain modelling.
- **The reorg window is your projection's max-latency knob.** Too low and read models lie during reorgs; too high and the UI is slow. Goldsky exposes it as `numBlockConfirmations`.
- **Indexer lag is asymmetric.** Fresh blocks reach indexers in 1-5 s; historical backfills take days for multi-year contracts — the inverse of most classical projections.
- **MEV reorders events for profit.** Validators/searchers can insert, reorder, or front-run before sealing. The global ordering is adversarial; [Flashbots](https://docs.flashbots.net/) and private mempools mitigate but don't eliminate.
- **Transaction receipt ≠ contract event.** A successful tx may emit zero events; a failed tx emits none of its in-flight events (rolled back). Project from logs, not from "the transaction happened".
- **`blockHash` is mutable until finality.** A log keyed by `(blockHash, logIndex)` is not a stable id during the reorg window — use `(blockNumber, txHash, logIndex)` plus a depth flag.
- **Bloom filter false positives.** `eth_getLogs` is filtered through the block-header bloom — fast but lossy. Always validate matched logs.
- **State roots are global, not per-contract.** Per-contract snapshots are an indexer-level construct, not a chain primitive.
- **Solana log messages are not indexable.** Solana programs emit free-form `msg!()` strings — no bloom filter, no topics, no first-class event ABI. Don't blindly port Ethereum subgraph patterns to Solana.
- **Hard-fork coordination is brutal.** The Ethereum DAO fork (2016) split the network into ETH and ETC because validators refused the migration. Classical ES schema versioning looks tame.

## 16. Cross-references & sources

Cross-refs:
- [../cross-cutting/unbounded-and-infinite-streams.md](../cross-cutting/unbounded-and-infinite-streams.md) — archetype-E slot blockchain fills.
- [banking-and-finance.md](banking-and-finance.md) — TigerBeetle, ledger-as-event-log; same hot-account problem that motivates rollups.
- [../../implementation-patterns/optimistic-concurrency.md](../../implementation-patterns/optimistic-concurrency.md) — `expectedVersion` is per-account nonce here, block-hash there.
- [../../implementation-patterns/subscriber-failure-strategies.md](../../implementation-patterns/subscriber-failure-strategies.md) — reorgs are the adversarial form.
- [../../implementation-patterns/subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md) — subgraph `startBlock` + reorg rewind is checkpointing under hostile conditions.
- [version-control.md](version-control.md) — Git as DAG-shaped event store; both are append-only with branches.
- [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md) — consensus without blockchain's protocol cost.
- [multi-region-replication.md](multi-region-replication.md) — the same reorg-style merge problem at smaller blast radius.

Sources:
- **Ethereum** — [Yellow Paper](https://ethereum.github.io/yellowpaper/paper.pdf); [Merkle Patricia Trie](https://ethereum.org/developers/docs/data-structures-and-encoding/patricia-merkle-trie/); [Gasper](https://ethereum.org/developers/docs/consensus-mechanisms/pos/gasper/); [Casper FFG (eth2book)](https://eth2book.info/latest/part2/consensus/casper_ffg/).
- **Solidity events** — [Chainlink — Events and Logging](https://blog.chain.link/events-and-logging-in-solidity/); [RareSkills — Solidity Events](https://rareskills.io/post/ethereum-events); [web3.py Bloom Filters](https://snakecharmers.ethereum.org/bloom-filters/).
- **Indexers** — [The Graph quick start](https://thegraph.com/docs/en/subgraphs/quick-start/); [Subsquid docs](https://docs.subsquid.io/); [Goldsky Mirror](https://goldsky.com/products/mirror); [Alchemy — What is an indexer](https://www.alchemy.com/overviews/blockchain-indexer); [Envio benchmarks](https://docs.envio.dev/blog/best-blockchain-indexers-2026).
- **L2 / AA** — [Arbitrum Nitro](https://docs.arbitrum.io/how-arbitrum-works/inside-arbitrum-nitro); [Unchained — Sequencers](https://unchainedcrypto.com/what-are-sequencers-in-layer-2-protocols-such-as-optimism-arbitrum-and-base/); [ERC-4337](https://eips.ethereum.org/EIPS/eip-4337).
- **Solana / Sui / Cosmos** — [Sealevel](https://solana.com/news/sealevel---parallel-processing-thousands-of-smart-contracts); [Helius — Solana vs Sui lifecycle](https://www.helius.dev/blog/solana-vs-sui-transaction-lifecycle); [Tendermint ABCI](https://docs.tendermint.com/master/spec/abci/).
- **UTXO vs account** — [Alchemy — UTXO vs Account](https://www.alchemy.com/docs/utxo-vs-account-models).
- **Hyperledger Fabric** — [Fabric model](https://hyperledger-fabric.readthedocs.io/en/latest/fabric_model.html).
- **MEV** — [Flashbots docs](https://docs.flashbots.net/).
- **Privacy & GDPR** — [INATBA — ZKPs for GDPR Compliance](https://inatba.org/policy/inatba-publishes-position-paper-on-leveraging-zkps-for-gdpr-compliance/).
