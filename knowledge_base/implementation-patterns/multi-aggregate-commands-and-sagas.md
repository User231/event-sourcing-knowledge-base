# Multi-Aggregate Commands, Sagas, and Process Managers

## The Rule: One Command = One Aggregate

Each aggregate has its own event stream with its own version. There's no way to atomically append to two streams with two separate optimistic concurrency checks in one transaction (in most event stores). So you fundamentally can't do a transactional update of two aggregates.

From Eventuous docs:

> When handling a command, you need to ensure it only changes the state of a single aggregate. An aggregate boundary is a transaction boundary, so the state transition needs to happen entirely or not at all.

## Why Direct Multi-Aggregate Updates Fail

```
1. Load AggregateA (version 5), Load AggregateB (version 3)
2. Execute logic -> events for both
3. Append to StreamA (expected=5) -> SUCCESS
4. Append to StreamB (expected=3) -> CONFLICT!
   Now what? StreamA already has the events. You can't roll back.
```

## The Solution: Saga / Process Manager

Instead of one command updating multiple aggregates, decompose it into a chain of events and commands — a sequence of microtransactions, each touching a single aggregate.

> Distributed processes embrace the impossibility of the two-phase commit. Instead of trying to make a big transaction across modules, it does a sequence of microtransactions. Each operation is handled by the module that's the source of truth. A lasagne of event/command/event/command until the process finishes.

## Concrete Example: Hotel Group Checkout

A group checkout needs to check out multiple guests:

```
                          +--------------+
InitiateGroupCheckout --->| GroupCheckout |---> GroupCheckoutInitiated
                          |  Aggregate   |
                          +--------------+
                                |
                    Saga handles event, sends
                    commands for each guest:
                                |
                    +-----------+-----------+
                    v           v           v
             CheckOutGuest CheckOutGuest CheckOutGuest
                    |           |           |
                    v           v           v
              GuestCheckedOut  GuestCheckedOut  GuestCheckOutFailed
                    |           |           |
                    +-----------+-----------+
                                |
                    Saga collects results:
                                v
                    RecordGuestCheckoutCompletion (x2)
                    RecordGuestCheckoutFailure   (x1)
                                |
                                v
                      GroupCheckoutCompleted (with failures noted)
```

### The Saga (stateless event-to-command mapping)

```csharp
public static class GroupCheckoutSaga
{
    public static Command<CheckOutGuest>[] Handle(GroupCheckoutInitiated @event) =>
        @event.GuestStayIds.Select(guestAccountId =>
            Send(new CheckOutGuest(guestAccountId, @event.InitiatedAt, @event.GroupCheckoutId))
        ).ToArray();

    public static SagaResult Handle(GuestCheckedOut @event)
    {
        if (!@event.GroupCheckOutId.HasValue)
            return Ignore;
        return Send(new RecordGuestCheckoutCompletion(
            @event.GroupCheckOutId.Value, @event.GuestStayId, @event.CheckedOutAt));
    }

    public static SagaResult Handle(GuestCheckOutFailed @event)
    {
        if (!@event.GroupCheckOutId.HasValue)
            return Ignore;
        return Send(new RecordGuestCheckoutFailure(
            @event.GroupCheckOutId.Value, @event.GuestStayId, @event.FailedAt));
    }
}
```

### The Saga Wiring (event subscriptions)

```csharp
eventBus
    .Subscribe<GroupCheckoutInitiated>((@event, ct) =>
        commandBus.Send(GroupCheckoutSaga.Handle(@event).Select(c => c.Message).ToArray(), ct)
    )
    .Subscribe<GuestCheckedOut>((@event, ct) =>
        GroupCheckoutSaga.Handle(@event) is Command<RecordGuestCheckoutCompletion>(var command)
            ? commandBus.Send([command], ct)
            : ValueTask.CompletedTask
    )
    .Subscribe<GuestCheckOutFailed>((@event, ct) =>
        GroupCheckoutSaga.Handle(@event) is Command<RecordGuestCheckoutFailure>(var command)
            ? commandBus.Send([command], ct)
            : ValueTask.CompletedTask
    );
```

### Each Command Handler Touches Exactly One Aggregate

```csharp
public async ValueTask RecordGuestCheckoutCompletion(RecordGuestCheckoutCompletion command, ...) {
    var groupCheckout = await GetGroupCheckOut(command.GroupCheckoutId, ct);
    groupCheckout.RecordGuestCheckoutCompletion(command.GuestStayId, command.CompletedAt);
    await eventStore.AppendToStream(id, groupCheckout.DequeueUncommittedEvents(), ct);
}
```

## Failure Handling: Compensation

Since there's no distributed transaction, handle failures via compensating actions:

```
OrderPlaced       -> ReserveInventory command
InventoryReserved -> ChargePayment command
PaymentCharged    -> ShipOrder command
PaymentFailed     -> ReleaseInventory command  <-- compensation!
```

If step 3 fails, you don't "roll back" — you issue a new command that undoes the effect of the previous step.

## Choreography vs Orchestration

| Style | How It Works | When to Use |
|---|---|---|
| **Choreography** | Each service reacts to events independently. No central coordinator. | Simple flows, few steps |
| **Orchestration** (Saga/Process Manager) | A central coordinator listens to events and issues commands. Tracks state. | Complex flows, many steps, compensation needed |

## Saga State Storage

There are three main approaches:

### 1. Stateless Saga + Tracking Aggregate (most common)

The saga itself is a pure function (event in -> commands out). Process tracking state lives in a dedicated aggregate:

```csharp
public class GroupCheckOut : Aggregate<GroupCheckoutEvent, Guid>
{
    private Dictionary<Guid, CheckoutStatus> guestStayCheckouts = new();

    public void RecordGuestCheckoutCompletion(Guid guestStayId, DateTimeOffset now)
    {
        if (guestStayCheckouts[guestStayId] != CheckoutStatus.Initiated)
            return;  // idempotency
        Enqueue(new GuestCheckOutCompleted(Id, guestStayId, now));
        guestStayCheckouts[guestStayId] = CheckoutStatus.Completed;
        if (!AreAnyOngoingCheckouts())
            Enqueue(Finalize(now));
    }
}
```

### 2. Event-Sourced Process Manager

The process manager has its own event stream (Commanded/Elixir, some Axon setups).

```elixir
defmodule ExampleProcessManager do
  use Commanded.ProcessManagers.ProcessManager,
    application: ExampleApp, name: "ExampleProcessManager"

  defstruct []

  def interested?(%AnEvent{uuid: uuid}), do: {:start, uuid}
  def handle(%ExampleProcessManager{}, %ExampleEvent{}), do: [%ExampleCommand{}]
  def apply(%ExampleProcessManager{} = pm, %SomeEvent{}), do: %{pm | status: :completed}
end
```

### 3. Serialized State in DB

Saga state serialized to a table (JDBC/Mongo), updated after each handled event (Axon's default `SagaStore`).

```java
void insertSaga(Class<? extends T> sagaType, String sagaIdentifier,
                T saga, Set<AssociationValue> associationValues);
void updateSaga(Class<? extends T> sagaType, String sagaIdentifier,
                T saga, AssociationValues associationValues);
```

### Comparison

| Pattern | State Storage | Pro | Con |
|---|---|---|---|
| Stateless Saga + tracking aggregate | Aggregate's event stream | Clean separation, testable | Extra aggregate to manage |
| Event-sourced Process Manager | Its own event stream | Full history, same rebuild pattern | More complex |
| Serialized state in DB | Database table | Simple | No history, different storage model |

## Key Takeaway

If you feel the need to update two aggregates atomically, reconsider your aggregate boundaries — maybe they should be one aggregate.

## Sources

- [EventSourcing.JVM — Distributed Processes](https://github.com/oskardudycz/EventSourcing.JVM/tree/main/samples/distributed-processes)
- [EventSourcing.NetCore — Hotel Management Sagas](https://github.com/oskardudycz/EventSourcing.NetCore)
- [Eventuous — Aggregate docs](https://github.com/eventuous/eventuous)
- [Commanded — Process Managers](https://github.com/commanded/commanded)
- [Saga and Process Manager - distributed processes in practice](https://event-driven.io/en/saga_process_manager_distributed_transactions)
