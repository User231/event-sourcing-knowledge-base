# Event Sourcing — Libraries & Tools Comparison

## Event Stores (Databases)

### EventStoreDB
- **Language**: Runs as a standalone server (gRPC/HTTP API)
- **Clients**: .NET, Java, Node.js, Go, Rust, Python (community)
- **License**: Open source (server-side public license)
- **Best for**: Dedicated event sourcing deployments, teams wanting a purpose-built event store
- **Key features**: Built-in projections (JavaScript), persistent subscriptions, catch-up subscriptions, stream categories, global ordering, clustering
- **Storage**: Custom append-only storage engine
- **URL**: https://www.eventstore.com

### Marten
- **Language**: .NET (C#)
- **License**: MIT
- **Storage**: PostgreSQL (uses JSONB)
- **Best for**: .NET teams already using PostgreSQL, wanting document DB + event store in one
- **Key features**: Event store + document store, inline projections, async projections, multi-tenancy, flexible event metadata
- **URL**: https://martendb.io

### Axon Server
- **Language**: Java (companion to Axon Framework)
- **License**: Open source (Standard) / Commercial (Enterprise)
- **Best for**: Java/Spring teams using Axon Framework
- **Key features**: Event store + message router, tracking processors, distributed command handling
- **URL**: https://axoniq.io

## Frameworks & Libraries

### Java / Kotlin / JVM

**Axon Framework**
- Full CQRS + ES framework for Spring Boot
- Command handling, event handling, saga support, query handling
- Can use Axon Server or other backing stores (JPA, JDBC, MongoDB)
- Mature, well-documented, production-proven
- https://github.com/AxonFramework/AxonFramework

**ES4J (Eventsourcing for Java)**
- Lightweight event capture and querying
- Less opinionated than Axon
- https://github.com/eventsourcing/es4j

### C# / .NET

**Marten**
- PostgreSQL-backed document DB + event store
- Flexible projections (inline, async, live)
- Great integration with ASP.NET
- https://github.com/JasperFx/marten

**Eventuous**
- Lightweight, opinionated ES library for .NET
- Supports EventStoreDB, PostgreSQL, and others
- Focus on simplicity and developer experience
- https://github.com/eventuous/eventuous

**EventFlow**
- CQRS + ES framework for .NET
- Aggregates, sagas, read models, snapshots
- Multiple storage backends
- https://github.com/eventflow/EventFlow

### Python

**eventsourcing (Python)**
- Mature, well-maintained library
- Supports multiple backends: SQLAlchemy, Django, DynamoDB, Axon Server
- Aggregate base classes, snapshots, application infrastructure
- Good documentation with domain-driven design focus
- https://github.com/pyeventsourcing/eventsourcing

### Node.js / TypeScript

**Castore**
- TypeScript-first event sourcing library
- Type-safe event definitions and commands
- Pluggable storage adapters (DynamoDB, in-memory)
- https://github.com/castore-dev/castore

**Emmett** (by Oskar Dudycz)
- TypeScript library, inspired by Marten
- Focuses on developer ergonomics
- PostgreSQL-backed
- https://event-driven.io/en/emmett/

### Elixir

**Commanded**
- Full CQRS + ES framework for Elixir
- Aggregates, process managers, projections
- Uses PostgreSQL-based event store (EventStore library)
- Excellent fit for BEAM concurrency model
- https://github.com/commanded/commanded

### Rust

**Thalo**
- CQRS + Event Sourcing framework for Rust
- Type-safe command and event handling
- https://github.com/thalo-rs/thalo

### PHP

**Prooph Event Store**
- PHP event store implementation
- Supports PostgreSQL, MySQL, MariaDB, in-memory
- Part of the broader Prooph ecosystem (service bus, snapshots)
- https://github.com/prooph/event-store

### Go

**Event Horizon**
- CQRS + ES toolkit for Go
- Event store abstraction with multiple backends
- https://github.com/looplab/eventhorizon

## Choosing a Library — Decision Matrix

| Factor | Question |
|--------|----------|
| Language | What's your primary language? |
| Existing DB | Already running PostgreSQL? Consider Marten or Prooph |
| Opinionation | Want a full framework (Axon, Commanded) or a lighter library (Eventuous, Castore)? |
| Scale | Need clustering/distribution? EventStoreDB or Axon Server |
| Learning | New to ES? Start with Oskar Dudycz's example repos for your language |
| Production readiness | Axon, Marten, EventStoreDB, and Commanded all have strong production track records |
