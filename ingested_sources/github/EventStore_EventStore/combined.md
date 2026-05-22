# EventStore/EventStore

- **URL**: https://github.com/EventStore/EventStore
- **Description**: EventStoreDB — purpose-built database for event sourcing
- **Stars**: 5798
- **Primary Language**: C#

---



## File: README.md

<a href="https://kurrent.io">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./KurrentLogo-White.png">
    <source media="(prefers-color-scheme: light)" srcset="./KurrentLogo-Black.png">
    <img alt="Kurrent" src="./KurrentLogo-Plum.png" height="50%" width="50%">
  </picture>
</a>

- [What is Kurrent](#what-is-kurrent)
- [What is KurrentDB](#what-is-kurrentdb)
- [What is Kurrent Cloud](#what-is-kurrent-cloud)
- [Licensing](#licensing)
- [Documentation](#docs)
- [Getting started with KurrentDB](#getting-started-with-kurrentdb)
- [Getting started with Kurrent Cloud](#getting-started-with-kurrent-cloud)
- [Client libraries](#client-libraries)
- [Deployment](#deployment)
- [Communities](#communities)
- [Contributing](#contributing)
- [Building KurrentDB](#building-kurrentdb)
- [More resources](#more-resources)

## What is Kurrent

Event Store – the company and the product – are rebranding as Kurrent.

- The flagship product will be referred to as “the Kurrent event-native data platform” or “the Kurrent platform” or simply “Kurrent"
- EventStoreDB will be referred to as KurrentDB
- Event Store Cloud will now be called Kurrent Cloud

Read more about the rebrand in the [rebrand FAQ](https://www.kurrent.io/blog/kurrent-re-brand-faq).

## What is KurrentDB

KurrentDB is a database that's engineered for modern software applications and event-driven architectures. Its event-native design simplifies data modeling and preserves data integrity while the integrated streaming engine solves distributed messaging challenges and ensures data consistency.

Download the [latest version](https://kurrent.io/downloads).
For more product information visit [the website](https://kurrent.io/kurrent).

## What is Kurrent Cloud?

 Kurrent Cloud is a fully managed cloud offering that's designed to make it easy for developers to build and run highly available and secure applications that incorporate KurrentDB without having to worry about managing the underlying infrastructure. You can provision KurrentDB clusters in AWS, Azure, and GCP, and connect these services securely to your own cloud resources.

For more details visit [the website](https://kurrent.io/kurrent-cloud).

## Licensing

View [KurrentDB's licensing information](https://github.com/kurrent-io/KurrentDB/blob/master/LICENSE.md).

## Docs

For guidance on installation, development, deployment, and administration, see the [User Documentation](https://docs.kurrent.io/).

## Getting started with KurrentDB

Follow the [getting started guide](https://docs.kurrent.io/latest.html).

## Getting started with Kurrent Cloud

Kurrent can manage KurrentDB for you, so you don't have to run your own clusters.
See the online documentation: [Getting started with Kurrent Cloud](https://docs.kurrent.io/cloud/).

## Client libraries

[This guide](https://docs.kurrent.io/clients/grpc/getting-started.html) shows you how to get started with KurrentDB by setting up an instance or cluster and configuring it.
KurrentDB supports the gRPC protocol.

### KurrentDB supported clients

- Python: [pyeventsourcing/kurrentdbclient](https://pypi.org/project/kurrentdbclient/)
- Node.js (javascript/typescript): [kurrent-io/KurrentDB-Client-NodeJS](https://github.com/kurrent-io/KurrentDB-Client-NodeJS)
- Java: [(kurrent-io/KurrentDB-Client-Java](https://github.com/kurrent-io/KurrentDB-Client-Java)
- .NET: [kurrent-io/EventStore-Client-Dotnet](https://github.com/kurrent-io/EventStore-Client-Dotnet)
- Go: [kurrent-io/KurrentDB-Client-Go](https://github.com/kurrent-io/KurrentDB-Client-Go)
- Rust: [kurrent-io/KurrentDB-Client-Rust](https://github.com/kurrent-io/KurrentDB-Client-Rust)
- Read more in the [gRPC clients documentation](https://docs.kurrent.io/clients/grpc)

### Community supported clients

- Elixir: [NFIBrokerage/spear](https://github.com/NFIBrokerage/spear)
- Ruby: [yousty/event_store_client](https://github.com/yousty/event_store_client)

Read more in the [documentation](https://docs.kurrent.io/server/latest/quick-start/#protocols-clients-and-sdks).

### Legacy clients (support ends with EventStoreDB v23.10 LTS)

- .NET: [EventStoreDB-Client-Dotnet-Legacy](https://github.com/kurrent-io/EventStoreDB-Client-Dotnet-Legacy)

## Deployment

- Kurrent Cloud - [steps to get started in Kurrent Cloud](https://docs.kurrent.io/cloud/).
- Self-managed - [steps to host KurrentDB yourself](https://docs.kurrent.io/latest/quick-start/installation).

## Communities

[Join our global community](https://www.kurrent.io/community) of developers.

- [Discuss](https://discuss.kurrent.io/)
- [Discord (Kurrent)](https://discord.gg/Phn9pmCw3t)
- [Discord (ddd-cqrs-es)](https://discord.com/invite/sEZGSHNNbH)

## Contributing

Development is done on the `master` branch.
We attempt to do our best to ensure that the history remains clean and to do so, commits are automatically squashed into a single logical commit when pull requests are merged.

If you want to switch to a particular release, you can check out the release branch for that particular release. For example:
`git checkout release/v25.0`

- [Create an issue](https://github.com/kurrent-io/KurrentDB/issues)
- [Documentation](https://docs.kurrent.io/)
- [Contributing guide](CONTRIBUTING.md)

## Building KurrentDB

KurrentDB is written in a mixture of C# and JavaScript. It can run on Windows, Linux and macOS (using Docker) using the .NET Core runtime.

**Prerequisites**

- [.NET SDK 10.0](https://dotnet.microsoft.com/download/dotnet/10.0)

Once you've installed the prerequisites for your system, you can launch a `Release` build of KurrentDB as follows:

```
dotnet build -c Release src
```

To start a single node, you can then run:

```
dotnet ./src/KurrentDB/bin/Release/net10.0/KurrentDB.dll --dev --db ./tmp/data --index ./tmp/index --log ./tmp/log
```

### Running the tests

You can launch the tests as follows:

```
dotnet test --solution src/KurrentDB.sln
```

### Build KurrentDB Docker image

You can also build a Docker image by running the command:

```
docker build --tag mykurrentdb . \
--build-arg CONTAINER_RUNTIME={container-runtime}
--build-arg RUNTIME={runtime}
```

For instance:

```
docker build --tag mykurrentdb . \
--build-arg CONTAINER_RUNTIME=noble \
--build-arg RUNTIME=linux-x64
```

**_Note:_** Because of the [Docker issue](https://github.com/moby/buildkit/issues/1900), if you're building a Docker image on Windows, you may need to set the `DOCKER_BUILDKIT=0` environment variable. For instance, running in PowerShell:

```
$env:DOCKER_BUILDKIT=0; docker build --tag mykurrentdb . `
--build-arg CONTAINER_RUNTIME=noble `
--build-arg RUNTIME=linux-x64
```

Currently, we support the following configurations:

1. Noble:

- `CONTAINER_RUNTIME=noble`
- `RUNTIME=linux-x64`

You can verify the built image by running:

```
docker run --rm mykurrentdb --insecure --what-if
```

## More resources

- [Release notes](https://docs.kurrent.io/server/latest/release-schedule/release-notes.html)
- [Beginners Guide to Event Sourcing](https://kurrent.io/event-sourcing)
- [Articles](https://kurrent.io/blog)
- [Webinars](https://kurrent.io/webinars)
- [Contact us](https://kurrent.io/contact)



## File: CONTRIBUTING.md

# Contributing to KurrentDB

## Working with Git

KurrentDB uses `master` as the main development branch. It contains all changes to the upcoming release. Older releases of KurrentDB have dedicated feature branches with the format `release/v{version}`. E.g., `release/v25.0`. Specific releases are tagged from the release branch commits.

Releases of EventStoreDB have feature branches with the format `release/oss-v{version}`. E.g. `release/oss-v24.10`.

We do our best to ensure a clean history. To do so, commits are automatically squashed into a single logical commit when pull requests are merged.

**To contribute to KurrentDB**:

1. Fork the repository.
2. Create a feature branch from the `master` (or release) branch.
3. It's recommended that feature branches use a rebase strategy (see more in [Git documentation](https://git-scm.com/book/en/v2/Git-Branching-Rebasing)). We also highly recommend using clear commit messages that represent the unit of change.
4. Rebase the latest source branch from the main repository before sending PR.
5. When ready to create the Pull Request on GitHub [check to see what has previously changed](https://github.com/kurrent-io/KurrentDB/compare).

## Documentation

Documentation files are in the [`docs`](/docs) folder. They're orchestrated in the separate [documentation repository](https://github.com/kurrent-io/documentation). The Kurrent Documentation site is publicly accessible at https://docs.kurrent.io/.

It's recommended to have documentation changes be put together with code changes.

Kurrent supports multiple versions of the documentation. Versions are kept in:
- The main (`master`) branch: The `master` branch should contain all changes related to the upcoming release. This includes both non-released changes and enhancements to documentation for existing features.
- Specific release branches: The latest and previous releases are maintained in specific branches (e.g. `release/v25.0`, `release/oss-v24.10`). We aim to keep the documentation up to date for the latest and previous LTS releases and any STS releases that occur in this timeline. For example, when v24.10 is released, Documentation will continue to be updated for v24.10 and v23.10 (whereas v22.10 will be updated on a "as time allows" basis). Read more on the release strategy [in the docs](https://docs.kurrent.io/server/latest/release-schedule/).

To update a specific database version's docs, we recommended creating a feature branch based on that versions release branch. For instance, if you want to change documentation in the `25.0` version, you would:
- Checkout `release/v25.0`
- Create a new branch and add your changes
- Create a pull request targeting the `release/v25.0` branch.

If you're unsure which branch to select, the safe choice is the main branch (`master`).

Multiple pull requests are not required for changes that should be reflected in multiple database version documentation. Contributors reviewing the pull request should label it (e.g., `cherry-pick:release/v25.0`). KurrentDB uses the [GitHub action](/.github/workflows/cherry-pick-pr-for-label.yml) based on the labels that create pull requests with cherry-picks to the target branches. It's recommended that contributors monitor notifications and make sure that cherry-picks succeed. Read more in [action documentation](https://github.com/kurrent-io/Automations/tree/master/cherry-pick-pr-for-label).

Using the previous example, assume a pull request targeting the `release/oss-v24.10` was committed. The changes should also be reflected in the upcoming release and version `25.0`. The contributor should add labels to the pull request for:
- `cherry-pick:master`,
- `cherry-pick:release/v25.0`.

_**Note:** Cherry-pick action requires changes to be rebased. If there is a merge commit, then cherry-pick will fail. It will also fail if there is a conflict with the target branch (so `target_branch` from label suffix). If those cases happen then, it's needed to do manual cherry-picks._

## Code style

Coding rules are described in the [.editorconfig file](/src/.editorconfig). This file is supported by all popular IDEs (e.g., Microsoft Visual Studio, Rider, and Visual Studio Code). Unless disabled manually, it should be automatically applied after opening the solution. We also recommend turning automatic formatting on saving to have all the rules applied.

## Licensing and legal rights

By contributing to KurrentDB:

1. You assert that contribution is your original work
2. You assert that you have the right to assign the copyright for the work
3. You accept the [Contributor License Agreement](https://gist.github.com/eventstore-bot/7a1e56c21e81f44a625a7462403298bf) (CLA) for your contribution
4. You accept the [License](LICENSE.md)

