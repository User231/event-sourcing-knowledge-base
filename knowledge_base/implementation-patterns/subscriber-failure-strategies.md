# Subscription Handler Failure Strategies

## Handler Return Statuses

Handlers don't just succeed or fail — they return explicit statuses:

| Status | Meaning | What Happens |
|---|---|---|
| `Success` | Handled OK | Event is ACK'd, checkpoint advances |
| `Ignored` | Not relevant to this handler | Treated as success (no-op) |
| `Failure` | Handler error | Event is NACK'd — what happens depends on config |

> The subscription will acknowledge the event only if all of its handlers don't fail.

> It's preferred to return `EventHandlingStatus.Failure` instead of throwing an exception. The `EventHandler` base class will return failure status automatically if the handler throws.

## Two Core Behaviors on Failure

### Option 1: Swallow the Error (default in Eventuous)

The subscription logs the error and moves on. The checkpoint still advances. The failed event is effectively skipped.

```csharp
catch (Exception e) {
    context.LogContext.MessageHandlingFailed(Options.SubscriptionId, context, e);
    if (Options.ThrowOnError) throw;  // only throws if explicitly configured
    // otherwise: logs and continues to next event
}
```

`ThrowOnError` defaults to `false`. The subscription keeps running — one bad event doesn't block everything else.

### Option 2: Stop the Subscription (`ThrowOnError = true`)

The subscription stops processing. The checkpoint doesn't advance. On restart, it retries the same event.

```csharp
public abstract record SubscriptionOptions {
    public bool ThrowOnError { get; set; }  // default: false
}
```

This creates a **poison message** problem: if the event always fails, the subscription is stuck forever.

## Strategies to Handle Failures

### 1. Retry with Backoff

Wrap handlers with a retry policy (e.g., Polly):

```csharp
builder.Services.AddSubscription<AllStreamSubscription, AllStreamSubscriptionOptions>(
    "OrderSaga",
    builder => builder
        .AddEventHandlerWithRetries<OrderSagaHandler>(
            Policy
                .Handle<Exception>()
                .WaitAndRetryAsync(3, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)))
        )
);
```

Subscription-level retry (for connection drops):

```csharp
var generalPolicy = Policy.Handle<Exception>(ex => !IsCancelledByUser(ex))
    .WaitAndRetryForeverAsync(
        sleepDurationProvider: _ =>
            TimeSpan.FromMilliseconds(1000 + new Random().Next(1000)),
        onRetry: (exception, _, _) =>
            logger.LogWarning("Subscription was dropped: {Exception}", exception)
    );
```

### 2. Dead Letter Queue

After retries are exhausted, park the event and move on:

**Marten** (built-in):
```csharp
foreach (var @event in eventRange.Events)
{
    try
    {
        await hubContext.Clients.All.SendAsync(@event.EventTypeName, @event.Data, ct);
    }
    catch (Exception exc)
    {
        // Park the event — don't block the subscription
        await subscriptionController.RecordDeadLetterEventAsync(@event, exc);
    }
}
```

**Axon Framework** (Java):
```java
private EnqueueDecision<EventMessage> onError(
    DeadLetter<? extends EventMessage> letter, Throwable cause
) {
    logger.warn("Processing dead letter [{}] failed.", letter.message().identifier(), cause);
    return enqueuePolicy.decide(letter, cause);  // retry later, discard, or re-enqueue
}

private EnqueueDecision<EventMessage> onSuccess(
    DeadLetter<? extends EventMessage> letter
) {
    logger.info("Dead letter [{}] processed successfully.", letter.message().identifier());
    return Decisions.evict();  // remove from dead letter queue
}
```

### 3. Persistent Subscription NACK (server-side)

With EventStoreDB persistent subscriptions, you ACK/NACK at the protocol level:

| Action | Meaning |
|---|---|
| **Retry** | Redeliver to same or different consumer |
| **Park** | Move to parked messages (dead letter) |
| **Skip** | Discard and move on |
| **Stop** | Halt the subscription |

### 4. Idempotent Non-Projections

For projections, make operations idempotent so re-delivery is harmless:

> The `insert` operation in the projection is not idempotent, so if the event is processed twice, the projector will throw. Make the operation idempotent by using "insert or update".

## Decision Matrix: Which Strategy When?

| Scenario | ThrowOnError | Retry | Dead Letter | Why |
|---|---|---|---|---|
| **Projections** (read models) | `false` | optional | nice to have | One bad event shouldn't block all reads; can rebuild |
| **Saga / Process Manager** | `true` | yes (with limit) | yes | Can't skip — business process would be incomplete |
| **Notifications** (email, webhook) | `false` | yes (limited) | yes | Best effort; review dead letters later |
| **Integration** (cross-service) | depends | yes | yes | Varies by business criticality |

## The Full Failure Handling Flow

```
Event arrives at subscription
        |
        v
   Handler processes
        |
   +----+----+
   v         v
SUCCESS    FAILURE
   |         |
   |    Retry policy (1..N attempts)
   |         |
   |    +----+----+
   |    v         v
   |  RECOVERED  EXHAUSTED
   |    |         |
   |    |    +----+-------------+
   |    |    v                  v
   |    |  ThrowOnError=true  ThrowOnError=false
   |    |    |                  |
   |    |    v                  v
   |    |  STOP subscription  Log + skip (or dead letter)
   |    |  (retry on restart) Continue processing
   |    |
   v    v
  ACK -> checkpoint advances
```

## The Poison Message Problem

A single permanently-failing event can block an entire subscription (when `ThrowOnError = true`). Solutions:

1. **Retry with limit** — After N retries, move to dead letter
2. **Dead letter queue** — Park the event, continue with the rest
3. **Manual intervention** — Alerts, monitoring, dashboards for dead-lettered events
4. **Fix and replay** — Fix the handler bug, then replay from dead letter queue

## Sources

- [Eventuous — Subscription Base docs](https://github.com/eventuous/eventuous)
- [Eventuous — Polly integration](https://github.com/eventuous/eventuous)
- [EventSourcing.NetCore — EventStoreDBSubscriptionToAll.cs](https://github.com/oskardudycz/EventSourcing.NetCore)
- [Axon — DeadLetteredEventProcessingTask.java](https://github.com/AxonFramework/AxonFramework)
- [Marten — Subscription infrastructure](https://github.com/JasperFx/marten)
