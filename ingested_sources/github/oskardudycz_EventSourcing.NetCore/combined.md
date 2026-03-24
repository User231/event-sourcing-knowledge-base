# oskardudycz/EventSourcing.NetCore

- **URL**: https://github.com/oskardudycz/EventSourcing.NetCore
- **Description**: Oskar Dudycz's .NET Event Sourcing examples & exercises
- **Stars**: 3668
- **Primary Language**: C#

---



## File: README.md

[<img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" height="20px" />](https://www.linkedin.com/in/oskardudycz/) ![Github Actions](https://github.com/oskardudycz/EventSourcing.NetCore/actions/workflows/build.dotnet.yml/badge.svg?branch=main) [![Github Sponsors](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&link=https://github.com/sponsors/oskardudycz/)](https://github.com/sponsors/oskardudycz/) [![blog](https://img.shields.io/badge/blog-event--driven.io-brightgreen)](https://event-driven.io/?utm_source=event_sourcing_net) [![blog](https://img.shields.io/badge/%F0%9F%9A%80-Architecture%20Weekly-important)](https://www.architecture-weekly.com/?utm_source=event_sourcing_net)

# EventSourcing .NET

Tutorial, practical samples and other resources about Event Sourcing in .NET. See also my similar repositories for [JVM](https://github.com/oskardudycz/EventSourcing.JVM) and [NodeJS](https://github.com/oskardudycz/EventSourcing.NodeJS).

- [EventSourcing .NET](#eventsourcing-net)
  - [1. Event Sourcing](#1-event-sourcing)
    - [1.1 What is Event Sourcing?](#11-what-is-event-sourcing)
    - [1.2 What is Event?](#12-what-is-event)
    - [1.3 What is Stream?](#13-what-is-stream)
    - [1.4 Event representation](#14-event-representation)
    - [1.5 Event Storage](#15-event-storage)
    - [1.6 Retrieving the current state from events](#16-retrieving-the-current-state-from-events)
    - [1.7 Strongly-Typed ids with Marten](#17-strongly-typed-ids-with-marten)
  - [2. Videos](#2-videos)
    - [2.1. Practical Event Sourcing with Marten](#21-practical-event-sourcing-with-marten)
    - [2.2. Keep your streams short! Or how to model event-sourced systems efficiently](#22-keep-your-streams-short-or-how-to-model-event-sourced-systems-efficiently)
    - [2.3. Let's build event store in one hour!](#23-lets-build-event-store-in-one-hour)
    - [2.4. CQRS is Simpler than you think with C#11 \& NET7](#24-cqrs-is-simpler-than-you-think-with-c11--net7)
    - [2.5. Practical Introduction to Event Sourcing with EventStoreDB](#25-practical-introduction-to-event-sourcing-with-eventstoredb)
    - [2.6. How to deal with privacy and GDPR in Event-Sourced systems](#26-how-to-deal-with-privacy-and-gdpr-in-event-sourced-systems)
    - [2.7 Let's build the worst Event Sourcing system!](#27-lets-build-the-worst-event-sourcing-system)
    - [2.8 The Light and The Dark Side of the Event-Driven Design](#28-the-light-and-the-dark-side-of-the-event-driven-design)
    - [2.9 Implementing Distributed Processes](#29-implementing-distributed-processes)
    - [2.10 Conversation with Yves Lorphelin about CQRS](#210-conversation-with-yves-lorphelin-about-cqrs)
    - [2.11. Never Lose Data Again - Event Sourcing to the Rescue!](#211-never-lose-data-again---event-sourcing-to-the-rescue)
  - [3. Support](#3-support)
  - [4. Prerequisites](#4-prerequisites)
  - [5. Tools used](#5-tools-used)
  - [6. Samples](#6-samples)
    - [6.1 Pragmatic Event Sourcing With Marten](#61-pragmatic-event-sourcing-with-marten)
    - [6.2 ECommerce with Marten](#62-ecommerce-with-marten)
    - [6.3 Simple EventSourcing with EventStoreDB](#63-simple-eventsourcing-with-eventstoredb)
    - [6.4 Implementing Distributed Processes](#64-implementing-distributed-processes)
    - [6.5 ECommerce with EventStoreDB](#65-ecommerce-with-eventstoredb)
    - [6.6 Warehouse](#66-warehouse)
    - [6.7 Warehouse Minimal API](#67-warehouse-minimal-api)
    - [6.8 Event Versioning](#68-event-versioning)
    - [6.9 Event Pipelines](#69-event-pipelines)
    - [6.10 Meetings Management with Marten](#610-meetings-management-with-marten)
    - [6.11 Cinema Tickets Reservations with Marten](#611-cinema-tickets-reservations-with-marten)
    - [6.12 SmartHome IoT with Marten](#612-smarthome-iot-with-marten)
  - [7. Self-paced training Kits](#7-self-paced-training-kits)
    - [7.1 Introduction to Event Sourcing](#71-introduction-to-event-sourcing)
    - [7.2 Build your own Event Store](#72-build-your-own-event-store)
  - [8. Articles](#8-articles)
  - [9. Event Store - Marten](#9-event-store---marten)
  - [10. CQRS (Command Query Responsibility Separation)](#10-cqrs-command-query-responsibility-separation)
  - [11. NuGet packages to help you get started.](#11-nuget-packages-to-help-you-get-started)
  - [12. Other resources](#12-other-resources)
    - [12.1 Introduction](#121-introduction)
    - [12.2 Event Sourcing on production](#122-event-sourcing-on-production)
    - [12.3 Projections](#123-projections)
    - [12.4 Snapshots](#124-snapshots)
    - [12.5 Versioning](#125-versioning)
    - [12.6 Storage](#126-storage)
    - [12.7 Design \& Modeling](#127-design--modeling)
    - [12.8 GDPR](#128-gdpr)
    - [12.9 Conflict Detection](#129-conflict-detection)
    - [12.10 Functional programming](#1210-functional-programming)
    - [12.12 Testing](#1212-testing)
    - [12.13 CQRS](#1213-cqrs)
    - [12.14 Tools](#1214-tools)
    - [12.15 Event processing](#1215-event-processing)
    - [12.16 Distributed processes](#1216-distributed-processes)
    - [12.17 Domain Driven Design](#1217-domain-driven-design)
    - [12.18 Whitepapers](#1218-whitepapers)
    - [12.19 Event Sourcing Concerns](#1219-event-sourcing-concerns)
    - [12.20 This is NOT Event Sourcing (but Event Streaming)](#1220-this-is-not-event-sourcing-but-event-streaming)
    - [12.21 Architecture Weekly](#1221-architecture-weekly)
  - [License](#license)

## 1. Event Sourcing

### 1.1 What is Event Sourcing?

Event Sourcing is a design pattern in which results of business operations are stored as a series of events.

It is an alternative way to persist data. In contrast with state-oriented persistence that only keeps the latest version of the entity state, Event Sourcing stores each state change as a separate event.

Thanks to that, no business data is lost. Each operation results in the event stored in the database. That enables extended auditing and diagnostics capabilities (both technically and business-wise). What's more, as events contains the business context, it allows wide business analysis and reporting.

In this repository I'm showing different aspects and patterns around Event Sourcing from the basic to advanced practices.

Read more in my articles:
-   📝 [How using events helps in a teams' autonomy](https://event-driven.io/en/how_using_events_help_in_teams_autonomy/?utm_source=event_sourcing_net)
-   📝 [When not to use Event Sourcing?](https://event-driven.io/en/when_not_to_use_event_sourcing/?utm_source=event_sourcing_net)

### 1.2 What is Event?

Events represent facts in the past. They carry information about something accomplished. It should be named in the past tense, e.g. _"user added"_, _"order confirmed"_. Events are not directed to a specific recipient - they're broadcasted information. It's like telling a story at a party. We hope that someone listens to us, but we may quickly realise that no one is paying attention.

Events:
- are immutable: _"What has been seen, cannot be unseen"_.
- can be ignored but cannot be retracted (as you cannot change the past).
- can be interpreted differently. The basketball match result is a fact. Winning team fans will interpret it positively. Losing team fans - not so much.

Read more in my articles:
-   📝 [What's the difference between a command and an event?](https://event-driven.io/en/whats_the_difference_between_event_and_command/?utm_source=event_sourcing_net)
-   📝 [Events should be as small as possible, right?](https://event-driven.io/en/events_should_be_as_small_as_possible/?utm_source=event_sourcing_net)
-   📝 [Anti-patterns in event modelling - Property Sourcing](https://event-driven.io/en/property-sourcing/?utm_source=event_sourcing_net)
-   📝 [Anti-patterns in event modelling - State Obsession](https://event-driven.io/en/state-obsession/?utm_source=event_sourcing_net)

### 1.3 What is Stream?

Events are logically grouped into streams. In Event Sourcing, streams are the representation of the entities. All the entity state mutations end up as the persisted events. Entity state is retrieved by reading all the stream events and applying them one by one in the order of appearance.

A stream should have a unique identifier representing the specific object. Each event has its own unique position within a stream. This position is usually represented by a numeric, incremental value. This number can be used to define the order of the events while retrieving the state. It can also be used to detect concurrency issues.

### 1.4 Event representation

Technically events are messages.

They may be represented, e.g. in JSON, Binary, XML format. Besides the data, they usually contain:
- **id**: unique event identifier.
- **type**: name of the event, e.g. _"invoice issued"_.
- **stream id**: object id for which event was registered (e.g. invoice id).
- **stream position** (also named _version_, _order of occurrence_, etc.): the number used to decide the order of the event's occurrence for the specific object (stream).
- **timestamp**: representing a time at which the event happened.
- other metadata like `correlation id`, `causation id`, etc.

Sample event JSON can look like:

```json
{
  "id": "e44f813c-1a2f-4747-aed5-086805c6450e",
  "type": "invoice-issued",
  "streamId": "INV/2021/11/01",
  "streamPosition": 1,
  "timestamp": "2021-11-01T00:05:32.000Z",

  "data":
  {
    "issuedTo": {
      "name": "Oscar the Grouch",
      "address": "123 Sesame Street"
    },
    "amount": 34.12,
    "number": "INV/2021/11/01",
    "issuedAt": "2021-11-01T00:05:32.000Z"
  },

  "metadata":
  {
    "correlationId": "1fecc92e-3197-4191-b929-bd306e1110a4",
    "causationId": "c3cf07e8-9f2f-4c2d-a8e9-f8a612b4a7f1"
  }
}
```

Read more in my articles:
-   📝 [Mapping event type by convention](https://event-driven.io/en/how_to_map_event_type_by_convention/?utm_source=event_sourcing_net)
-   📝 [Explicit events serialisation in Event Sourcing](https://event-driven.io/en/explicit_events_serialisation_in_event_sourcing/?utm_source=event_sourcing_net)


### 1.5 Event Storage

Event Sourcing is not related to any type of storage implementation. As long as it fulfills the assumptions, it can be implemented having any backing database (relational, document, etc.). The state has to be represented by the append-only log of events. The events are stored in chronological order, and new events are appended to the previous event. Event Stores are the databases' category explicitly designed for such purpose.

Read more in my articles:
-   📝 [Let's build event store in one hour!](https://event-driven.io/en/lets_build_event_store_in_one_hour/?utm_source=event_sourcing_net)
-   📝 [What if I told you that Relational Databases are in fact Event Stores?](https://event-driven.io/en/relational_databases_are_event_stores/?utm_source=event_sourcing_net)

### 1.6 Retrieving the current state from events

In Event Sourcing, the state is stored in events. Events are logically grouped into streams. Streams can be thought of as the entities' representation. Traditionally (e.g. in relational or document approach), each entity is stored as a separate record.

| Id       | IssuerName       | IssuerAddress     | Amount | Number         | IssuedAt   |
| -------- | ---------------- | ----------------- | ------ | -------------- | ---------- |
| e44f813c | Oscar the Grouch | 123 Sesame Street | 34.12  | INV/2021/11/01 | 2021-11-01 |

 In Event Sourcing, the entity is stored as the series of events that happened for this specific object, e.g. `InvoiceInitiated`, `InvoiceIssued`, `InvoiceSent`.

```json
[
    {
        "id": "e44f813c-1a2f-4747-aed5-086805c6450e",
        "type": "invoice-initiated",
        "streamId": "INV/2021/11/01",
        "streamPosition": 1,
        "timestamp": "2021-11-01T00:05:32.000Z",

        "data":
        {
            "issuer": {
                "name": "Oscar the Grouch",
                "address": "123 Sesame Street",
            },
            "amount": 34.12,
            "number": "INV/2021/11/01",
            "initiatedAt": "2021-11-01T00:05:32.000Z"
        }
    },
    {
        "id": "5421d67d-d0fe-4c4c-b232-ff284810fb59",
        "type": "invoice-issued",
        "streamId": "INV/2021/11/01",
        "streamPosition": 2,
        "timestamp": "2021-11-01T00:11:32.000Z",

        "data":
        {
            "issuedTo": "Cookie Monster",
            "issuedAt": "2021-11-01T00:11:32.000Z"
        }
    },
    {
        "id": "637cfe0f-ed38-4595-8b17-2534cc706abf",
        "type": "invoice-sent",
        "streamId": "INV/2021/11/01",
        "streamPosition": 3,
        "timestamp": "2021-11-01T00:12:01.000Z",

        "data":
        {
            "sentVia": "email",
            "sentAt": "2021-11-01T00:12:01.000Z"
        }
    }
]
```

All of those events share the stream id (`"streamId": "INV/2021/11/01"`), and have incremented stream positions.

In Event Sourcing each entity is represented by its stream: the sequence of events correlated by the stream id ordered by stream position.

To get the current state of an entity we need to perform the stream aggregation process. We're translating the set of events into a single entity. This can be done with the following steps:
1. Read all events for the specific stream.
2. Order them ascending in the order of appearance (by the event's stream position).
3. Construct the empty object of the entity type (e.g. with default constructor).
4. Apply each event on the entity.

This process is called also _stream aggregation_ or _state rehydration_.

We could implement that as:

```csharp
public record Person(
    string Name,
    string Address
);

public record InvoiceInitiated(
    double Amount,
    string Number,
    Person IssuedTo,
    DateTime InitiatedAt
);

public record InvoiceIssued(
    string IssuedBy,
    DateTime IssuedAt
);

public enum InvoiceSendMethod
{
    Email,
    Post
}

public record InvoiceSent(
    InvoiceSendMethod SentVia,
    DateTime SentAt
);

public enum InvoiceStatus
{
    Initiated = 1,
    Issued = 2,
    Sent = 3
}

public class Invoice
{
    public string Id { get;set; }
    public double Amount { get; private set; }
    public string Number { get; private set; }

    public InvoiceStatus Status { get; private set; }

    public Person IssuedTo { get; private set; }
    public DateTime InitiatedAt { get; private set; }

    public string IssuedBy { get; private set; }
    public DateTime IssuedAt { get; private set; }

    public InvoiceSendMethod SentVia { get; private set; }
    public DateTime SentAt { get; private set; }

    public void Evolve(object @event)
    {
        switch (@event)
        {
            case 

[... truncated for indexing ...]