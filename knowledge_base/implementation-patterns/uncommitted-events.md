# Uncommitted Events Pattern

## What Are Uncommitted Events?

Uncommitted events are domain events that an aggregate has produced during command handling but that haven't been persisted to the event store yet. They live temporarily in a private in-memory collection inside the aggregate, waiting to be flushed to storage.

## Why This Pattern Exists

1. **Separation of concerns** — The aggregate focuses purely on business logic and invariant enforcement. It doesn't know about the event store. It just records "what happened" into an internal buffer. A separate infrastructure component (repository/store) reads that buffer and persists.

2. **Transactional boundary** — You can execute multiple business operations on the aggregate, accumulating several events, then persist them all atomically in a single append to the event store.

3. **State consistency during command handling** — When a command produces an event, the aggregate applies that event to its own state immediately (in memory), so subsequent logic within the same command sees the updated state. But the event hasn't been committed yet — it's queued.

4. **Testability** — You can invoke a command on an aggregate and assert which uncommitted events were produced, without needing a real event store.

## The Universal Structure

The core structure is always the same across all languages and frameworks:

```
Aggregate
  ├── private queue/list of uncommitted events
  ├── Enqueue(event)       — adds event + applies it to state
  └── DequeueUncommitted() — returns events + clears the buffer
```

## Code Examples

### C# (EventSourcing.NetCore — Oskar Dudycz)

```csharp
public abstract class Aggregate<TEvent> : IAggregate
{
    public Guid Id { get; protected set; }

    private readonly Queue<object> uncommittedEvents = new();

    public object[] DequeueUncommittedEvents()
    {
        var dequeuedEvents = uncommittedEvents.ToArray();
        uncommittedEvents.Clear();
        return dequeuedEvents;
    }

    protected void Enqueue(object @event) =>
        uncommittedEvents.Enqueue(@event);

    protected virtual void Apply(TEvent @event) { }
}
```

### Java (EventSourcing.JVM)

```java
public abstract class AbstractAggregate<Event, Id> implements Aggregate<Id> {
    protected int version = -1;
    private final Queue<Object> uncommittedEvents = new LinkedList<>();

    public Object[] dequeueUncommittedEvents() {
        var dequeuedEvents = uncommittedEvents.toArray();
        uncommittedEvents.clear();
        return dequeuedEvents;
    }

    protected void enqueue(Event event) {
        uncommittedEvents.add(event);
        when(event);     // apply to state immediately
        version++;
    }

    public abstract void when(Event event);
}
```

### TypeScript (EventSourcing.NodeJS)

```typescript
export abstract class Aggregate<E extends Event> {
  #uncommitedEvents: E[] = [];

  abstract evolve(event: E): void;

  protected enqueue = (event: E) => {
    this.#uncommitedEvents = [...this.#uncommitedEvents, event];
    this.evolve(event);
  };

  dequeueUncommitedEvents = (): E[] => {
    const events = this.#uncommitedEvents;
    this.#uncommitedEvents = [];
    return events;
  };
}
```

## How the Repository Uses It

The infrastructure/repository layer follows this pattern:

```java
// From AggregateStore.java (EventSourcing.JVM)
var events = entity.dequeueUncommittedEvents();  // grab pending events
var result = eventStore.appendToStream(           // persist atomically
    streamId, appendOptions, events.iterator()
);
```

## The Flow

```
1. Load aggregate (replay past events -> rebuild state)
2. Execute command -> aggregate validates, then calls Enqueue(new SomethingHappened(...))
   └── Enqueue: adds to buffer + applies to in-memory state + increments version
3. Repository calls DequeueUncommittedEvents() -> gets the new events
4. Repository appends events to event store (with optimistic concurrency check)
5. Buffer is now empty — aggregate is "clean"
```

## Key Design Decisions

| Aspect | Common Choice | Why |
|---|---|---|
| Data structure | `Queue` or `List` | Order matters — events must be appended in sequence |
| Enqueue visibility | `protected` | Only aggregate logic can produce events |
| Dequeue visibility | `public` | Infrastructure needs to read and flush |
| Dequeue clears buffer | Always | Prevents double-persist; makes the aggregate reusable |
| State applied immediately | Yes (`when`/`evolve`/`Apply`) | So the rest of the command sees updated state |
| Version incremented on enqueue | Usually | Tracks expected version for optimistic concurrency |

## Sources

- [EventSourcing.NetCore — Aggregate.cs](https://github.com/oskardudycz/EventSourcing.NetCore)
- [EventSourcing.JVM — AbstractAggregate.java](https://github.com/oskardudycz/EventSourcing.JVM)
- [EventSourcing.NodeJS — aggregate.ts](https://github.com/oskardudycz/EventSourcing.NodeJS)
- [Eventuous — Aggregate.cs](https://github.com/eventuous/eventuous)
