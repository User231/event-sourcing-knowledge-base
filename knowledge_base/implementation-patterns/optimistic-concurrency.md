# Optimistic Concurrency Control

## The Mechanism: Expected Version

When you load an aggregate, you note its current stream version (the number of events already in the stream). When you append new events, you pass this version as the expected version.

The event store performs an atomic check:

```
IF current_stream_version != expected_version THEN
    REJECT (conflict!)
ELSE
    APPEND events, increment version
```

## How It Works at the Database Level

PostgreSQL function (from EventSourcing.NetCore workshop):

```sql
-- check optimistic concurrency
IF expected_stream_version IS NOT NULL
   AND stream_version != expected_stream_version THEN
    RETURN FALSE;   -- reject the append
END IF;
```

## How We Detect Conflicts in Code

Each framework throws a specific exception:

**Marten (.NET)**:
```csharp
throw new ConcurrencyException(
    $"Expected the existing version to be {expectedStartingVersion}, but was {version}",
    typeof(TDoc), id);
```

**Event-Nest (TypeScript)**:
```typescript
export class EventConcurrencyException extends Error {
    constructor(aggregateRootId: string, databaseVersion: number, version: number) {
        super(`Concurrency issue for aggregate ${aggregateRootId}. ` +
              `Expected ${version}. Stored ${databaseVersion}`);
    }
}
```

**Eventuous (.NET)** — catches and wraps:
```csharp
catch (Exception e) {
    throw e.InnerException?.Message.Contains("WrongExpectedVersion") == true
        ? new OptimisticConcurrencyException(streamName, e)
        : e;
}
```

## Concrete Scenario

```
Time 0:  User A loads ShoppingCart (version = 3)
Time 0:  User B loads ShoppingCart (version = 3)
Time 1:  User A adds item -> appends with expectedVersion=3 -> SUCCESS (version now 4)
Time 2:  User B adds item -> appends with expectedVersion=3 -> FAIL! (actual version is 4)
```

## HTTP Integration via ETags

The version is exposed to the client via standard HTTP conditional headers (RFC 7232).

### Server Returns Version as ETag

```http
HTTP/1.1 200 OK
ETag: W/"3"
Content-Type: application/json

{ "id": "cart-123", "items": [...] }
```

### Client Sends Version Back via If-Match

```http
POST /shopping-carts/cart-123/product-items HTTP/1.1
If-Match: W/"3"
Content-Type: application/json

{ "productId": "shoes-1", "quantity": 2 }
```

### Server Extracts and Uses as Expected Revision

```typescript
export const toWeakETag = (value: number | bigint | string): WeakETag => {
  return `W/"${value}"`;
};

export const getETagFromIfMatch = (request: Request): ETag => {
  const etag = request.headers['if-match'];
  if (etag === undefined) {
    throw new Error(ETagErrors.MISSING_IF_MATCH_HEADER);
  }
  return etag;
};

export const getWeakETagValue = (etag: ETag): string => {
  const result = WeakETagRegex.exec(etag);  // /W\/"(-?\d+.*)"/
  return result[1]!;
};
```

### Response Includes the New Version

```http
HTTP/1.1 200 OK
ETag: W/"4"
```

## Full Round-Trip Example

```
1. GET /carts/123           -> 200 OK, ETag: W/"3"
2. POST /carts/123/items    + If-Match: W/"3"  -> 200 OK, ETag: W/"4"
3. POST /carts/123/confirm  + If-Match: W/"4"  -> 200 OK, ETag: W/"5"
4. POST /carts/123/items    + If-Match: W/"3"  -> 412 Precondition Failed (stale!)
```

## HTTP Status Code Mapping

| Framework | Exception | HTTP Status |
|---|---|---|
| Eventuous | `OptimisticConcurrencyException` | `409 Conflict` |
| EventSourcing.NodeJS | `WrongExpectedRevision` | `412 Precondition Failed` |
| Marten | `ConcurrencyException` | Depends on mapping |

## Three Strategies for Handling Conflicts

### 1. Retry (most common for server-side / automated)

Reload the aggregate at the new version, re-execute the command, try appending again.

```
loop:
  1. Load aggregate (get latest version)
  2. Execute command
  3. Try append with expected version
  4. If conflict -> go to 1 (with retry limit)
  5. If success -> return
```

### 2. Return Conflict to Client (most common for UIs)

Return `409`/`412`. The client can refresh data, show the user what changed, let them decide.

### 3. Merge / Resolve (rare, domain-specific)

Load events between expected and current version, check if they conflict with intent, retry at new version if compatible.

## Why ETags?

- **No custom protocol** — any HTTP client understands ETags
- **Proxies and caches** understand them natively
- **Well-defined semantics** — `If-Match` means "only do this if the resource is still at this version"
- **The raw version number is hidden** — the client treats it as an opaque token

## Sources

- [EventSourcing.NodeJS — ETag tools](https://github.com/oskardudycz/EventSourcing.NodeJS)
- [EventSourcing.NetCore — EventStore (PostgreSQL)](https://github.com/oskardudycz/EventSourcing.NetCore)
- [Eventuous — WriterExtensions.cs](https://github.com/eventuous/eventuous)
- [Optimistic concurrency for pessimistic times](https://event-driven.io/en/optimistic_concurrency_for_pessimistic_times/)
