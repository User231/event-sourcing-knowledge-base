# eventsourcing/es4j

- **URL**: https://github.com/eventsourcing/es4j
- **Description**: ES4J — Event capture and querying for Java
- **Stars**: 411
- **Primary Language**: Java

---



## File: README.md

[![Build Status](https://travis-ci.org/eventsourcing/es4j.svg?branch=master)](https://travis-ci.org/eventsourcing/es4j)
[![Maven Central](https://img.shields.io/maven-central/v/com.eventsourcing/eventsourcing-core.svg?maxAge=2592000)]()
[ ![Download](https://api.bintray.com/packages/eventsourcing/maven-snapshots/eventsourcing-core/images/download.svg) ](https://bintray.com/eventsourcing/maven-snapshots/eventsourcing-core/_latestVersion)
[![Join the chat at https://gitter.im/eventsourcing/eventsourcing](https://badges.gitter.im/eventsourcing/eventsourcing.svg)](https://gitter.im/eventsourcing/eventsourcing?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

# ![logo](https://eventsourcing.com/android-icon-48x48.png) Eventsourcing for Java

### *Enabling plurality and evolution of domain models*

Instead of mutating data in a database, Eventsourcing stores all changes (*events*) and what caused them (*commands*). To make this data useful,
Eventsourcing builds indices over it.

This helps developing applications faster because there is no need to worry
about designing the *right* domain models upfront (or as close to *right* as possible). By keeping all the commands and events, we can enrich or change
our domain models over time with very little friction. Furthermore, this approach removes a need to have a *one and only* domain model for every entity. We experience the world and reality in different ways, depending on circumstances and points of view, and our programs should be able to reflect that.

To learn more about what kind of problems ES4J addresses, please read [Why Use Eventsourcing Database](https://blog.eventsourcing.com/why-use-eventsourcing-database-6b5e2ac61848)

[![Lazy event sourcing: living in the now](https://www.dropbox.com/s/k2zdv7ez9wq4zog/lazy_eventsourcing_video.png?dl=1)](https://www.youtube.com/watch?v=aqv8d1pjmU8)


## Key benefits

* Domain model flexibility
* Late domain model binding
* Persistence of causal information
* Serializable conflict resolution
* Audit trail logging
* Mapping application functionality

## Key features

* Strongly typed schemas
* Event migrations
* Domain protocols
* Batteries included (shared event languages)
* Basic support for [Kotlin](http://kotlinlang.org)
* Causality-preserving [Hybrid Logical Clocks](http://www.cse.buffalo.edu/tech-reports/2014-04.pdf)
* In-memory and server (**PostgreSQL**) storage
* Locking synchronization primitive
* JMX-based introspection and management

# Presentation

You can find our current slide deck at https://eventsourcing.com/presentation

# Downloading and installing

To start using ES4J, please follow the [installation instructions](https://es4j.eventsourcing.com/docs/master/getting_started/install.html).

# Documentation

Documentation can be found at [es4j.eventsourcing.com](https://es4j.eventsourcing.com/docs/master)

We strive to specify the building blocks behind Eventsourcing and its ecosystem as succinct specifications, you can find the current list of them at [rfc.eventsourcing.com](http://rfc.eventsourcing.com)

# Roadmap

As this project is striving to be a decentralized, contributors-driven project governed by the [C4 process](http://rfc.unprotocols.org/spec:1/C4), there is no central roadmap per se. However, there's a [centralized list of reported issues](https://github.com/eventsourcing/es4j/issues). These do not imply an actual roadmap, just what has been reported, ranging from bugs to longer-term  design issues.

# Contributing

Contributions of all kinds (code, documentation, testing, artwork, etc.) are highly encouraged. Please open a GitHub issue if you want to suggest an idea or ask a question.

We use Unprotocols [C4 process](http://rfc.unprotocols.org/1/). In a nutshell, this means:

* We merge pull requests rapidly (try!)
* We are open to diverse ideas
* We prefer code now over consensus later

For more details, please refer to [CONTRIBUTING](CONTRIBUTING.md)

# Related projects

* [es4j-graphql](https://github.com/eventsourcing/es4j-graphql) A Relay.js/GraphQL adaptor for ES4J-based applications.



## File: docs/README.md

!INCLUDE "../README.md"



## File: CONTRIBUTING.md

Our goal is to encourage frictionless contributions to the project. In order to achieve that, we use Unprotocols [C4 process](https://rfc.unprotocols.org/spec:1/C4). Please read it, it will answer a lot of questions. Our goal is to merge pull requests as quickly as possible and make new stable releases regularly.

It is highly recommended to watch [Pieter Hintjens' talk on building open source communities](https://www.youtube.com/watch?v=uzxcILudFWM) as well as read his [book
on the same matter](https://www.gitbook.com/book/hintjens/social-architecture/details).

The code style is defined as per [IntelliJ IDEA 15 XML code style file](es4j-intellij-code-style.xml)

# Submitting an issue

According to [development process](https://rfc.unprotocols.org/spec:1/C4#24-development-process), the issue should describe a documented and provable. What this means is that an issue should trive to have a clear, understandable problem statement. Just like a patch, it SHOULD be titled "Problem: ..." and have a detailed description describing evidence behind it, be it a bug or a feature request, or a longer term "exploratory" issue.

# Preparing a patch

According to [patch requirements](https://rfc.unprotocols.org/spec:1/C4#23-patch-requirements), the patch should be a minimal and accurate answer to exactly one identified and agreed problem. A patch commit message must consist of a single short (less than 50 characters) line stating the problem ("Problem: ...") being solved, followed by a blank line and then the proposed solution ("Solution: ...").

```
Problem: short problem statement

Optional longer explanation of the problem that this patch
addresses, giving necessary details for the reader to be
able to understand it better.

Solution: explanation of the solution to the problem. Could
be longer than one line.
```

