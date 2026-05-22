# oskardudycz/EventSourcing.JVM

- **URL**: https://github.com/oskardudycz/EventSourcing.JVM
- **Description**: Oskar Dudycz's JVM Event Sourcing examples
- **Stars**: 322
- **Primary Language**: Java

---



## File: README.md

[![Github Sponsors](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&link=https://github.com/sponsors/oskardudycz/)](https://github.com/sponsors/oskardudycz/) [![blog](https://img.shields.io/badge/blog-event--driven.io-brightgreen)](https://event-driven.io/?utm_source=event_sourcing_jvm) [![Architecture Weekly](https://img.shields.io/badge/%F0%9F%9A%80-Architecture%20Weekly-important)](https://www.architecture-weekly.com/?utm_source=event_sourcing_jvm) [![LinkedIn](https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/oskardudycz/) 

# EventSourcing.JVM

Tutorial, practical samples and other resources about Event Sourcing in JVM. See also my similar repositories for [.NET](https://github.com/oskardudycz/EventSourcing.NetCore) and [NodeJS](https://github.com/oskardudycz/EventSourcing.NodeJS).

- [EventSourcing.JVM](#eventsourcingjvm)
  - [Event Sourcing](#event-sourcing)
    - [What is Event Sourcing?](#what-is-event-sourcing)
    - [What is Event?](#what-is-event)
    - [What is Stream?](#what-is-stream)
    - [Event representation](#event-representation)
    - [Retrieving the current state from events](#retrieving-the-current-state-from-events)
    - [Event Store](#event-store)
  - [Videos](#videos)
    - [Practical introduction to Event Sourcing with Spring Boot and EventStoreDB](#practical-introduction-to-event-sourcing-with-spring-boot-and-eventstoredb)
    - [Facts and Myths about CQRS](#facts-and-myths-about-cqrs)
    - [Let's build the worst Event Sourcing system!](#lets-build-the-worst-event-sourcing-system)
    - [The Light and The Dark Side of the Event-Driven Design](#the-light-and-the-dark-side-of-the-event-driven-design)
    - [Conversation with Yves Lorphelin about CQRS](#conversation-with-yves-lorphelin-about-cqrs)
    - [How to deal with privacy and GDPR in Event-Sourced systems](#how-to-deal-with-privacy-and-gdpr-in-event-sourced-systems)
  - [Support](#support)
  - [Introduction to Event Sourcing self-paced kit](#introduction-to-event-sourcing-self-paced-kit)
    - [Exercises](#exercises)
  - [Samples](#samples)
    - [Event Sourcing with Spring Boot and EventStoreDB](#event-sourcing-with-spring-boot-and-eventstoredb)
      - [Overview](#overview)
      - [Main assumptions](#main-assumptions)
      - [Prerequisites](#prerequisites)
      - [Tools used](#tools-used)
    - [Event Versioning](#event-versioning)
    - [Uniqueness](#uniqueness)
    - [Distributed Processes](#distributed-processes)
  - [Articles](#articles)
  
## Event Sourcing

### What is Event Sourcing?

Event Sourcing is a design pattern in which results of business operations are stored as a series of events. 

It is an alternative way to persist data. In contrast with state-oriented persistence that only keeps the latest version of the entity state, Event Sourcing stores each state change as a separate event.

Thanks for that, no business data is lost. Each operation results in the event stored in the databse. That enables extended auditing and diagnostics capabilities (both technically and business-wise). What's more, as events contains the business context, it allows wide business analysis and reporting.

In this repository I'm showing different aspects, patterns around Event Sourcing. From the basic to advanced practices.

Read more in my article:
-   📝 [How using events helps in a teams' autonomy](https://event-driven.io/en/how_using_events_help_in_teams_autonomy/?utm_source=event_sourcing_jvm)
-   📝 [When not to use Event Sourcing?](https://event-driven.io/en/when_not_to_use_event_sourcing/?utm_source=event_sourcing_jvm)

### What is Event?

Events, represent facts in the past. They carry information about something accomplished. It should be named in the past tense, e.g. _"user added"_, _"order confirmed"_. Events are not directed to a specific recipient - they're broadcasted information. It's like telling a story at a party. We hope that someone listens to us, but we may quickly realise that no one is paying attention.

Events:
- are immutable: _"What has been seen, cannot be unseen"_.
- can be ignored but cannot be retracted (as you cannot change the past).
- can be interpreted differently. The basketball match result is a fact. Winning team fans will interpret it positively. Losing team fans - not so much.

Read more in my articles:
-   📝 [What's the difference between a command and an event?](https://event-driven.io/en/whats_the_difference_between_event_and_command/?utm_source=event_sourcing_jvm)
-   📝 [Events should be as small as possible, right?](https://event-driven.io/en/whats_the_difference_between_event_and_command/?utm_source=event_sourcing_jvm)

### What is Stream?

Events are logically grouped into streams. In Event Sourcing, streams are the representation of the entities. All the entity state mutations ends up as the persisted events. Entity state is retrieved by reading all the stream events and applying them one by one in the order of appearance.

A stream should have a unique identifier representing the specific object. Each event has its own unique position within a stream. This position is usually represented by a numeric, incremental value. This number can be used to define the order of the events while retrieving the state. It can be also used to detect concurrency issues. 

### Event representation

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
      "address": "123 Sesame Street",
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

### Retrieving the current state from events

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
            "issuedTo": {
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

All of those events shares the stream id (`"streamId": "INV/2021/11/01"`), and have incremented stream position.
We can get to conclusion that in Event Sourcing entity is represented by stream, so sequence of event correlated by the stream id ordered by stream position.

To get the current state of entity we need to perform the stream aggregation process. We're translating the set of events into a single entity. This can be done with the following the steps:
1. Read all events for the specific stream.
2. Order them ascending in the order of appearance (by the event's stream position).
3. Construct the empty object of the entity type (e.g. with default constructor).
4. Apply each event on the entity.

This process is called also _stream aggregation_ or _state rehydration_.

Read more in my article:
-   📝 [Why Partial<Type> is an extremely useful TypeScript feature?](https://event-driven.io/en/partial_typescript/?utm_source=event_sourcing_jvm)
-   📝 [How to get the current entity state from events?](https://event-driven.io/en/how_to_get_the_current_entity_state_in_event_sourcing/?utm_source=event_sourcing_jvm)

### Event Store

Event Sourcing is not related to any type of storage implementation. As long as it fulfils the assumptions, it can be implemented having any backing database (relational, document, etc.). The state has to be represented by the append-only log of events. The events are stored in chronological order, and new events are appended to the previous event. Event Stores are the databases' category explicitly designed for such purpose. 

In the further samples, I'll use [EventStoreDB](https://developers.eventstore.com/). It's the battle-tested OSS database created and maintained by the Event Sourcing authorities. It supports many dev environments via gRPC clients, including JVM.

Read more in my article:
-   📝 [What if I told you that Relational Databases are in fact Event Stores?](https://event-driven.io/en/relational_databases_are_event_stores/=event_sourcing_jvm)

## Videos

### Practical introduction to Event Sourcing with Spring Boot and EventStoreDB

<a href="https://www.youtube.com/watch?v=LaUSPtwFLSg" target="_blank"><img src="https://img.youtube.com/vi/LaUSPtwFLSg/0.jpg" alt="Practical introduction to Event Sourcing with Spring Boot and EventStoreDB" width="320" height="240" border="10" /></a>

### Facts and Myths about CQRS

<a href="https://www.youtube.com/watch?v=9COWKz1E32w" target="_blank"><img src="https://img.youtube.com/vi/9COWKz1E32w/0.jpg" alt="Facts and Myths about CQRS" width="320" height="240" border="10" /></a>

### Let's build the worst Event Sourcing system!

<a href="https://www.youtube.com/watch?v=Lu-skMQ-vAw" target="_blank"><img src="https://img.youtube.com/vi/Lu-skMQ-vAw/0.jpg" alt="Let's build the worst Event Sourcing system!" width="320" height="240" border="10" /></a>

### The Light and The Dark Side of the Event-Driven Design

<a href="https://www.youtube.com/watch?v=ZGugOiYcq8k" target="_blank"><img src="https://img.youtube.com/vi/ZGugOiYcq8k/0.jpg" alt="The Light and The Dark Side of the Event-Driven Design" width="320" height="240" border="10" /></a>

### Conversation with [Yves Lorphelin](https://github.com/ylorph/) about CQRS

<a href="https://www.youtube.com/watch?v=D-3N2vQ7ADE" target="_blank"><img src="https://img.youtube.com/vi/D-3N2vQ7ADE/0.jpg" alt="Event Store Conversations: Yves Lorphelin talks to Oskar Dudycz about CQRS (EN)" width="320" height="240" border="10" /></a>

### How to deal with privacy and GDPR in Event-Sourced systems

<a href="https://www.youtube.com/watch?v=7NGlYgobTyY" target="_blank"><img src="https://img.youtube.com/vi/7NGlYgobTyY/0.jpg" alt="How to deal with privacy and GDPR in Event-Sourced systems" width="320" height="240" border="10" /></a>

## Support

Feel free to [create an issue](https://github.com/oskardudycz/EventSourcing.JVM/issues/new) if you have any questions or request for more explanation or samples. I also take **Pull Requests**!

💖 If this repository helped you - I'd be more than happy if you **join** the group of **my official supporters** at:

👉 [Github Sponsors](https://github.com/sponsors/oskardudycz) 

⭐ Star on GitHub or sharing with your friends will also help!

## [Introduction to Event Sourcing self-paced kit](./workshops/introduction-to-event-sourcing/)

Event Sourcing is perceived as a complex pattern. Some believe that it's like Nessie, everyone's heard about it, but rarely seen it. In fact, Event Sourcing is a pretty practical and straightforward concept. It helps build predictable applications closer to business. Nowadays, storage is cheap, and information is priceless. In Event Sourcing, no data is lost. 

The workshop aims to build the knowledge of the general concept and its related patterns for the participants. The acquired knowledge will allow for the conscious design of architectural solutions and the analysis of associated risks. 

The emphasis will be on a pragmatic understanding of architectures and applying it in practice using Marten and EventStoreDB.

1. Introduction to Event-Driven Architectures. Differences from the classical approach are foundations and terminology (event, event streams, command, query).
2. What is Event Sourcing, and how is it different from Event Streaming. Advantages and disadvantages.
3. Write model, data consistency guarantees on examples from Marten and EventStoreDB.
4. Various ways of handling business logic: Aggregates, Command Handlers, functional approach.
5. Projections, best practices and concerns for building read models from events on the examples from Marten and EventStoreDB.
6. Challenges in Event Sourcing and EDA: deliverability guarantees, sequence of event handling, idempotency, etc.
8. Saga, Choreography, Process Manager,  distributed processes in practice.
7. Event Sourcing in the context of application architecture, integration with other approaches (CQRS, microservices, messaging, etc.).
8. Good and bad practices in event modelling.
9. Event Sourcing on production, evolution, events' schema versioning, etc.

You can do the workshop as a self-paced kit. That should give you a good foundation for starting your journey with Eve

[... truncated for indexing ...]