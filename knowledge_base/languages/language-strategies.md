# Event Sourcing — Language & Framework Strategies

## Java / Spring Boot

### Recommended Stack
- **Framework**: Axon Framework (most mature ES framework in Java ecosystem)
- **Event Store**: Axon Server (free tier) or EventStoreDB
- **Projections DB**: PostgreSQL / MongoDB for read models
- **Serialization**: Jackson JSON or Avro for event schemas

### Key Patterns in Java
- Use Spring Boot auto-configuration with `axon-spring-boot-starter`
- Aggregates annotated with `@Aggregate`, commands with `@CommandHandler`, events with `@EventHandler`
- Sagas via `@Saga` annotation with association properties
- Tracking event processors for async projections
- JPA for persisting read models

### Example Structure
```
src/main/java/com/example/
├── command/          # Aggregates, command handlers
├── event/            # Event classes
├── query/            # Projections, query handlers
├── saga/             # Process managers
└── api/              # REST controllers
```

## C# / .NET

### Recommended Stacks

**Option A: Marten + PostgreSQL**
- Best if you're already on PostgreSQL
- Document store + event store combined
- Inline and async projections with Marten's projection system
- Works beautifully with ASP.NET minimal APIs

**Option B: Eventuous + EventStoreDB**
- Lightweight, less opinionated
- Great developer experience
- Strong EventStoreDB integration

### Key Patterns in .NET
- Aggregate base classes with `When(event)` pattern matching
- Decider pattern: `(state, command) → event[]` and `(state, event) → state`
- Projection subscriptions with checkpoint tracking
- Use records for events (immutability by default in C# 9+)

### Example Structure
```
src/
├── Domain/              # Aggregates, events, value objects
├── Application/         # Command handlers, services
├── Projections/         # Read model builders
├── Infrastructure/      # Event store config, serialization
└── Api/                 # Controllers / minimal API endpoints
```

## Python

### Recommended Stack
- **Library**: `eventsourcing` package
- **Backend**: SQLAlchemy (PostgreSQL) or DynamoDB
- **Read models**: SQLAlchemy ORM or any DB
- **API**: FastAPI or Django

### Key Patterns in Python
- Aggregate classes inheriting from `Aggregate`
- Domain events as `DomainEvent` dataclasses
- Application class wiring aggregates to infrastructure
- Runner/subscribers for projection processing

### Example Structure
```
app/
├── domain/
│   ├── model.py        # Aggregates and events
│   └── commands.py     # Command definitions
├── application/
│   ├── services.py     # Application services
│   └── projections.py  # Read model builders
├── infrastructure/
│   └── config.py       # Event store setup
└── api/
    └── routes.py       # REST endpoints
```

## Node.js / TypeScript

### Recommended Stack
- **Library**: Emmett (PostgreSQL) or Castore (DynamoDB/in-memory)
- **Event Store**: PostgreSQL or EventStoreDB (has official gRPC client)
- **Read models**: Any database via Prisma/Drizzle/TypeORM
- **API**: Express, Fastify, or NestJS

### Key Patterns in TypeScript
- Strong typing for events using discriminated unions
- Decider pattern works naturally with TypeScript type narrowing
- Event schemas with Zod or io-ts for runtime validation
- Functional approach: pure functions for decide/evolve, side effects at boundaries

### Example Structure
```
src/
├── domain/
│   ├── events.ts       # Event type definitions
│   ├── commands.ts      # Command types
│   └── aggregate.ts     # Decider logic
├── projections/
│   └── readModels.ts   # Projection handlers
├── infrastructure/
│   ├── eventStore.ts    # Store adapter
│   └── subscriptions.ts # Event subscriptions
└── api/
    └── routes.ts        # HTTP endpoints
```

## Elixir / BEAM

### Recommended Stack
- **Framework**: Commanded
- **Event Store**: commanded-ecto-projections + PostgreSQL
- **Read models**: Ecto
- **API**: Phoenix

### Why Elixir Excels at Event Sourcing
- BEAM's actor model maps naturally to aggregates (each aggregate = a process)
- Built-in supervision trees handle failure recovery
- GenServer for aggregate lifecycle management
- Pattern matching makes event handling elegant
- Immutability is the default

### Key Patterns
- Aggregates as modules with `execute/2` and `apply/2` functions
- Process managers via Commanded's `ProcessManager` behaviour
- Event handlers as GenServers
- Projections using Ecto for persistence

## Cross-Language Best Practices

### Serialization
- JSON is the most common format for events (human-readable, easy to debug)
- Consider Avro or Protobuf for high-throughput systems (schema registry recommended)
- Always include event type name and version in metadata
- Store both metadata (timestamp, correlation ID, causation ID, user ID) and data (the event payload)

### Event Design
- Events should be self-contained (don't reference external state)
- Use past tense: `OrderPlaced`, not `PlaceOrder`
- Include enough context to be useful without the full aggregate state
- Avoid large payloads — events should be lightweight

### Testing Across All Languages
- Given/When/Then pattern works in every language
- Unit test aggregates in isolation (no infrastructure)
- Integration test projections against a real event store
- Use test containers (Testcontainers) for database-dependent tests
