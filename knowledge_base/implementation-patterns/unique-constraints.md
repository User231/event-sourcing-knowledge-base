# Unique Constraints in Event Sourcing

## The Problem

Event stores are append-only and don't support set-based validation (e.g., "email must be unique across all users"). Traditional unique indexes don't exist on the write side.

## Key Concept: Stream ≠ Aggregate

A stream is just an ordered sequence of events with an ID. An aggregate *uses* a stream, but not every stream is an aggregate. Streams can also represent:
- Sagas / process managers
- Technical concerns (reservations, locks)
- Projections, categories

This distinction matters because the reservation pattern creates streams that are not domain aggregates — they are concurrency guards.

## Approaches

### 1. Projection-Based Check (Simple, Eventually Consistent)

Query a read-side projection with a unique index before accepting a command.

```sql
CREATE TABLE user_emails (
  email VARCHAR UNIQUE,
  user_id UUID
);
```

```
Command → SELECT from projection → If exists, reject → Append event
```

- No extra streams or aggregates
- Aggregate keeps its normal UUID
- **Race condition window**: two concurrent commands can both pass the check before the projection updates
- Acceptable when duplicates are extremely unlikely or detectable after the fact

### 2. Reservation Pattern (Strong Consistency)

The standard robust solution. Uses a dedicated reservation stream per unique value, leveraging the event store's optimistic concurrency on stream creation.

#### Flow

```
1. Reserve:   appendToStream("email-res-{hash}", [EmailReserved], expectedRevision: NO_STREAM)
2. Register:  appendToStream("user-{uuid}", [UserRegistered])
3. Confirm:   appendToStream("email-res-{hash}", [ReservationConfirmed])
```

`expectedRevision: NO_STREAM` guarantees only one writer wins — if two requests try to reserve the same email, only one succeeds.

#### The reservation stream is NOT a domain aggregate

- It has no business logic or `apply()` methods
- It exists purely to exploit optimistic concurrency on stream creation
- Your `User` aggregate keeps its normal UUID
- If unified IDs matter, hash the value: `uuidv5(email, NAMESPACE)`

#### Failure Scenarios and Cleanup

| Scenario | What happens | Cleanup |
|---|---|---|
| Reservation fails (stream exists) | Someone else claimed the value | Reject command. Nothing to clean up |
| Reservation succeeds, registration fails | Orphaned reservation | TTL-based expiry releases it |
| Both succeed, confirmation fails | User exists, reservation unconfirmed | Process manager retries confirmation, or TTL cleanup |

#### Tracking Pending Reservations

You cannot efficiently scan all streams in most event stores. A **read-side projection** tracks pending reservations:

```sql
CREATE TABLE pending_reservations (
  resource_key VARCHAR PRIMARY KEY,
  reserved_at TIMESTAMP,
  expires_at TIMESTAMP,
  status VARCHAR  -- 'pending' | 'confirmed'
);
```

Built by an event handler listening to reservation events (e.g., via category subscription `$ce-email-reservation`):

```typescript
on('EmailReserved', (e) => {
  db.insert('pending_reservations', {
    resource_key: e.resourceKey,
    reserved_at: e.reservedAt,
    expires_at: e.reservedAt + TTL,
    status: 'pending'
  });
});

on('ReservationConfirmed', (e) => {
  db.update('pending_reservations', e.resourceKey, { status: 'confirmed' });
});

on('ReservationReleased', (e) => {
  db.delete('pending_reservations', e.resourceKey);
});
```

A **background job** queries for expired reservations and appends `ReservationReleased` events:

```sql
SELECT resource_key FROM pending_reservations
WHERE status = 'pending' AND expires_at < NOW();
```

#### Full Architecture

```
Event Store (source of truth)          Read Side (queryable)
┌─────────────────────────┐           ┌─────────────────────┐
│ email-res-{hash} stream │──handler─→│ pending_reservations │
│  - EmailReserved        │           │ table (with expiry)  │
│  - ReservationConfirmed │           └──────────┬──────────┘
│  - ReservationReleased  │                      │
└─────────────────────────┘           background job queries
                                      expired rows → emits
                                      ReservationReleased
```

### 3. DB-Level Constraint on Event Store

Some stores (e.g., Marten with `NaturalKeyTable`) support unique indexes on projections inline with the event store. Strong consistency, but couples you to the store implementation.

## When to Use What

| Approach | Consistency | Complexity | Use when |
|---|---|---|---|
| Projection check | Eventually consistent | Low | Duplicates are unlikely and detectable |
| Reservation pattern | Strongly consistent | Medium | Uniqueness is a hard business requirement |
| DB-level constraint | Strongly consistent | Low | Your event store supports it natively |

## Sources

- [Oskar Dudycz — Uniqueness sample (Java)](https://github.com/oskardudycz/EventSourcing.JVM/tree/main/samples/uniqueness)
- [Set-Based Consistency Validation in Event Sourcing](https://event-driven.io/en/uniqueness-in-event-sourcing/)
