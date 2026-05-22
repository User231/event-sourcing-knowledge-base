# oskardudycz/EventSourcing.NodeJS

- **URL**: https://github.com/oskardudycz/EventSourcing.NodeJS
- **Description**: Oskar Dudycz's Node.js Event Sourcing examples
- **Stars**: 497
- **Primary Language**: TypeScript

---



## File: README.md

[<img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white" height="20px" />](https://www.linkedin.com/in/oskardudycz/) [![Subscribe](https://img.shields.io/badge/%F0%9F%9A%80-subscribe!-important)](https://www.architecture-weekly.com/?utm_source=github_architecture_weekly) [![Github Sponsors](https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&link=https://github.com/sponsors/oskardudycz/)](https://github.com/sponsors/oskardudycz/) [![blog](https://img.shields.io/badge/blog-event--driven.io-brightgreen)](https://event-driven.io/?utm_source=architecture_weekly) 

# EventSourcing.NodeJS

Tutorial, practical samples and other resources about Event Sourcing in NodeJS. See also my similar repositories for [.NET](https://github.com/oskardudycz/EventSourcing.NetCore) and [JVM](https://github.com/oskardudycz/EventSourcing.JVM).

- [EventSourcing.NodeJS](#eventsourcingnodejs)
  - [Event Sourcing](#event-sourcing)
    - [What is Event Sourcing?](#what-is-event-sourcing)
    - [What is Event?](#what-is-event)
    - [What is Stream?](#what-is-stream)
    - [Event representation](#event-representation)
    - [Retrieving the current state from events](#retrieving-the-current-state-from-events)
    - [Event Store](#event-store)
  - [Videos](#videos)
    - [Introduction to Event Sourcing in TypeScript and NodeJS with EventStoreDB](#introduction-to-event-sourcing-in-typescript-and-nodejs-with-eventstoredb)
    - [Event-Driven revolution, from CRUD to Event Sourcing](#event-driven-revolution-from-crud-to-event-sourcing)
    - [Let's build the worst Event Sourcing system!](#lets-build-the-worst-event-sourcing-system)
    - [The Light and The Dark Side of the Event-Driven Design](#the-light-and-the-dark-side-of-the-event-driven-design)
    - [Conversation with Yves Lorphelin about CQRS](#conversation-with-yves-lorphelin-about-cqrs)
  - [Articles](#articles)
  - [Samples](#samples)
  - [Self-paced training Kit Introduction to Event Sourcing](#self-paced-training-kit-introduction-to-event-sourcing)
  - [Exercises](#exercises)
  - [Node.js project configuration](#nodejs-project-configuration)
    - [General configuration](#general-configuration)
    - [VSCode debug configuration](#vscode-debug-configuration)
    - [Unit tests with Jest](#unit-tests-with-jest)
    - [API tests with SuperTest](#api-tests-with-supertest)
    - [Continuous Integration - Run tests with Github Actions](#continuous-integration---run-tests-with-github-actions)
    - [Continuous Delivery - Build Docker image and publish to Docker Hub and GitHub Container Registry](#continuous-delivery---build-docker-image-and-publish-to-docker-hub-and-github-container-registry)
      - [Docker](#docker)
      - [Image](#image)
      - [Useful commands](#useful-commands)
      - [Container registry](#container-registry)
      - [Docker Hub publishing setup](#docker-hub-publishing-setup)
      - [Github Container Registry publishing setup](#github-container-registry-publishing-setup)
      - [Publish through GitHub Actions](#publish-through-github-actions)
  - [Tasks List](#tasks-list)

## Event Sourcing

### What is Event Sourcing?

Event Sourcing is a design pattern in which results of business operations are stored as a series of events.

It is an alternative way to persist data. In contrast with state-oriented persistence that only keeps the latest version of the entity state, Event Sourcing stores each state change as a separate event.

Thanks for that, no business data is lost. Each operation results in the event stored in the database. That enables extended auditing and diagnostics capabilities (both technically and business-wise). What's more, as events contains the business context, it allows wide business analysis and reporting.

In this repository I'm showing different aspects, patterns around Event Sourcing. From the basic to advanced practices.

Read more in my article:

- 📝 [How using events helps in a teams' autonomy](https://event-driven.io/en/how_using_events_help_in_teams_autonomy/?utm_source=event_sourcing_nodejs)
- 📝 [When not to use Event Sourcing?](https://event-driven.io/en/when_not_to_use_event_sourcing/?utm_source=event_sourcing_nodejs)

### What is Event?

Events, represent facts in the past. They carry information about something accomplished. It should be named in the past tense, e.g. _"user added"_, _"order confirmed"_. Events are not directed to a specific recipient - they're broadcasted information. It's like telling a story at a party. We hope that someone listens to us, but we may quickly realise that no one is paying attention.

Events:

- are immutable: _"What has been seen, cannot be unseen"_.
- can be ignored but cannot be retracted (as you cannot change the past).
- can be interpreted differently. The basketball match result is a fact. Winning team fans will interpret it positively. Losing team fans - not so much.

Read more in my articles:

- 📝 [What's the difference between a command and an event?](https://event-driven.io/en/whats_the_difference_between_event_and_command/?utm_source=event_sourcing_nodejs)
- 📝 [Events should be as small as possible, right?](https://event-driven.io/en/events_should_be_as_small_as_possible/?utm_source=event_sourcing_nodejs)

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

  "data": {
    "issuedTo": {
      "name": "Oscar the Grouch",
      "address": "123 Sesame Street"
    },
    "amount": 34.12,
    "number": "INV/2021/11/01",
    "issuedAt": "2021-11-01T00:05:32.000Z"
  },

  "metadata": {
    "correlationId": "1fecc92e-3197-4191-b929-bd306e1110a4",
    "causationId": "c3cf07e8-9f2f-4c2d-a8e9-f8a612b4a7f1"
  }
}
```

This structure could be translated directly into the TypeScript class. However, to make the code less redundant and ensure that all events follow the same convention, it's worth adding the base type. It could look as follows:

```typescript
export type Event<
  EventType extends string = string,
  EventData extends Record<string, unknown> = Record<string, unknown>
> = Readonly<{
  type: Readonly<EventType>;
  data: Readonly<EventData>;
}>;
```

Several things are going on here:

1. Event type definition is not directly string, but it might be defined differently (`EventType extends string = string`). It's added to be able to define the alias for the event type. Thanks to that, we're getting compiler check and IntelliSense support,
2. Event data is defined as [Record](https://www.typescriptlang.org/docs/handbook/utility-types.html#recordkeystype) (`EventData extends Record<string, unknown> = Record<string, unknown>`). It is the way of telling the TypeScript compiler that it may expect any type but allows you to specify your own and get a proper type check.
3. We're using [Readonly<>](https://www.typescriptlang.org/docs/handbook/utility-types.html#readonlytype) wrapper around the Event type definition. We want to be sure that our event is immutable. Neither type nor data should change once it was initialised. `Readonly<>` constructs a type with all properties set as `readonly`. Syntax:

```typescript
Readonly<{
  type: EventType;
  data: EventData;
}>;
```

is equal to:

```typescript
{
  readonly type: EventType;
  readonly data: EventData;
};
```

I prefer the former, as, in my opinion, it's making the type definition less cluttered.

We're also wrapping the `EventType` and `EventData` with `Readonly<>`. This is needed as `Readonly<>` does only shallow type copy. It won't change the nested types definition. So:

```typescript
Readonly<{
  type: "invoice-issued";
  data: {
    number: string;
    issuedBy: string;
    issuedAt: Date;
  };
}>;
```

is the equivalent of:

```typescript
{
  readonly type: 'invoice-issued';
  readonly data: {
    number: string;
    issuedBy: string;
    issuedAt: Date;
  }
};
```

while we want to have:

```typescript
{
  readonly type: 'invoice-issued';
  readonly data: {
    readonly number: string;
    readonly issuedBy: string;
    readonly issuedAt: Date;
  }
};
```

Wrapping `EventType` and `EventType` and `EventData` with `Readonly<>` does that for us and enables immutability.

_**Note**: we still need to remember to wrap nested structures inside the event data into `Readonly<>` to have all properties set as `readonly`._

Having that, we can define the event as eg.:

```typescript
// alias for event type
type INVOICE_ISSUED = "invoice-issued";

// person DTO used in issued by event data
type Person = Readonly<{
  name: string;
  address: string;
}>;

// event type definition
type InvoiceIssued = Event<
  INVOICE_ISSUED,
  {
    issuedTo: Person;
    amount: number;
    number: string;
    issuedAt: Date;
  }
>;
```

then create it as:

```typescript
const invoiceIssued: InvoiceIssued = {
  type: "invoice-issued",
  data: {
    issuedTo: {
      name: "Oscar the Grouch",
      address: "123 Sesame Street",
    },
    amount: 34.12,
    number: "INV/2021/11/01",
    issuedAt: new Date(),
  },
};
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

    "data": {
      "issuedTo": {
        "name": "Oscar the Grouch",
        "address": "123 Sesame Street"
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

    "data": {
      "issuedBy": "Cookie Monster",
      "issuedAt": "2021-11-01T00:11:32.000Z"
    }
  },
  {
    "id": "637cfe0f-ed38-4595-8b17-2534cc706abf",
    "type": "invoice-sent",
    "streamId": "INV/2021/11/01",
    "streamPosition": 3,
    "timestamp": "2021-11-01T00:12:01.000Z",

    "data": {
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
3. Apply each event on the entity.

This process is called also _stream aggregation_ or _state rehydration_.

For this process we'll use the [reduce function](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Array/Reduce). It executes a reducer function (that you can provide) on each array element, resulting in a single output value. TypeScript extends it with the type guarantees:

1. reduce in TypeScript is a generic method. It allows to provide the result type as a parameter. It doesn’t have to be the same as type of the array elements.
2. You can also use optional param to provide the default value for accumulation.
3. Use [Partial<Type>](https://www.typescriptlang.org/docs/handbook/utility-types.html#partialtype) as the generic reduce param. It constructs a type with all properties of Type set to optional. This utility will return a type that represents all subsets of a given type. This is extremely important, as TypeScript forces you to define all required properties. We'll be merging different states of the aggregate state into the final one. Only the first event (`InvoiceInitiated`) will provide all required fields. The other events will just do a partial update (`InvoiceSent` only changes the status and sets the sending method and date).

Having event types defined as:

```typescript
type InvoiceInitiated = Event<
  "invoice-initiated",
  {
    number: string;
    amount: number;
    issuedTo: Person;
    initiatedAt: Date;
  }
>;

type InvoiceIssued = Event<
  "invoice-issued",
  {
    number: string;
    issuedBy: string;
    issuedAt: Date;
  }
>;

type InvoiceSent = Event<
  "invoice-sent",
  {
    number: string;
    sentVia: InvoiceSendMethod;
    sentAt: Date;
  }
>;
```

Entity as:

```typescript
type Invoice = Readonly<{
  number: string;
  amount: number;
  status: InvoiceStatus;

  issuedTo: Person;
  initiatedAt: Date;

  issued?: Readonly<{
    by?: string;
    at?: Date;
  }

[... truncated for indexing ...]