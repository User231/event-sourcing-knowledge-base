# Event Sourcing — Core Concepts

## What is Event Sourcing?

Event Sourcing is an architectural pattern where application state is determined by a sequence of events rather than by storing only the current state. Instead of updating a row in a database, you append an immutable event that describes what happened. The current state is derived by replaying all events from the beginning (or from a snapshot).

### Key Idea
Traditional: `UPDATE accounts SET balance = 150 WHERE id = 1`
Event Sourced: Append `MoneyDeposited { account_id: 1, amount: 50 }` to the event stream.

## Core Terminology

### Event
An immutable record of something that happened in the past. Events are facts — they cannot be deleted or modified. Examples: `OrderPlaced`, `PaymentReceived`, `ItemShipped`.

Events should be named in past tense (something that already happened).

### Event Stream (Event Log)
An ordered, append-only sequence of events for a specific aggregate or entity. Each stream has an identity (e.g., `order-123`). Events within a stream are ordered by version/sequence number.

### Aggregate
A cluster of domain objects treated as a single unit for the purpose of state changes. In event sourcing, the aggregate is the consistency boundary — it produces and consumes events. Each aggregate instance has its own event stream.

### Event Store
The database or storage system that persists event streams. An event store must support:
- Append-only writes
- Reading events by stream (optionally by position/version)
- Optimistic concurrency control (expected version checks)
- Optionally: global ordering, subscriptions, projections

### Projection (Read Model / View)
A derived representation of state built by processing events. Projections are disposable and rebuildable — if you lose them, replay the events. Different projections can present the same events in different shapes for different query needs.

### Snapshot
A cached version of aggregate state at a specific point in time, used to optimize replay performance. Instead of replaying 10,000 events, load the snapshot at event 9,950 and replay only the last 50.

### Command
A request to perform an action. Commands are validated against the current state (rebuilt from events) and, if accepted, produce one or more new events. Commands can be rejected; events cannot.

### CQRS (Command Query Responsibility Segregation)
A pattern often paired with Event Sourcing that separates the write model (commands → events) from the read model (projections). This allows independent optimization of reads and writes.

### Eventual Consistency
Since projections are built asynchronously from events, read models may lag behind the write model. This is a fundamental trade-off of event sourcing + CQRS architectures.

### Idempotency
The ability to process the same event or command multiple times without changing the result beyond the first application. Critical for reliable event processing in distributed systems.

## When to Use Event Sourcing

### Good Fit
- Audit trail / compliance requirements (finance, healthcare, legal)
- Complex domain logic with many state transitions
- Need to answer "how did we get here?" questions
- Time-travel debugging
- Systems where multiple read model shapes are needed
- Event-driven integrations between bounded contexts

### Poor Fit
- Simple CRUD applications
- When you only ever need current state
- High-frequency updates where event volume is extreme (consider carefully)
- When the team lacks experience and the domain doesn't justify the complexity
- Reporting-first systems where relational queries dominate

## Event Sourcing vs Event-Driven Architecture

These are different concepts often confused:
- **Event-Driven Architecture**: Components communicate via events (pub/sub). State might still be stored traditionally.
- **Event Sourcing**: State IS the sequence of events. Events are the source of truth, not just communication messages.

You can have event-driven architecture without event sourcing, and vice versa (though they pair well).
