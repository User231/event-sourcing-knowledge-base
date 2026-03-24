# AxonFramework/AxonFramework

- **URL**: https://github.com/AxonFramework/AxonFramework
- **Description**: Axon Framework — CQRS and Event Sourcing for Java/Spring
- **Stars**: 3569
- **Primary Language**: Java

---



## File: README.md

<p align="center">
  <a href="https://www.axoniq.io/products/axon-framework">
    <img src="https://raw.githubusercontent.com/AxonFramework/.github/main/images/AxonFrameworkLogo-2025.png" alt="Axon Framework logo" width="500"/>
  </a>
</p>

<p align="center">
  Build modern event-driven systems with AxonIQ technology.
  <br>
  <a href="https://www.axoniq.io/products/axon-framework"><strong>Product Description »</strong></a>
  <br>
  <br>
  <a href="https://github.com/AxonIQ/code-samples">Code Samples Repo</a>
  ·
  <a href="https://developer.axoniq.io/axon-framework/overview">Technical Overview</a>
  ·
  <a href="https://github.com/AxonFramework/AxonFramework/issues">Feature / Bug Request</a>


</p>

# Axon Framework

[![Maven Central](https://img.shields.io/maven-central/v/org.axonframework/axon-framework-bom)](https://central.sonatype.com/artifact/org.axonframework/axon-framework-bom)
[![Build Status](https://github.com/AxonFramework/AxonFramework/actions/workflows/main.yml/badge.svg)](https://github.com/AxonFramework/AxonFramework/actions/workflows/main.yml)
[![SonarCloud Status](https://sonarcloud.io/api/project_badges/measure?project=AxonFramework_AxonFramework&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=AxonFramework_AxonFramework)

Axon Framework is a framework for building evolutionary, event-driven microservice systems based on the principles of Domain-Driven Design (DDD), Command-Query Responsibility Separation (CQRS), and Event Sourcing.

<img src="https://library.axoniq.io/axoniq-console-getting-started/main/ac-monitor-axon-framework-applications/_images/ac-message-dependency-diagram.png" alt="Bootstrap logo">

Axon Framework provides you with the necessary building blocks to follow these principles.
Examples of building blocks are aggregate design handles, aggregate repositories, command buses, saga design handles, event stores, query buses, and more.
The framework provides sensible defaults for all of these components out of the box.

The messaging support for commands, events, and queries is at the core of these building blocks. 
It is the messaging basics that enable an evolutionary approach towards microservices through the [location transparency](https://en.wikipedia.org/wiki/Location_transparency) they provide.

Axon will also assist in distributing applications to support scalability or fault tolerance, for example.
The most accessible and quick road forward would be to use [Axon Server](https://developer.axoniq.io/axon-server/overview) to seamlessly adjust message buses to distributed implementations.
Axon Server provides a distributed command bus, event bus, query bus, and an efficient event store implementation for scalable event sourcing.
Additionally, the [Axon Framework organization](https://github.com/AxonFramework) has several extensions that can help in this space.

All this helps to create a well-structured application without worrying about the infrastructure.
Hence, your focus can shift from non-functional requirements to your business functionality.

For more information on anything Axon, please visit our website, [http://axoniq.io](http://axoniq.io).

## Getting started

Numerous resources can help you on your journey in using Axon Framework.
A good starting point is [AxonIQ Developer Portal](https://developer.axoniq.io/), which provides links to resources like blogs, videos, and descriptions.

Furthermore, below are several other helpful resources:
* The [quickstart page](https://docs.axoniq.io/reference-guide/getting-started/quick-start) of the documentation provides a simplified entry point into the framework with the [quickstart project](https://download.axoniq.io/quickstart/AxonQuickStart.zip).
* We have our very own [academy](https://academy.axoniq.io/)! 
  The introductory courses are free, followed by more in-depth (paid) courses.
* The [reference guide](https://docs.axoniq.io) explains all of the components maintained within Axon Framework's products.
* If the guide doesn't help, our [forum](https://discuss.axoniq.io/) provides a place to ask questions you have during development.
* The [hotel demo](https://github.com/AxonIQ/hotel-demo) shows a fleshed-out example of using Axon Framework.
* The [code samples repository](https://github.com/AxonIQ/code-samples) contains more in-depth samples you can benefit from.
* You can [Ask Axon Guru](https://gurubase.io/g/axon-framework), it is an Axon-focused AI to answer your questions.

## Receiving help

Are you having trouble using any of our libraries or products?
Know that we want to help you out the best we can!
There are a couple of things to consider when you're traversing anything Axon:

* Checking the [reference guide](https://docs.axoniq.io) should be your first stop.
* When the reference guide does not cover your predicament, we would greatly appreciate it if you could file an [issue](https://github.com/AxonIQ/reference-guide/issues) for it.
* Our [forum](https://discuss.axoniq.io/) provides a space to communicate with the Axon community to help you out. 
  AxonIQ developers will help you out on a best-effort basis. 
  And if you know how to help someone else, we greatly appreciate your contributions!
* We also monitor Stack Overflow for any question tagged with [**axon**](https://stackoverflow.com/questions/tagged/axon). 
  Similarly to the forum, AxonIQ developers help out on a best-effort basis.

## Feature requests and issue reporting

We use GitHub's [issue tracking system](https://github.com/AxonFramework/AxonFramework/issues)) for new feature requests, framework enhancements, and bugs.
Before filing an issue, please verify that it's not already reported by someone else. 
Furthermore, make sure you are adding the issue to the correct repository!

When filing bugs:
* A description of your setup and what's happening helps us figure out what the issue might be.
* Do not forget to provide the versions of the Axon products you're using, as well as the language and version.
* If possible, share a stack trace. 
  Please use Markdown semantics by starting and ending the trace with three backticks (```).

When filing a feature or enhancement:
* Please provide a description of the feature or enhancement at hand. 
  Adding why you think this would be beneficial is also a great help to us.
* (Pseudo-)Code snippets showing what it might look like will help us understand your suggestion better.
  Similarly as with bugs, please use Markdown semantics for code snippets, starting and ending with three backticks (```).
* If you have any thoughts on where to plug this into the framework, that would be very helpful too.
* Lastly, we value contributions to the framework highly. 
  So please provide a Pull Request as well!

## Update Checker and Anonymous Usage Data Collection

The update checker is a new feature included in the upcoming Axon Framework 5, which ensures the security of the Axon
Framework application and its modules and provides useful information to its maintainers.

It does so by retrieving available updates and known vulnerabilities for the Axon modules in use. Furthermore, to
detect updates and vulnerabilities, the checker collects anonymous data about your Axon Framework installation. This
data is sent to AxonIQ and includes technical information about your environment.

Please read [this page](https://docs.axoniq.io/axon-framework-update-checker/) of our documentation for more details on
why we collect this information, what you get in return, how to opt out, and why this matters. Please check out
our [Privacy Policy](https://www.axoniq.io/privacy-policy) for any privacy concerns.

<img referrerpolicy="no-referrer-when-downgrade" src="https://static.scarf.sh/a.png?x-pxid=31ffe27e-667c-48ff-8a14-8029d44dfb66" />



## File: docs/README.md

# Documentation For Axon Framework.

This folder contains the docs related to the Axon Framework project. The docs in this folder are written as part of the [AxonIQ Documentation](https://docs.axoniq.io), and are [written in AsciiDoc and built with Antora.](https://docs.axoniq.io/contribution_guide/overview/platform.html)

The following are the current documentation sources (folders):

- `af-fundamentals-tutorial`: [A tutorial covering Axon Framework's fundamental components and features.](https://docs.axoniq.io/axon_framework_fundamentals/index.html)
- `identifier-generation-guide` : [Guide that covers several considerations in regards to identifier generation in Axon Framework-based applications.](https://docs.axoniq.io/identifier-generation-guide/index.html)
- `message-handler-tunning-guide` : [Guide that covers the message handler tuning in your Axon Framework applications.](https://docs.axoniq.io/message-handler-tuning-guide/index.html)
- `meta-annotations-guide` : [Guide that covers several considerations in regards to creating Meta Annotations for Axon Framework-based applications.](https://docs.axoniq.io/meta-annotations-guide/index.html)
- `old-reference-guide` : [The Axon Framework former reference guide migrated from former docs.axoniq.io](https://docs.axoniq.io/axon-framework-reference/introduction.html)
- `rdbms-tunning-guide` : [Guide that covers several considerations in regards to tuning the database for events.](https://docs.axoniq.io/rdbms-tuning-guide/index.html)


## Contributing to the docs.

You are welcome to contribute to these docs. Whether you want to fix a typo, or you find something missing, something that it's not clear or can be improved, or even if you want to write an entire piece of docs to illustrate something that could help others to understand the use of the Bike Rental App, you are more than welcome to send a Pull Request to this github repository. Just make sure you follow the guidelines explained in [AxonIQ Library Contribution Guide](https://docs.axoniq.io/contribution_guide/index.html)

## Building and testing this docs locally.

If you want to build and explore the docs locally (because you have made changes or before contributing), you can use the Antora's build file in `docs/_playbook` folder.

You can check the [detailed information on how the process to build the docs works](https://docs.axoniq.io/contribution_guide/overview/build.html), but in short, all you have to do is: 

1. Make sure you have Node (a LTS version is preferred), Antora and Vale installed in your system.
2. CD to the `docs/_playbook` folder.
3. Run `npm install.`
4. Run `npx antora playbook.yaml`. Antora will generate the set of static html files under `docs/_playbook/build/site`
5. Move to `docs/_playbook/build/site` and execute some local http server to serve files in that directory. For example by executing `python3 -m http.server 8070`
6. Open your browser and go to `http://localhost:8070`. You should be able to navigate the local version of the docs.



## File: CONTRIBUTING.md

# Contribution Guidelines

Thank you for your interest in contributing to the Axon Framework. To make sure using Axon is a smooth experience for
everybody, we've set up a number of guidelines to follow.

There are different ways in which you can contribute to the framework:

1. You can report any bugs, feature requests or ideas about improvements on
   our [issue page](https://github.com/AxonFramework/AxonFramework/issues/new/choose). All ideas are welcome. Please be
   as exact as possible when reporting bugs. This will help us reproduce and thus solve the problem faster.
2. If you have created a component for your own application that you think might be useful to include in the framework,
   send us a pull request (or a patch / zip containing the source code). We will evaluate it and try to fit it in the
   framework. Please make sure code is properly documented using JavaDoc. This helps us to understand what is going on.
3. If you know of any other way you think you can help us, do not hesitate to send a message to
   the [AxonIQ's discussion platform](https://discuss.axoniq.io/).

## Code Contributions

If you're contributing code, please take care of the following:

### Contributor Licence Agreement

To keep everyone out of trouble (both you and us), we require that all contributors (digitally) sign a Contributor
License Agreement. Basically, the agreement says that we may freely use the code you contribute to the Axon Framework,
and that we won't hold you liable for any unfortunate side effects that the code may cause.

To sign the CLA, visit: https://cla-assistant.io/AxonFramework/AxonFramework

### Code Style

We're trying very hard to maintain a consistent style of coding throughout the code base. Think of things like indenting
using 4 spaces, putting opening brackets (the '{') on the same line and putting proper JavaDoc on all non-private
members.

If you're using IntelliJ IDEA, you can download the code style
definition [here](https://github.com/AxonFramework/AxonFramework/blob/master/axon_code_style.xml). Simply import the XML
file in under "Settings -> Code Style -> Scheme -> Import Scheme". Doing so should make the code style selectable
immediately.

