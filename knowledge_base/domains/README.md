# Real-World Event Sourcing — Aggregate & Stream Decomposition by Domain

How production systems actually carve real domains into aggregates and streams. Each file in this directory is a field guide for one domain — concrete aggregate boundaries, stream-id patterns, key events, the canonical sagas, and the gotchas that bite teams once they leave the textbook.

Per the core rule (see [../concepts/core-concepts.md](../concepts/core-concepts.md) and [../implementation-patterns/multi-aggregate-commands-and-sagas.md](../implementation-patterns/multi-aggregate-commands-and-sagas.md)): **one command touches exactly one aggregate**. Decomposition therefore drives almost every downstream design choice — how you draw boundaries determines what your sagas, projections, and read models look like.

## Domains

### Industry / business domains

| File                                                                                       | Industries it covers                                                                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [specific/banking-and-finance.md](specific/banking-and-finance.md)                         | Retail/commercial banking, neobanks, payments, lending, ledger platforms (Monzo, Square, Wise, Modern Treasury, TigerBeetle)                                                                                                                 |
| [specific/ride-sharing-and-mobility.md](specific/ride-sharing-and-mobility.md)             | Ride-hailing, micromobility, on-demand delivery dispatch (Uber, Lyft, Grab, DoorDash, Lime/Bird)                                                                                                                                             |
| [specific/food-ordering-and-delivery.md](specific/food-ordering-and-delivery.md)           | Food delivery, grocery, restaurant POS integration (DoorDash, Uber Eats, Wolt, Instacart, Toast, Olo)                                                                                                                                        |
| [specific/ecommerce-and-retail.md](specific/ecommerce-and-retail.md)                       | Retail commerce, marketplaces, B2B platforms, inventory (Walmart, Shopify, Salesforce B2C, Zalando, ASOS, Mercado Libre)                                                                                                                     |
| [specific/hotel-and-hospitality.md](specific/hotel-and-hospitality.md)                     | PMS, OTA distribution, channel managers, group bookings (Booking.com, Mews, Marriott; Dudycz's canonical HotelManagement sample)                                                                                                             |
| [specific/long-running-subscriptions.md](specific/long-running-subscriptions.md)           | Subscription billing, dunning, proration, revenue recognition, loyalty/elite-tier accumulators (Stripe Billing, Chargebee, Recurly, Zuora, Paddle, Netflix, Spotify, telco postpaid, insurance, frequent-flyer)                              |

### Communication & social platforms

| File                                                                                       | What it covers                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [specific/chat-and-messaging.md](specific/chat-and-messaging.md)                           | Channels, threads, reactions, read state, presence, edits/deletes, E2E encryption (Slack, Discord, WhatsApp, Signal, Matrix, Telegram, XMPP, IRC)                                                                                            |
| [specific/social-feeds.md](specific/social-feeds.md)                                       | Posts, timelines, follow graphs, fan-out vs fan-in, reaction storms, algorithmic feeds, BlueSky AT Protocol, ActivityPub federation (Twitter/X, Facebook, Instagram, TikTok, LinkedIn, Pinterest, Reddit, BlueSky, Mastodon)                 |

### Collaboration tools & developer infrastructure

| File                                                                                       | What it covers                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [specific/spreadsheets.md](specific/spreadsheets.md)                                       | Collaborative spreadsheets — grid-as-document vs row-as-record vs dimensional models, formula dependency graphs, OT/CRDT/LWW collaboration, recompute sagas (Google Sheets, Excel Online, Airtable, Notion, EtherCalc, HyperFormula, Causal) |
| [specific/version-control.md](specific/version-control.md)                                 | VCS as event store — commit-as-event, ref-as-aggregate, DAG-not-log histories, optimistic CAS via `git push`, history rewriting, patch-theory alternatives (Git, Mercurial, SVN, Jujutsu, Pijul, Sapling, Fossil, Darcs, Dolt, GitOps)      |

### Systems & infrastructure as event stores

| File                                                                                       | What it covers                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [specific/observability.md](specific/observability.md)                                     | Where ES applies in observability (alerts, incidents, SLOs, deployments, audit/SIEM) vs where it doesn't (raw spans, metrics, logs); OpenTelemetry data model; hot/cold split (Datadog, Honeycomb, Grafana, Prometheus, Splunk, PagerDuty)  |
| [specific/smart-contracts-and-blockchain.md](specific/smart-contracts-and-blockchain.md)   | Blockchain as planetary-scale adversarial multi-master ES — consensus as optimistic concurrency, reorgs as compensation, smart-contract events, indexers as projections, UTXO vs account vs object models (Bitcoin, Ethereum, Solana, L2s)  |
| [specific/multi-master-distributed-dbs.md](specific/multi-master-distributed-dbs.md)       | When the substrate is multi-master — five flavors (leaderless quorum, consensus-per-shard, CRDT-native, log-as-DB, single-leader), CDC + outbox, HLC, DB-as-ES vs DB-backed-ES (Cassandra, Dynamo, Spanner, CockroachDB, Kafka, FoundationDB) |
| [specific/federated-systems.md](specific/federated-systems.md)                             | Multi-master across independently-operated servers — Matrix room DAG + state resolution, ActivityPub inbox/outbox, AT Protocol per-user repo, Nostr signed events, defederation, advisory deletes (Mastodon, Matrix, XMPP, email, Usenet)    |
| [specific/multi-region-replication.md](specific/multi-region-replication.md)               | The latency tax, three architectural shapes (single-writer/region-pinned/true multi-master), home-region pinning, cross-region sagas, GDPR/Schrems II partitioning, Kafka MM2 (Netflix, Stripe, Shopify, Cloudflare, Spanner, CockroachDB)   |

### Cross-cutting taxonomy

| File                                                                                       | What it covers                                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [unbounded-and-infinite-streams.md](unbounded-and-infinite-streams.md)                     | The six archetypes of domains where classical ES hits a wall (no natural close, hot-write, non-linear history, lifetime records, branching, high-throughput) and the patterns that bound them; the entry point for the deep-dive docs above |


## Patterns that recur across every domain

Read the per-domain files for specifics, but the same five forces show up everywhere:

1. **The "request" and the "thing requested" are different aggregates.** Reservation ≠ Stay. Cart ≠ Order. Authorization ≠ Posted withdrawal. They share data, not lifecycle. Conflating them is the canonical modelling mistake.
2. **High-volume telemetry doesn't go in event streams.** Driver GPS pings, courier locations, IoT sensors, page-view tracking — these live in hot stores (Redis/Kafka topics with short retention) and only **milestone** events get appended to the aggregate stream.
3. **Hot-write aggregates need sharding.** Fee accumulators, suspense accounts, flash-sale SKUs, popular ride-hailing geo-cells all blow up the single-stream optimistic-lock model. The fix is partition keys (`account-{id}-{period}`, `inventory-{sku}-{warehouseId}`, `surge-cell-{h3}-{minute}`) — not a bigger machine.
4. **"Closed" aggregates often get reopened.** Returns months after delivery. Chargebacks 60 days after settlement. Tip adjustments 24h after a ride. Never put an aggregate into a terminal-locked state until every regulatory/policy window has expired — or model the post-close events as their own aggregate (`Return`, `Dispute`, `TipAdjustment`).
5. **Compensation is event-shaped, not rollback-shaped.** A failed step in a saga doesn't undo earlier events; it appends new ones (`StockReleased`, `WithdrawalReleased`, `ReservingEntryPosted`, `FareAdjusted`). The audit trail tells you what happened *and* what unhappened. See [../implementation-patterns/multi-aggregate-commands-and-sagas.md](../implementation-patterns/multi-aggregate-commands-and-sagas.md).

## Heuristics for drawing aggregate boundaries

Distilled from Vaughn Vernon's [Effective Aggregate Design](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf) and observation across the domains here:

- **Different lifecycle → different aggregate.** If A can be deleted/cancelled/closed while B continues — they're different.
- **Different write frequency by 10×+ → different aggregate (or different store).** Catalog vs. price-changes; reservation vs. availability projection; courier-online vs. courier-location.
- **Different consistency window → different aggregate.** Same transaction (auth a card) vs. eventually consistent (settle the network file).
- **Different audit/compliance scope → different aggregate.** PCI scope, KYC scope, GDPR scope, GAAP scope.
- **Different actor / team owns it → different aggregate.** Distribution team owns Reservation; front-desk team owns GuestStay.

**When in doubt, lean larger.** Splitting later means introducing a saga and relaxing an invariant you used to enforce — both reversible but invasive. Merging two streams later is closer to a one-time data migration. Most teams over-split early because "aggregates should be small" sounds prudent; they then spend a year reintroducing coordination they didn't need. The signals above are when to commit to a split, not a license to split on suspicion.

## Where to look in the cloned repos

Real worked examples available locally in `repos_cloned/`:

- **Hotel** (the richest sample): `oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/` — three variants (saga / choreography / process-manager) of the canonical GroupCheckout flow.
- **E-Commerce**: `oskardudycz_EventSourcing.NetCore/Sample/ECommerce/` — ShoppingCart, Order, Shipment, Payment with their interactions.
- **Shopping Cart** (focused): `oskardudycz_EventSourcing.NodeJS/` and `oskardudycz_EventSourcing.JVM/samples/event-sourcing-esdb-aggregates/`.
- **Bank Account** (basic, intentionally so): `oskardudycz_EventSourcing.JVM/workshops/build-your-own-event-store/solved/src/test/java/bankaccounts/`.
- **University / Faculty** (course bookings, capacity invariants): `AxonFramework_AxonFramework/examples/university-java/`.
- **Booking + Payment** (multi-service): `eventuous_eventuous/samples/postgres/Bookings/`.

