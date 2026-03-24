# Introduction to Event Sourcing | Kurrent

Source: https://www.eventstore.com/event-sourcing

# Introduction to Event Sourcing

The Architectural Pattern for Highly Adaptive, Auditable, and AI-Ready Business Applications

[Play](https://youtube.com/watch?v=mZAWsvym43Q)

## Event Sourcing in 4 minutes

Learn the big picture and fundamentals of event sourcing in this short video

[Watch the Full Video here](https://www.youtube.com/watch?v=mZAWsvym43Q&list=PLWG5TK2D4U_N3hiOYPu40FiYF7-quXp9X&index=1)

[ð Get Started with Event Sourcing](https://docs.kurrent.io/getting-started/introduction.html)

[ð Explore Event Sourcing Resources](/resources/eventsourcing)

## Why Developers are Adopting Event Sourcing

Modernize monolithic and tightly coupled applications and databases

Fuel contextual AI and analytics with rich and auditable historical data

[Learn more in this 30-min "Why Event Sourcing" video](/blog/why-event-sourcing/)

## Challenges of Business Application Development

### Monolithic Application and Shared Data Models

* Monolithic applications often force business logic to use shared data models
* If any business logic or model changes, everything has to change
* This dependency makes it challenging to scale and decouple the monolith

### Context Loss in Operational Databases

* Operational databases often only keep the current version of each record to maximize performance and minimize storage costs
* This approach overwrites historical snapshots, erasing previous states with every update and delete
* As a result, valuable historical context is lost, making it difficult to support advanced AI and analytics

## Event Sourcing 101

1

### Append domain events to the event store

Every change in the application is captured as a domain event and appended to an event store.

2

### Replay events with a projection

Another application can replay these events from the event store using a projection.

3

### Build a custom data model

The projection builds a custom data model optimized for a specific use case, in any database or schema.

### Domain Event

A business event representing a change in the application, modeled in language familiar to business stakeholders rather than technical details.

[Learn more](https://docs.kurrent.io/getting-started/concepts.html#event)

### Event Store

An append-only database that records every event in sequence, preserving a complete and permanent log of changes. KurrentDB is an example of an event store.

[Learn more](https://docs.kurrent.io/getting-started/concepts.html#event-log)

### Projection

A function that constructs a data model by sequentially replaying events from the event store.

[Watch this Video for the Basics](https://www.youtube.com/watch?v=AEbBCjo-WGM&list=PLWG5TK2D4U_N3hiOYPu40FiYF7-quXp9X&index=2)

[Read this for an In-Depth Explanation](/resources/eventsourcing/what-is-event-sourcing/)

[Take this Course for the Essentials](https://academy.kurrent.io/essentials)

## Decouple Monolithic Applications with Event Sourcing

### Separate Data Model from your Business Logic

Domain events are not strongly tied to any specific data model, database, or schema, which helps separate the business logic from the data model.

### Modularize Monolithic Application to Services

Monolithic applications can be decoupled into independent vertical slices for microservices or modular monoliths that are easier to evolve, scale, and maintain.

[Click here to learn more](/cqrs-pattern)

## Build Rich, Auditable, and Contextual AI with Event Sourcing

### Time Travel and Analyze your Business with a Full Audit Log

Cart Events

Added

80" TV

$1200

Added

Pro. HDMI

$80

Removed

80" TV

$1200

Removed

Pro. HDMI

$80

Added

60" TV

$800

Timeline

Cart  
Total

$1200

$2060

$860

$780

$1580

[{"type":"add","item":{"name":"80\" TV","price":1200},"cartSummary":{"items":1,"total":1200}},{"type":"add","item":{"name":"Pro. HDMI","price":80},"cartSummary":{"items":4,"total":2060}},{"type":"remove","item":{"name":"80\" TV","price":1200},"cartSummary":{"items":3,"total":860}},{"type":"remove","item":{"name":"Pro. HDMI","price":80},"cartSummary":{"items":2,"total":780}},{"type":"add","item":{"name":"60\" TV","price":800},"cartSummary":{"items":3,"total":1580}}]

[Learn How to Build Applications to Time Travel](https://docs.kurrent.io/dev-center/use-cases/time-travel/tutorial/tutorial-intro.html)

### Prompt for Insightful Questions only Possible with Historical Events

Which products are most frequently removed from carts?

How often are items swapped for cheaper alternatives?

What accessories are removed when a primary product is removed?

At what cart value do users begin to remove items?

Which items are most commonly added to the cart first?

What sequence of actions leads to cart abandonment?

How does adding a high-value item influence subsequent additions?

Which items are most often added back after being removed?

Do users remove items after viewing shipping costs?

What product combinations are most frequently tried but not purchased?

Which products are most frequently removed from carts?

How often are items swapped for cheaper alternatives?

What accessories are removed when a primary product is removed?

At what cart value do users begin to remove items?

Which items are most commonly added to the cart first?

What sequence of actions leads to cart abandonment?

How does adding a high-value item influence subsequent additions?

Which items are most often added back after being removed?

Do users remove items after viewing shipping costs?

What product combinations are most frequently tried but not purchased?

## The world's leading event store for event-sourced applications

### Decade of Event Sourcing Expertise

Represents over a decade of refined event sourcing expertise and best practices from thousands of customers.

### Immutable Append-Only Log

Features a durable, sequential, and append-only log of immutable events.

[Learn more](https://docs.kurrent.io/getting-started/concepts.html#event-log)

### Event Indexing

Stores billions of events with indexes to retrieve specific events quickly.

[Learn more](https://docs.kurrent.io/getting-started/concepts.html#stream-indexing)

### Native Pub/sub

Supports Native pub/sub to synchronize other systems in real-time or on-demand.

### Programming Platforms

Supports clients for major programming platforms such as .NET, Java, Node.js, Python, Go, and Rust.

[Learn more](https://docs.kurrent.io/clients/)

### Kurrent Cloud

Offers diverse deployment options, including Kurrent Cloud as a fully managed solution.

[Learn more](/kurrent-cloud)

[ð Get Started with Event Sourcing](https://docs.kurrent.io/getting-started/introduction.html)

[ð Explore Event Sourcing Resources](/resources/eventsourcing)