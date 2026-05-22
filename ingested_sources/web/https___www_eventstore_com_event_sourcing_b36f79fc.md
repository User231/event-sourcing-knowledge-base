# Event Sourcing Database â Built for It, Not Bolted On

Source: https://www.eventstore.com/event-sourcing

# The only database purpose-built for event sourcing.

Stop building an event store from scratch. Start with one that's already complete.

Start Free Trial

## Free Trial

  Request Trial License

### Stop fighting

Immutability, ordering, streaming, and projections are native capabilitiesânot bolted on like with CRUD databases.

### Ship faster

No designing schemas, building subscriptions, or debugging concurrency. Start with a working event store on day one.

### Simplify your stack

One purpose-built platform instead of five. Fewer moving parts, fewer failure modes.

## 50M+

DOWNLOADS

## F500

DEPLOYMENTS

## Î¼s

LATENCY

## 99.9%

UPTIME

## SOC 2

CERTIFIED

The Problem 

## "I feel like I'm battling my database"

When organizations implement event sourcing with general-purpose databases like PostgreSQL, MongoDB, or Cassandra, they quickly discover these databases weren't designed for event-driven patterns. What starts as "we'll just store events in a table" becomes months of custom development across six critical areas.

### Schema & Data Model Design

General-purpose databases have no native concept of event streams. Teams design custom schemas from scratchâevent tables with aggregate IDs, sequence numbers, and payload columns.

### Third-Party Libraries or Custom Code

Without native support, teams adopt third-party libraries or build custom implementations. Either path means your event store is only as reliable as non-core code.

### Ordering & Consistency Guarantees

Event sourcing depends on strict orderingâwithin streams and globally. General-purpose databases don't provide this automatically. Teams must implement sequence generation and handle failures.

### Concurrency Control

When multiple processes append events simultaneously, you need optimistic concurrency control. General-purpose databases require custom implementationâerror-prone code with silent data corruption as the consequence.

### Real-Time Streaming Infrastructure

General-purpose databases offer limited or no native streaming. Teams bolt on external message brokersâdoubling operational complexity and creating synchronization challenges.

### Projection & Read Model Management

Events need transformation into read models. General-purpose databases require external frameworks, custom microservices, or batch jobsâplus checkpoint management and synchronization logic.

## Building an Event Store is a Burden

Specialized Knowledge

Development Time

Ongoing Maintenance

Infrastructure Focus

System Fragility

Tech Debt

The Solution 

## A database that's designed to store events

KurrentDB is the database that speaks event sourcing natively. With 12+ years of continuous development and hundreds of production deployments, it delivers native capabilities that eliminate the complexity, performance compromises, and operational overhead of retrofitting traditional databases.

### Native Immutable Event Streams

Every event is immutable and stored in append-only streams that preserve complete history. This isn't a feature bolted onâit's the fundamental architecture.

Impact

Zero data loss. Reconstruct any past state, audit every change, replay any outcome.

### Built-In Global Event Ordering

Strict ordering within streams and global consistency across the entire event store. Every event receives a unique, monotonically increasing position.

Impact

Eliminates complex application-level sequencing. Event order is guaranteed, not hoped for.

### Multi-Stream Atomic Appends

Append events to multiple streams atomically in a single transaction, eliminating saga patterns and complex coordination logic.

Impact

Run and manage KurrentDB yourself with full control and support.

### Native Real-Time Subscriptions

Built-in pub/sub powers real-time event flows with catch-up subscriptions (replay from any point) and persistent subscriptions (competing consumers)âno external brokers required.

Impact

Reactive architectures without adding message brokers or messaging infrastructure to your stack.

### Advanced Projections Engine

Process, transform, and link events in real-time directly within the database. Like stored procedures for event streamsâtriggered by new data, executed in-database.

Impact

Eliminates external stream processing frameworks. Event transformations run where the events live.

### Optimistic Concurrency Built-In

Native concurrency control prevents lost updates without pessimistic locking. Specify expected versions; the database rejects mismatched writes automatically.

Impact

No events silently lost to concurrent modifications. High-throughput writes without locking overhead.

### Sophisticated Event Indexing

Multi-tier indexing with dedicated entries per stream enables direct lookups. Custom indexes create virtual views by any event property without duplicating data.

Impact

Sub-millisecond retrieval regardless of database size. New query patterns through configuration, not code.

### Unlimited Event Retention

Events stored indefinitely by defaultânever automatically deleted. Tiered archiving moves older events to cloud storage while maintaining transparent read-through access.

Impact

Complete audit trail without retention limits. Balance storage costs without sacrificing historical accessibility.

### Enterprise-Ready & Production-Proven

Encryption at rest, RBAC, ISO 27001 and SOC2 Type II compliance. Official client libraries for .NET, Node.js, Python, Java, Go, and Rust.

Impact

12+ years of battle-tested stability across hundreds of production deployments. Mission-critical ready.

How It Works 

## KurrentDB's event-native data model

KurrentDB stores events in fine-grained streams with unique keys per streamâscalable to billions of streams without data duplication. Each event captures time as a key element, enabling global ordering across streams and intra-stream causation. Every append triggers a new stream version for optimistic concurrency, ensuring durable writes of atomic events with unique identification within and across streams.

## KurrentDB in an event sourced application

In an event-sourced architecture, commands flow through deciders that determine state changes, which are persisted as events to KurrentDB. The event store serves as the single source of truth, with projections transforming events into read-optimized models for queries. Reactions listen to events and trigger updates to external systemsâall with immediate consistency for commands and eventual consistency for projections and reactions.

[More about KurrentDB](/kurrentdb)  [Read Docs](https://docs.kurrent.io/)

The Kurrent Difference 

## Plug-and-play vs. infrastructure project

General-purpose databases were designed around CRUDâthey assume you'll overwrite data as state changes. Event sourcing requires the opposite: append-only storage where history is never lost. Retrofitting CRUD databases means fighting their core design. KurrentDB was purpose-built for event sourcing, eliminating the complexity tax entirely.

##### Other DBs

## Kurrent

Enforced manually

Immutability

Native

Custom schema

Native Eventâ¨Streams

Built-in

Custom implementation

Global Eventâ¨Ordering

Guaranteed

Custom logic

Optimisticâ¨Concurrency

Native

Limited or external tools

Real-Timeâ¨Subscriprions

Native

External tools

Server-Sideâ¨Projections

Built-in

Varies, often limited

Event Retention

Unlimited + archiving

Complex or unavailable

Multi-Streamâ¨Atomicity

Native

Immutability

Enforced manually

Native

Native Eventâ¨Streams

Custom schema

Built-in

Global Eventâ¨Ordering

Custom implementation

Guaranteed

Optimisticâ¨Concurrency

Custom logic

Native

Real-Timeâ¨Subscriprions

Limited or external tools

Native

Server-Sideâ¨Projections

External tools

Built-in

Event Retention

Varies, often limited

Unlimited + archiving

Multi-Streamâ¨Atomicity

Complex or unavailable

Native

## Deploy Your Way

Choose the deployment model that fits your needs

Recommended

#### Kurrent Cloud

Focus on your application while we manage the infrastructure.

  [Sign Up (No credit card required)](https://identity.eventstore.com/login?state=hKFo2SB2VDJFblBMRnlHbFdhOUVwc3ZTRXY0bkFVN0FBWmZicKFupWxvZ2luo3RpZNkgSk9EWU5VZF9kYmhEVm15RUZ4WUNyNE4wNGFPeEhpY2qjY2lk2SBCZW1SUHJmYVNvVGxsQld5VHExcHR2aWk1UTc4T3d4dw&client=BemRPrfaSoTllBWyTq1ptvii5Q78Owxw&protocol=oauth2&audience=https%3A%2F%2Fapi.kurrent.cloud&initial_tab=sign_up&redirect_uri=https%3A%2F%2Fconsole.kurrent.cloud%2Fcallback&response_type=code&scope=openid%20profile%20email%20offline_access%20cloud%3Aaccess%20cloud%3Aadmin%20cloud%3Aadmin-viewer)

#### Kurrent Enterprise

Run and manage KurrentDB yourself with full control and support.

Start Free Trial (30-days free)

## Free Trial

  Request Trial License

#### Kurrent Community

Develop locally with core functionality.

  [Download now](https://docs.kurrent.io/server/v26.0/quick-start/installation.html)

## Tired of DIY event sourcing?

Talk to an Expert

## Talk to an Expert

  Get in Touch