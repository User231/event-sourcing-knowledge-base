# Command Handling and API Response Flow

## The Standard Flow: Synchronous Write Side

The standard approach is synchronous on the write side: the HTTP response is only sent **after** the event store confirms the append. The client waits for event persistence.

```
Client -> API Endpoint -> Command Service -> Aggregate -> Event Store -> back up the chain -> Client
```

### Sequence Diagram (from Eventuous docs)

```
Client          API Endpoint      Command Service    Aggregate     Event Store
  |                 |                  |                 |              |
  |  HTTP Request   |                 |                 |              |
  |---------------->|  Command        |                 |              |
  |                 |---------------->|  Load stream    |              |
  |                 |                 |-------------------------------->|
  |                 |                 |  Events         |              |
  |                 |                 |<--------------------------------|
  |                 |                 |  Execute        |              |
  |                 |                 |---------------->|              |
  |                 |                 |  New events     |              |
  |                 |                 |<----------------|              |
  |                 |                 |  Append events  |              |
  |                 |                 |-------------------------------->|
  |                 |                 |  Return result  |              |
  |                 |                 |<--------------------------------|
  |                 |  Return result  |                 |              |
  |<----------------|                 |                 |              |
```

## Why Wait for Persistence?

The write side (command handling + event persistence) is the consistency boundary. If the append fails (e.g., optimistic concurrency conflict), the client needs to know. Without waiting, you can't tell the client whether the command actually succeeded.

## HTTP Status Code Mapping

Frameworks map event store outcomes to HTTP status codes:

| Outcome | HTTP Status |
|---|---|
| Success | `200 OK` or `201 Created` |
| Optimistic concurrency conflict | `409 Conflict` or `412 Precondition Failed` |
| Aggregate not found | `404 Not Found` |
| Domain validation failure | `400 Bad Request` |

### Example (Eventuous — C#)

```csharp
[Route("/booking")]
public class CommandApi : CommandHttpApiBase<Booking> {
    public CommandApi(ICommandService<Booking> service) : base(service) { }

    [HttpPost]
    [Route("book")]
    public Task<ActionResult<Result>> BookRoom(
        [FromBody] BookRoom cmd, CancellationToken ct
    ) => Handle(cmd, ct);  // awaits persistence, then maps result to HTTP status
}
```

## Write Side vs Read Side

There are two separate concerns:

```
Write side:  Client -> Command -> Append events -> Respond  (synchronous)
Read side:   Events -> Projections -> Read models           (asynchronous, eventual consistency)
```

- You **do wait** for the event to be **persisted** (write side) — this is the confirmation that the fact was recorded.
- You **don't wait** for **projections/read models** to be updated — those catch up asynchronously.

When the client gets a `200 OK`, it means: "your events are safely stored." But if they immediately query a read model, it might not yet reflect the change. This is **eventual consistency** on the read side.

## UI Strategies for Eventual Consistency

1. **Optimistic UI** — Update the UI immediately on the client side after getting `200` from the command, without re-fetching the read model.

2. **Return new state in the command response** — Some frameworks (like Eventuous) return `Result<TState>` which includes the updated aggregate state, so the client has it immediately without querying.

3. **Polling / subscriptions** — Client polls or subscribes (e.g., via WebSocket / SSE) until the read model catches up.

4. **ETag-based waiting** — The command returns the new stream version. The client sends this as a header to the query side, which can wait briefly for the projection to catch up to that version.

## Sources

- [Eventuous — Command API docs](https://github.com/eventuous/eventuous)
- [Eventuous — Functional Service docs](https://github.com/eventuous/eventuous)
- [EventSourcing.NodeJS — API tools](https://github.com/oskardudycz/EventSourcing.NodeJS)
