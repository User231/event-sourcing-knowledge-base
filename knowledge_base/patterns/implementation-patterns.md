# Event Sourcing — Implementation Patterns

## Event Store Design Patterns

### Stream-per-Aggregate
The most common pattern. Each aggregate instance gets its own stream:
- `order-abc123` contains all events for order abc123
- `cart-user456` contains all events for user456's cart

### Category Streams
Group streams by type for cross-aggregate queries:
- `$ce-Order` is a virtual stream of all events across all order streams (EventStoreDB syntax)

### Global Event Log
Some stores maintain a single global ordering across all streams. Useful for projections that span multiple aggregates.

## Concurrency Control

### Optimistic Concurrency
When appending events, specify the expected version of the stream. If another write happened in between, the append fails and you retry:
```
Expected version: 5
Actual version: 6 → CONFLICT → re-read, re-validate, retry
```
This is the standard approach and avoids locks.

### Pessimistic Locking
Rarely used in event sourcing. Only consider for extremely contention-heavy aggregates.

## Event Versioning & Schema Evolution

### Problem
Events are immutable and stored forever. But your domain model evolves. How do you handle old event schemas?

### Strategies

**Weak Schema**: Store events as loosely-typed data (JSON). New fields have defaults, removed fields are ignored. Simple but fragile.

**Upcasting**: Transform old events to new schemas at read time. When loading events, a chain of upcasters converts v1 → v2 → v3 as needed. Events on disk stay unchanged.

**Event Mapping / Transformation**: Similar to upcasting but applied at the projection level. Each projection knows how to interpret old and new event formats.

**Copy-and-Replace (Stream Migration)**: Read all events, transform them, write to a new stream. Destructive to the original stream — use with caution.

**New Event Types**: Instead of changing `OrderPlaced_v1` to `OrderPlaced_v2`, introduce a new event type. Old projections handle old types, new projections handle both.

### Best Practices
- Make events as small and specific as possible (easier to evolve)
- Include a schema version in event metadata
- Prefer upcasting over stream migration
- Use a schema registry in larger systems
- Test backward compatibility in CI

## Snapshots

### When to Use
When aggregate streams grow very long (thousands of events) and rebuild time becomes a bottleneck.

### Implementation
1. After every N events (e.g., 100), save a snapshot of current state
2. When loading, find latest snapshot, then replay only events after that snapshot
3. Snapshots are optimization only — system must work without them

### Snapshot Storage
- Same event store (as a special event type)
- Separate snapshot store
- In-memory cache with persistence

## Saga / Process Manager

### Purpose
Coordinate long-running business processes that span multiple aggregates or bounded contexts.

### How It Works
1. Saga subscribes to events
2. When triggered, it issues commands to other aggregates
3. Tracks its own state (often event-sourced itself)
4. Handles compensating actions on failure

### Example: Order Fulfillment Saga
```
OrderPlaced → ReserveInventory command
InventoryReserved → ChargePayment command
PaymentCharged → ShipOrder command
PaymentFailed → ReleaseInventory command (compensation)
```

### Choreography vs Orchestration
- **Choreography**: Each service reacts to events independently. No central coordinator.
- **Orchestration**: A saga/process manager explicitly directs the flow.

## Projection Patterns

### Inline (Synchronous) Projections
Update read models in the same transaction as event persistence. Simpler but couples read/write performance.

### Async Projections
Read models updated by background workers subscribing to event streams. Allows independent scaling but introduces eventual consistency.

### Catch-up Subscriptions
Projections track their position in the event stream. On startup, they "catch up" from their last known position. This makes projections rebuildable.

### Live Projections
Built on-the-fly by replaying a stream. No persistence — useful for debugging, one-off queries, or testing.

## Testing Strategies

### Given-When-Then
The gold standard for testing event-sourced aggregates:
```
GIVEN [past events]          → sets up aggregate state
WHEN  [command]              → action under test
THEN  [expected new events]  → what should happen
```

### Projection Testing
```
GIVEN [stream of events]
WHEN  [projection processes them]
THEN  [read model state matches expected]
```

### Integration Testing
- Spin up an event store (in Docker)
- Write events, run projections, query read models
- Verify end-to-end behavior
