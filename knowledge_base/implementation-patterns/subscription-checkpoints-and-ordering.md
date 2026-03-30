# Subscription Checkpoints, Ordering, and Parallel Processing

## How Subscriptions Guarantee Delivery

Events are durably stored in the event store. The subscription maintains a checkpoint — a position marker saying "I've processed up to event #N." If the process crashes, it restarts from the last checkpoint.

```
Event Store (immutable, durable):
  [0] CartConfirmed
  [1] OrderInitiated
  [2] PaymentCharged     <-- subscriber processed up to here, checkpoint = 2
  [3] InventoryReserved  <-- not yet processed
  [4] ShipmentRequested  <-- not yet processed
```

## Failure and Recovery

```
1. Subscription receives event #3
2. Handler tries to send command -> CRASH
3. Checkpoint was NOT advanced (still at #2)
4. Process restarts
5. Loads checkpoint: "last processed = #2"
6. Resumes from event #3 -> retries
7. Success -> checkpoint advances to #3
```

The checkpoint is only advanced after successful processing.

## At-Least-Once Delivery

Since the checkpoint advances after processing, a crash between processing and checkpointing means the event gets delivered again. Handlers must be **idempotent**.

```csharp
public void RecordGuestCheckoutCompletion(Guid guestStayId, DateTimeOffset now)
{
    // Already processed? skip.
    if (guestStayCheckouts[guestStayId] != CheckoutStatus.Initiated)
        return;
    Enqueue(new GuestCheckOutCompleted(Id, guestStayId, now));
}
```

## Ordering Strategies

The real requirement: **events for the same aggregate must be processed in order**. Events for different aggregates can safely be processed in parallel.

### Strategy 1: Sequential (default)

Process events one-by-one in global order. Safe but slow. Fine for low-to-medium volume.

### Strategy 2: Partitioned Parallel (the sweet spot)

Partition by stream name (= aggregate). Sequential within partition, parallel across partitions.

```
Partition 0 (Order-1):  [0] OrderPlaced -> [2] ItemAdded -> [5] OrderConfirmed
Partition 1 (Order-2):  [1] OrderPlaced -> [4] PaymentReceived
Partition 2 (Order-3):  [3] OrderPlaced

All three partitions process CONCURRENTLY.
Within each partition: SEQUENTIAL.
```

**Eventuous (C#)**:
```csharp
var partitionCount = 4;
builder.Services.AddSubscription<AllStreamSubscription, AllStreamSubscriptionOptions>(
    "BookingsProjections",
    builder => builder
        .Configure(cfg => cfg.ConcurrencyLimit = partitionCount)
        .AddEventHandler<BookingStateProjection>()
        .WithPartitioningByStream(partitionCount)
);
```

Custom partitioning:
```csharp
public delegate string GetPartitionKey(IMessageConsumeContext context);

builder => builder
    .Configure(cfg => cfg.ConcurrencyLimit = partitionCount)
    .WithPartitioning(partitionCount, MyCustomPartitionFunction)
```

**Axon Framework (Java)** — automatic via sequencing policies:
- Aggregate events -> `SequentialPerAggregatePolicy`
- Non-aggregate events -> `SequentialPolicy`

**Commanded (Elixir)**:
```elixir
defmodule MyEventHandler do
  use Commanded.Event.Handler,
    application: ExampleApp,
    concurrency: 10

  def partition_by(%OrderPlaced{order_id: id}, _metadata), do: id
end
```

### Strategy 3: Persistent Subscriptions (competing consumers)

Server-managed. Multiple consumers pull events. **No ordering guarantee.** Use only for integrations/notifications.

> Persistent subscriptions do not guarantee ordered event processing. We only recommend using them for integration purposes (reactions).

## Tradeoff Spectrum

```
<-- Safest                                           Fastest -->

Fully           Partitioned by       Persistent        Fully
Sequential      aggregate/stream     subscriptions     parallel
                                     (competing)
One-by-one      Sequential within    No order          Random
global order    partition, parallel  guarantee          order
                across partitions

                Best tradeoff
                for most cases
```

## How Checkpoints Work with Parallel Partitions

**Key insight: It's still just one checkpoint per subscription, even with partitions.**

Partitioning happens after reading. The subscription reads from the global `$all` stream with a single cursor. Partitioning is purely in-memory dispatch.

### The Gap Detection Problem

With parallel partitions, events finish out of order. You can only checkpoint up to the lowest position where all events at or below it have been fully processed.

```
Events read:     [0] [1] [2] [3] [4] [5] [6] [7]
Completed:        Y   Y   Y   Y   Y   N   Y   Y
                                      ^
                                   gap! [5] still processing

Safe checkpoint: 4  (everything up to 4 is done)

Later, [5] completes:
Safe checkpoint: 7  (jump forward)
```

**Eventuous CheckpointCommitHandler**:
```csharp
CommitPosition GetCommitPosition(bool force) {
    var pos = _lastCommit.Valid switch {
        true when _lastCommit.Sequence + 1 != _positions.Min.Sequence && !force
            => AtGap(),      // gap between last commit and list head
        _ => _positions.FirstBeforeGap()  // find highest contiguous position
    };
    return pos;
}
```

### Checkpoint Summary

| Scenario | Number of Checkpoints | How It Works |
|---|---|---|
| Sequential, one subscription | 1 value | Advances linearly |
| Partitioned parallel | 1 value + in-memory gap tracker | Advances to lowest contiguous completed |
| Multiple subscriptions | 1 per subscription | Each independent |
| Persistent subscription | 0 on your side | Server tracks it |

## Checkpoint Batching for Performance

Don't checkpoint after every event:

```csharp
public abstract record SubscriptionWithCheckpointOptions : SubscriptionOptions {
    public int CheckpointCommitBatchSize { get; set; } = 100;    // every 100 events
    public int CheckpointCommitDelayMs   { get; set; } = 5000;   // or every 5 seconds
    // whichever comes first
}
```

On crash, you may re-process up to ~100 events. Idempotency handles this.

## Where Checkpoints Are Stored

| Store | Example |
|---|---|
| Event store itself | Dedicated stream `checkpoint_{subscriptionId}` |
| Database table | MongoDB, PostgreSQL, SQL Server |
| Redis | For less critical subscriptions |

```csharp
// Checkpoint stored as event in its own stream
var @event = new CheckpointStored(subscriptionId, position, DateTime.UtcNow);
await eventStoreClient.AppendToStreamAsync(
    $"checkpoint_{subscriptionId}",
    expectedRevision,
    eventToAppend
);
```

## Sources

- [Eventuous — ESDB Subscription docs](https://github.com/eventuous/eventuous)
- [Eventuous — CheckpointCommitHandler.cs](https://github.com/eventuous/eventuous)
- [EventSourcing.NetCore — EventStoreDBSubscriptionToAll.cs](https://github.com/oskardudycz/EventSourcing.NetCore)
- [EventSourcing.JVM — EventStoreDBSubscriptionToAll.java](https://github.com/oskardudycz/EventSourcing.JVM)
- [Commanded — Event Handler](https://github.com/commanded/commanded)
