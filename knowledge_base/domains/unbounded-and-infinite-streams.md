# Unbounded & "Infinite" Streams — Domains Where Classical ES Hits a Wall

Most domain docs in this directory assume an aggregate has a natural lifecycle: a reservation gets cancelled, an order is delivered, a transfer settles. The escape hatches for long streams (snapshots, [closing-the-books](https://event-driven.io/en/closing_the_books_in_practice/)) work because there's a point where you *can* close the books.

This file is about the domains where that assumption breaks — where the stream has **no natural close**, **no obvious period boundary**, or **branches/diverges** instead of advancing linearly. The Google Docs / Sheets question is the canonical example: a single document edited continuously for years by many people, with concurrent operations, and no "DocumentClosed" event in sight.

Classical ES (one stream per aggregate, replay-from-zero, optimistic-locked appends) starts to fail in five distinguishable ways:

1. **Storage grows forever** — snapshots speed up replay but don't bound size.
2. **Write rate exceeds single-stream serial-append capacity** — telemetry, tick data, keystroke streams.
3. **History isn't linear** — concurrent edits, branches, multi-master merges.
4. **The "aggregate" has no closing event** — patient records, chat channels, social feeds.
5. **Retention is legally required to be forever** — healthcare, audit, land titles.

Below is a taxonomy of domains by *which* of these problems they hit. The point isn't that ES is wrong for these — it's that you need different tools ([CRDTs, OT, LWW](../concepts/collaborative-editing-ot-crdt-lww.md), log compaction, time-series stores, snapshot+truncate) than the per-aggregate stream model.

## A. Collaborative documents — every keystroke/operation is an event

The canonical "Google Docs problem". CRDT or Operational-Transform territory, not classical ES.

- **Word processing**: Google Docs, Word Online, Notion, Confluence, Quip
- **Spreadsheets**: Google Sheets, Excel Online, Airtable, Coda
- **Design / whiteboarding**: Figma, Miro, FigJam, Lucidchart, Excalidraw
- **CAD / 3D**: Onshape, Fusion 360 cloud, Tinkercad
- **Collaborative code editors**: VS Code Live Share, Replit multiplayer, JetBrains Code With Me
- **DAW / music collab**: BandLab, Soundtrap, Audiotool

**What hurts**: each user keystroke is an operation; one document over a year is millions of events. State may not even be totally ordered (concurrent edits from offline clients merge in arbitrary order).

**Toolkit shift**: CRDTs (Yjs, Automerge), Operational Transform (Google Docs' approach), per-section sub-streams, periodic snapshot + truncate of pre-snapshot operations.

## B. Long-running conversations & activity timelines — no end-of-life

The aggregate is alive for the lifetime of a *relationship* (an account, a channel, a profile), not a transaction.

- **Chat**: Slack channels, Discord servers, WhatsApp groups, Teams channels (some Slack channels have 1M+ messages)
- **Email**: mailboxes / threads spanning decades
- **Social feeds**: Twitter/X timelines, Facebook walls, Instagram profiles, TikTok activity
- **Forums**: Reddit megathreads, Hacker News, Discourse
- **Support tickets**: Zendesk/Intercom long-running cases, multi-year B2B accounts
- **CRM activity**: Salesforce / HubSpot account timelines (every email, call, meeting, deal-stage change)
- **Issue trackers**: Jira/Linear issues with thousands of comments/transitions
- **Wikis**: Wikipedia article histories, Confluence page revisions over a decade

**What hurts**: there's no `Closed` event because the relationship doesn't end.

**Toolkit shift**: time-bucketed sub-streams (`channel-{id}-2026Q2`), retention tiers (hot / warm / cold archive), separate "summary" projections that don't need full replay.

**Deep dives**: [specific/chat-and-messaging.md](specific/chat-and-messaging.md) (Slack/Discord/WhatsApp/Signal/Matrix/Telegram/XMPP/IRC) · [specific/social-feeds.md](specific/social-feeds.md) (Twitter/Facebook/Instagram/TikTok/Reddit/BlueSky/Mastodon).

## C. High-frequency telemetry — volume, not lifetime, is the killer

These often aren't ES'd at all. Raw signal goes to time-series stores (InfluxDB, TimescaleDB, ClickHouse, kdb+); only **derived events** (`DeviceWentOffline`, `ThresholdExceeded`, `MaintenanceDue`) land in the event store.

- **IoT / smart home**: Nest, Ring, smart meters, Hue, Matter devices
- **Industrial / SCADA**: factory PLCs, predictive maintenance, energy grids
- **Vehicle telemetry / fleets**: Tesla, connected-car platforms, trucking fleets, drone fleets
- **Healthcare wearables**: continuous glucose monitors, ECG patches, fitness trackers feeding clinical systems
- **Real-time games**: player input streams, world simulation
- **Observability**: app logs/metrics (already not ES — though OpenTelemetry traces are conceptually similar)

**What hurts**: 1–100 Hz × millions of devices. Even snapshots can't save you.

**Toolkit shift**: hot-path goes to TSDB; ES holds derived business events only. Same pattern as ride-sharing GPS pings (see [specific/ride-sharing-and-mobility.md](specific/ride-sharing-and-mobility.md)).

**Deep dive**: [specific/observability.md](specific/observability.md) — where ES applies in observability (alerts, incidents, SLOs, deployments, audit/SIEM) vs where it doesn't (raw spans, metrics, logs); OpenTelemetry data model; hot/cold/control-plane tiering across Datadog/Honeycomb/Grafana/Prometheus/Splunk/PagerDuty.

## D. Lifetime records that never naturally close

The *individual* aggregate is unbounded: 1 patient × 80 years × many encounters; 1 property × centuries of ownership transfers.

- **Healthcare / EHR**: patient record spanning decades; regulatory retention often *requires* immutable history
- **Education / LMS**: student academic record (Canvas, Blackboard, Workday Student)
- **Insurance**: life policies, multi-decade auto/home; claims open and close over years
- **Real estate / land titles**: chain of title forever (the use case blockchain land registries actually target)
- **Genealogy**: Ancestry, MyHeritage — events span centuries
- **Long-running subscriptions**: Netflix, gym memberships, SaaS contracts running 10+ years
- **Loyalty / membership programs**: airline frequent-flyer, hotel status (every flight/stay forever)
- **Government / civic**: voter records, court case histories, regulatory filings
- **Pets / livestock identity**: lifetime medical + ownership records
- **Audit / compliance logs**: SOX, HIPAA, PCI — many mandate multi-year append-only

**What hurts**: closing-the-books only partially helps — you still need queryable history, often legally.

**Toolkit shift**: period-sharded streams (`patient-{id}-{year}`) carrying summary events forward; cold archival to S3 Glacier / Azure Archive with index-only hot tier; PII handling strategies (crypto-shredding, tokenization) compatible with "forever" retention — see the GDPR section in [specific/ecommerce-and-retail.md](specific/ecommerce-and-retail.md).

**Deep dive**: [specific/long-running-subscriptions.md](specific/long-running-subscriptions.md) — Stripe Billing / Chargebee / Recurly / Zuora subscription state machines, billing-period as closing-the-books, dunning sagas, loyalty accumulators, ASC 606 revenue-recognition streams separate from cash streams.

## E. Branching / non-linear histories

These break the linear-stream model entirely. There isn't one true history.

- **Version control**: Git, Mercurial, SVN (Git is essentially ES with branches)
- **Smart contracts / blockchain**: Ethereum, Solana — global infinite append-only
- **Multi-master / distributed DBs**: CockroachDB, Cassandra ring history
- **Multiplayer game world state**: MMO server state with concurrent player actions
- **Federated systems**: ActivityPub (Mastodon), Matrix — events flow across servers
- **Multi-region replication**: any system with eventual cross-region merge

**What hurts**: you need merge semantics, not just append semantics.

**Toolkit shift**: CRDTs, three-way-merge, vector clocks, Lamport timestamps. The event store becomes a DAG, not a log.

**Deep dives**:
- [specific/version-control.md](specific/version-control.md) — Git as ES-with-a-DAG-not-a-log: commit-as-event, ref-as-aggregate, `git push` as compare-and-swap, history rewriting, patch-theory alternatives (Pijul/Darcs/jj), Git-as-event-store in production (Dolt/GitOps/Fossil).
- [specific/smart-contracts-and-blockchain.md](specific/smart-contracts-and-blockchain.md) — blockchain as planetary-scale adversarial multi-master ES: consensus as optimistic concurrency, reorgs as compensation, smart-contract events, indexers as projections, UTXO vs account vs object aggregate models.
- [specific/multi-master-distributed-dbs.md](specific/multi-master-distributed-dbs.md) — running ES on Cassandra/Dynamo/Cockroach/Spanner/Kafka: five flavors of multi-master, CDC + outbox, HLC, DB-as-ES vs DB-backed-ES.
- [specific/federated-systems.md](specific/federated-systems.md) — multi-master across independently-operated servers: Matrix room DAG + state resolution, ActivityPub inbox/outbox, AT Protocol per-user repo, Nostr signed events, defederation, advisory deletes.
- [specific/multi-region-replication.md](specific/multi-region-replication.md) — the latency tax, three architectural shapes, home-region pinning, cross-region sagas, GDPR/Schrems II partitioning, Kafka MirrorMaker 2, Netflix/Stripe/Shopify/Cloudflare deployments.

## F. High-throughput operational streams

ES might apply at the *business event* layer above, but the raw operational stream is too hot for a per-aggregate stream model.

- **Trading / market data**: tick streams, order books (LMAX, KX/KDB)
- **Payments at scale**: card-network switch volumes (TigerBeetle was built for exactly this — see [specific/banking-and-finance.md](specific/banking-and-finance.md))
- **Ad-tech**: bid streams, impression/click logs
- **CDN / web analytics**: every request from every edge node

**What hurts**: a single hot "stream" sees more writes per second than any optimistic-lock model can serialise.

**Toolkit shift**: purpose-built primitives (TigerBeetle, LMAX Disruptor); shard the logical stream into many physical streams; treat ES as the layer above the raw operation.

## Patterns that mitigate unbounded streams

The unifying technique across all six archetypes: **don't let one logical stream be one physical stream forever.** Some combination of:

- **Snapshots** — bound replay time, but storage still grows linearly. Necessary, not sufficient.
- **Period-sharding / closing the books** — `account-{id}-{period}` with `PeriodOpened{openingBalance}` / `PeriodClosed{closingBalance}`. Works when you can define a meaningful period.
- **Sub-stream by sub-entity** — Google Doc as N section/paragraph streams instead of one document stream. Figma file as per-frame streams.
- **Cold archival tiering** — recent + snapshot in fast storage; older events in cheap archive accessed only on replay / audit.
- **Compaction / squashing** — collapse `IncrementBy(1)` × 1000 into `IncrementBy(1000)` once the events are "settled". Kafka log compaction is the canonical example.
- **Hot-path / cold-path split** — raw signal to TSDB or in-memory store; only milestone events to ES. Used by every ride-sharing and IoT system.
- **CRDT / OT** — replace "single linear stream with optimistic locks" with "merge-able operations". Used by every collab editor.

The recurring shape: **the aggregate stays an aggregate, but its events get redirected, partitioned, summarised, or compacted before they accumulate without bound.**

## Which domains in this directory already touch these problems

| Domain doc | Archetype touched | Where it's addressed |
|---|---|---|
| [specific/banking-and-finance.md](specific/banking-and-finance.md) | D (lifetime), F (throughput) | Period-sharded streams, separate journal stream, TigerBeetle for hot accounts |
| [specific/ride-sharing-and-mobility.md](specific/ride-sharing-and-mobility.md) | C (telemetry) | GPS pings explicitly kept *off* the event store |
| [specific/food-ordering-and-delivery.md](specific/food-ordering-and-delivery.md) | C (courier location) | Same pattern — separate location topic with short retention |
| [specific/ecommerce-and-retail.md](specific/ecommerce-and-retail.md) | D (inventory streams that never close) | Period rollup (`inventory-{sku}-{warehouseId}-2026Q2`); GDPR vs immutability |
| [specific/hotel-and-hospitality.md](specific/hotel-and-hospitality.md) | — | Hotel domain has natural closes (checkout, year-end), so it doesn't hit this directly |
| [specific/spreadsheets.md](specific/spreadsheets.md) | A (collab docs) | Grid-as-doc vs row-as-record vs dimensional; OT/CRDT/LWW; per-section sub-streams |
| [specific/chat-and-messaging.md](specific/chat-and-messaging.md) | B (no-end-of-life) | Period-bucketed channel streams; reactions/threads as separate aggregates; E2E + the event store |
| [specific/social-feeds.md](specific/social-feeds.md) | B (no-end-of-life), E (federation) | Fan-out-on-write vs read; Timeline-is-a-projection-not-an-aggregate; BlueSky's per-user signed event log |
| [specific/long-running-subscriptions.md](specific/long-running-subscriptions.md) | D (lifetime) | Billing-period-as-closing-the-books; dunning sagas; loyalty accumulators with annual rollover |
| [specific/observability.md](specific/observability.md) | C (telemetry) | The clearest counter-example: ES applies to alerts/incidents/SLOs, NOT to raw spans/metrics/logs |
| [specific/version-control.md](specific/version-control.md) | E (branching) | "Git is ES where the event store is a DAG, not a log"; `git push` as compare-and-swap; rebase as derived aggregate |
| [specific/smart-contracts-and-blockchain.md](specific/smart-contracts-and-blockchain.md) | E (branching), F (throughput) | Consensus as planetary optimistic concurrency; reorgs as compensation; indexers as projection engines |
| [specific/multi-master-distributed-dbs.md](specific/multi-master-distributed-dbs.md) | E (branching) | The substrate question: when DB-as-ES, when DB-backed-ES, when CDC + outbox |
| [specific/federated-systems.md](specific/federated-systems.md) | E (branching) | Matrix DAG + state resolution; ActivityPub inbox/outbox; AT Protocol signed repos; advisory deletes |
| [specific/multi-region-replication.md](specific/multi-region-replication.md) | E (branching) | Latency tax; home-region pinning; cross-region sagas; GDPR partitioning |

## Domains still worth their own future doc

The archetypes most underserved by classical ES literature, where a dedicated deep-dive would still pay off:

- **Collaborative documents broader than spreadsheets (A)** — Figma/Notion/Miro/CAD with their distinctive per-object CRDT/LWW choices. The [spreadsheets doc](specific/spreadsheets.md) covers the grid case but the canvas/whiteboard/3D case has its own toolkit.
- **Healthcare / EHR (D)** — lifetime records with mandatory retention and PII constraints. Combines the unbounded-stream problem with the strongest regulatory pressure.
- **IoT / telemetry (C)** — every team building one of these has to learn the hot/cold split the hard way; [observability.md](specific/observability.md) covers the platform side but not the device fleet side.
- **High-throughput trading / market data (F)** — LMAX Disruptor, kdb+, the architectures behind tick-level event handling.
