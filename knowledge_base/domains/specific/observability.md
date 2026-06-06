# Observability — Aggregate & Stream Decomposition

How telemetry platforms (Datadog, Honeycomb, Grafana, Splunk, Elastic, SigNoz) and the incident tooling above them (PagerDuty, incident.io, FireHydrant, Nobl9) structure data — and why **most of it is not event-sourced**. An OpenTelemetry span, a Datadog "event", a Prometheus sample, a syslog line, and a `JournalEntryPosted` all look like immutable append-only records but are not interchangeable. ES applies to the *control plane* (alerts, incidents, SLOs, monitor configs, audit logs), not the *data plane* (raw spans, metrics, logs). See [../cross-cutting/unbounded-and-infinite-streams.md#c-high-frequency-telemetry--volume-not-lifetime-is-the-killer](../cross-cutting/unbounded-and-infinite-streams.md) — observability is canonical archetype C.

## 1. The vocabulary collision: "event" means several different things

| Term | Meaning | Storage | Contract |
|---|---|---|---|
| **Business event** (ES sense) | Domain state-change: `WithdrawalPosted`, `IncidentDeclared`. Loaded into an aggregate to derive state. | Event store (EventStoreDB, Kafka log + projection, Postgres event table). | Immutable, versioned, replayable. |
| **OTel "event on a span"** | Timestamped attribute on a span: `db.query.start`, `exception`. | Trace backend (Tempo, Jaeger, ClickHouse). | Immutable after ingest, **sampled**, 7–30d retention. |
| **Datadog / Grafana "event"** | Discrete marker on a timeline: `DeployStarted`, `MonitorTriggered`. | Events index (ES/OpenSearch, ClickHouse). | Append-only, query-optimised, not replay-optimised. |
| **OTel LogRecord** | Emitted log line in OTel's unified format. The spec defines Events as "the standardized format for LogRecords." | Log backend (Loki, Elastic, Splunk). | Immutable, lossy at volume, tiered retention. |
| **Metric sample** | `(name, labels, timestamp, value)` tuple. *Not* a state-change — a measurement. | TSDB (Prometheus, Mimir, VictoriaMetrics). | Append-only, pre-aggregated, downsampled. |

The OTel spec is explicit: "Events are OpenTelemetry's standardized format for LogRecords" ([Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)). That has nothing to do with DDD events. **Rule**: if it represents a *decision the system made* and you want to replay to derive state, it's a business event and ES applies. If it represents a *measurement* you want to slice dimensionally, it's telemetry and a columnar TSDB applies.

## 2. What IS event-sourced and what is NOT

| Concept | ES? | Why |
|---|---|---|
| **Span** | No | Sampled (head and/or tail), lossy, columnar. Replay-from-zero is meaningless when 90%+ are dropped by design. |
| **Metric sample** | No | Pre-aggregated time-series. The OTel metrics "Event model" is the SDK input format, not a durable history ([Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/)). Pull-based scrape is lossy on agent restart. |
| **Log line** | No (mostly) | Append-only in storage, but treated as a query workload, not a replay workload. |
| **Trace** (DAG of N spans) | Conceptually closest; **not** stored as one | Reconstructed *at query time* from sampled spans. See §6. |
| **Alert** (firing instance) | **Yes** | Lifecycle aggregate; state transitions durable; replay meaningful. |
| **Incident** | **Yes** — saga-shaped | Multi-step workflow with timeline, ownership, postmortem. The textbook ES case here. |
| **Monitor / Detector** | **Yes** (config-as-events) | Created, edited, paused, deleted. Many teams CRUD this and regret it. |
| **SLO + error budget period** | **Yes** | Period-rollover — identical shape to banking's "close the books." |
| **OnCallShift / EscalationPolicy** | **Yes** | Roster events: `ShiftStarted`, `OverrideApplied`, `EscalationFired`. |
| **Deployment** | **Yes** | Drives Grafana annotations, Datadog event markers, SLO change-attribution. |
| **Audit log / SIEM record** | **Yes** — purest ES case here | Immutable, never deleted, replayable for forensics, legally append-only. |
| **Synthetic check run** | Edge case | Usually telemetry; sometimes aggregated into window summaries. |

The non-ES rows are the bulk of every observability bill — not second-class, just a different contract.

## 3. Aggregate boundaries (where ES applies)

The ES surface area is the **control plane**: things with a lifecycle, an owner, and a decision history.

| Aggregate | Why a boundary | Lifecycle |
|---|---|---|
| **Monitor / Detector** | Config artefact with edit history. Audit matters ("who muted this in March?"). | Created → Active → Muted → Edited → Disabled → Deleted (soft) |
| **Alert** (one *firing* of a rule) | Discrete short-lived instance. | Pending → Firing → Acknowledged → Resolved → Auto-Closed |
| **Incident** | Multi-step saga: declared → triaged → mitigated → resolved → postmortem. | Declared → Investigating → Identified → Monitoring → Resolved → Postmortem |
| **OnCallShift** | Roster occurrence with handoffs, overrides, escalations. | Scheduled → Started → HandedOff → Ended |
| **EscalationPolicy** | Config aggregate, analogous to Monitor. | Created → Edited → Deactivated |
| **SLO** + **SLOPeriod** | SLO is long-lived config; each calendar window is a sub-aggregate with open/close + burn summary. | SLO: Defined → Active → Retired. Period: Opened → BudgetConsumed × N → Closed |
| **Deployment** | Recorded for SLO attribution, change tracking, dashboard annotations. | Started → Succeeded / Failed / RolledBack |
| **Runbook execution** | Step-by-step trace, saga-like. | Triggered → StepCompleted × N → Completed / Aborted |
| **AuditLogEntry** | Pure append-only forensic record. | Recorded (immutable forever) |

**Not boundaries**: Service / Host / Container are *resources* (OTel terminology) — typically CMDB rows, not ES aggregates, because their state derives from agent heartbeats not authoritative commands. Trace — see §6. Dashboards — Git-backed JSON is sufficient audit for most teams.

## 4. Stream-id naming patterns

```
monitor-{monitorId}                       # config lifecycle, all edits
alert-{alertId}                           # one stream per firing instance
incident-{incidentId}                     # the saga stream
oncall-shift-{scheduleId}-{shiftDate}     # daily-bucketed roster events
escalation-policy-{policyId}
slo-{sloId}                               # SLO definition lifecycle
slo-{sloId}-{period}                      # one stream per error-budget window (e.g. slo-checkout-2026-05)
deployment-{deploymentId}                 # per release/rollout
runbook-execution-{executionId}
audit-{tenantId}-{yyyyMMdd}               # day-sharded forensic log
```

`alert-{alertId}` is **one stream per firing**, not per monitor. A flapping monitor fires hundreds of times; conflating produces an unbounded firehose with no natural close. Each alert is short-lived (minutes-to-days) and closes cleanly with `AlertResolved`.

The SLO pattern (`slo-{id}-{period}`) is structurally identical to banking's [`account-{id}-{period}`](banking-and-finance.md#2-stream-id-naming-patterns) — see Dudycz, [Closing the Books](https://event-driven.io/en/closing_the_books_in_practice/). Each period opens with `BudgetPeriodOpened{budgetSeconds, target}` and closes with `BudgetPeriodClosed{consumedSeconds, breached}`. You never replay 12 months of burn events to know today's remaining budget.

`audit-{tenantId}-{yyyyMMdd}` is day-sharded because audit logs are write-heavy, read-rarely, and retention-bounded by regulation rather than domain lifecycle.

## 5. Key events per aggregate

### Monitor / Detector
```
MonitorCreated   { monitorId, name, query, thresholds, ownerTeam, createdBy }
MonitorEdited    { changedFields, previousValues, editedBy, reason }
MonitorMuted     { mutedBy, until, reason }   # planned maintenance
MonitorUnmuted   { unmutedBy }
MonitorDisabled  { disabledBy, reason }
MonitorDeleted   { deletedBy }                # soft delete; event remains
```
Most teams start with CRUD on a `monitors` table and lose the ability to answer "who muted the prod-checkout latency alert at 02:14, and why" during the next postmortem.

### Alert (one stream per firing instance)
```
AlertPending          { alertId, monitorId, evaluatedAt, currentValue, threshold }
AlertFired            { firedAt, severity, dimensions{service, env, region, ...} }
AlertNotified         { channel, recipient, notifiedAt, deliveryRef }
AlertAcknowledged     { acknowledgedBy, acknowledgedAt, comment }
AlertEscalated        { escalatedTo, escalationStep, reason }
AlertSuppressed       { suppressedBy, untilEvent, reason }
AlertAutoResolved     { resolvedAt, finalValue }     # metric returned to normal
AlertManuallyResolved { resolvedBy, resolvedAt, comment }
AlertFlapping         { flapCount, windowSeconds }
```

### Incident (the saga aggregate)
```
IncidentDeclared       { incidentId, severity, declaredBy, summary, affectedServices }
IncidentLinkedToAlert  { alertId }                   # many alerts -> one incident
RoleAssigned           { role: 'commander'|'comms'|'scribe', userId }
StatusUpdatePosted     { author, body, channels[] }
MitigationApplied      { description, appliedBy, mitigationRef }
ImpactConfirmed        { startTime, endTime, customersAffected, revenueEstimate }
SeverityChanged        { from, to, reason }          # sev3 -> sev1 mid-flight
IncidentMerged         { mergedIntoIncidentId }
IncidentResolved       { resolvedBy, resolvedAt, resolutionSummary }
PostmortemPublished    { url, publishedBy, actionItemIds[] }
```
FireHydrant models incidents through phases — Started, Active, Post-incident, Closed — with milestones inside each ([FireHydrant Lifecycle Phases](https://docs.firehydrant.com/docs/incident-milestones-lifecycle-phases)). PagerDuty's equivalent is Triggered → Acknowledged → Resolved with escalation events between ([PagerDuty Incidents](https://support.pagerduty.com/main/docs/incidents)).

### SLO period (`slo-{sloId}-{period}`)
```
BudgetPeriodOpened   { period, startedAt, target, budgetSeconds, sliQuery }
BudgetConsumed       { atTime, secondsBurned, runningTotal, attributedDeploymentId? }
BurnRateAlertFired   { burnRate, threshold, windowMinutes }   # e.g. 14.4x fast-burn
DeploymentAttributed { deploymentId, budgetConsumed }
BudgetExhausted      { exhaustedAt, deployFreezeDecision }
BudgetPeriodClosed   { closedAt, totalConsumed, breached, postmortemRef? }
```
Nobl9's calendar-aligned window matches: a monthly window opens with a fresh ~43-min budget for a 99.9% SLO and refills at month boundary ([Nobl9 — Understanding Error Budgets](https://www.nobl9.com/service-level-objectives/error-budget)). Rolling 30-day windows are a projection over the last 30 days of `BudgetConsumed`, not a closed-period aggregate.

### OnCallShift, Deployment, AuditLogEntry
```
ShiftScheduled / ShiftStarted / OverrideApplied{overriddenUserId, replacementUserId, reason}
EscalationTriggered{alertId, fromUserId, toUserId, atLevel} / ShiftHandedOff / ShiftEnded

DeploymentStarted{deploymentId, service, version, env} / RolloutAdvanced{stage}
DeploymentSucceeded{gitSha} / DeploymentRolledBack{reason, triggerAlertId?}

AuditLogEntryRecorded { entryId, tenantId, actor, action, resourceType, resourceId,
                        beforeHash, afterHash, ipAddress, userAgent, recordedAt }
```
The audit entry is one event type, one structure, immutable. Hashing before/after state lets you detect tampering without storing raw payloads in the audit stream.

## 6. Traces: the thing that LOOKS like ES but is not

A trace is a DAG of spans. Each span carries `trace_id` (128-bit), `span_id` (64-bit), `parent_span_id`, name, kind, start/end, attributes, and zero or more events-on-spans ([OTel spec](https://opentelemetry.io/docs/specs/otel/overview/)). Spans can `link` to other traces — arbitrary DAG topologies. That sounds like an event-sourced aggregate, and "just store traces in our event store" comes up regularly. It is wrong for four reasons:

1. **Sampling is the whole point.** Head-sampling drops a configurable fraction (often 99%) at the SDK; tail-sampling drops most traces *after* reconstruction, keeping only slow/errored ones ([Jaeger features](https://www.jaegertracing.io/docs/2.13/features/)). An event store assumes you have every event.
2. **Replay isn't meaningful.** A trace is a *query result*, not a state machine; there's no aggregate to rehydrate.
3. **Storage is columnar.** Tempo writes Parquet to S3/GCS. Jaeger backends include Cassandra, OpenSearch, increasingly ClickHouse — Uber-scale Jaeger uses Kafka for ingestion plus ClickHouse for query, billions of spans/day ([Why we migrated Jaeger to ClickHouse](https://dok.community/blog/why-we-decided-to-migrate-our-jaeger-storage-to-clickhouse/)). None optimised for per-aggregate optimistic-locked appends.
4. **Retention is short.** 7–30 days typical; a regulator asking "replay 2023" doesn't get spans.

What you *can* do is treat **trace_id as a correlation key**, like a saga-id. Stamp the current `trace_id`/`span_id` on every business event emitted during request handling. Trace = short-retention causal view of *how*; event stream = long-retention immutable view of *what*. Datadog calls this trace correlation via the standard `trace_id`/`span_id`/`service`/`env`/`version` tags injected by the agent ([Datadog Observability Explained](https://technoroots.org/insights/datadog-observability-explained-metrics-logs-and-traces-and-how-they-work-together-8rM6B)). The DAG-shaped nature is structurally the same family of problem as branching history (archetype E in [../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories](../cross-cutting/unbounded-and-infinite-streams.md)) — the operational answer: don't event-source it; project it from sampled spans.

## 7. Hot path / cold path / control plane — the three-tier split

Three storage tiers, three contracts:

- **Hot path (data plane).** Raw spans, metric samples, log lines at 100k–10M items/sec. TSDB (Prometheus, Mimir, VictoriaMetrics), trace backend (Tempo/Jaeger), log backend (Loki/Elastic/Splunk), wide-event columnar (Honeycomb, ClickHouse, SigNoz). Retention hours–30d. Replay not meaningful.
- **Cold path (warehouse).** Sampled spans, downsampled metrics, log archives. S3+Parquet, ClickHouse, Druid, Pinot. Retention 90d–years. Replay at query time, columnar. Used for ML, capacity planning, dispute reconstruction, forensics.
- **Control plane (event-sourced).** `monitor-{id}`, `alert-{id}`, `incident-{id}`, `slo-{id}-{p}`, `oncall-{id}-{d}`, `deploy-{id}`, `audit-{tenant}-{day}`. EventStoreDB / Kafka+projection / Postgres event table. Retention years (audit: ~forever). Replay required.

Structurally identical to ride-sharing's GPS pings (raw → Redis/Hadoop; milestones → event store — see [ride-sharing-and-mobility.md §5](ride-sharing-and-mobility.md#5-hot-path-vs-cold-path)). Observability derives `AlertFired` and `SLOBudgetExhausted` from metric thresholds and `IncidentDeclared` from human/automated decisions. Control-plane subscribers consume the hot path read-only — they query Prometheus, look at recent spans, search logs, but don't write to it. The hot path is a cache rebuildable from agents; the control plane is the system of record.

## 8. Why metrics and raw telemetry aren't event-sourced

Metrics are the most common candidate for confusion. The Prometheus pull model makes the non-ES nature concrete:

- **Pull-based scrape, not push.** Prometheus polls `/metrics` on a schedule. A scrape is a snapshot of *current* counter values — between two scrapes you don't know if a counter went up by 5 once or by 1 five times. The pull model is "the core principle that allows Prometheus to be lightweight and reliable" ([groundcover — Prometheus Scraping](https://www.groundcover.com/learn/observability/prometheus-scraping)) — opposite of an event log.
- **Pre-aggregation by design.** The OTel metrics data model defines three layers — Event (SDK input), in-flight (OTLP), TimeSeries (exporter) — to aggregate before storage. You store summaries, not events.
- **Lossy at every layer.** Agent restarts lose buffered samples; downsampling averages away precision; recording rules collapse cardinality.
- **Remote-write is not "push to event store."** The spec is explicit: stateless, no inter-message communication, scraper-to-receiver propagation only ([Remote-Write Spec](https://prometheus.io/docs/specs/prw/remote_write_spec/)).

Two further pressures break ES patterns for raw telemetry overall. **Cardinality**: a single high-cardinality dimension (`user_id`, `trace_id`, `container_id`) multiplied across tags blows up TSDB indices. ClickHouse markets itself as the answer to "the high-cardinality trap" because sparse indices and aggressive compression let you query billions of unique values without pre-aggregation ([ClickHouse — High-Cardinality Trap](https://clickhouse.com/resources/engineering/high-cardinality-slow-observability-challenge)). Honeycomb's "wide events" philosophy goes further: store the full structured event with every dimension and let the query engine slice it ([Honeycomb — Structured Events](https://www.honeycomb.io/blog/structured-events-basis-observability); Charity Majors' [Observability 2.0](https://www.honeycomb.io/blog/time-to-version-observability-signs-point-to-yes)). **Retention**: ES replay-from-zero assumes history is bounded or compactable. Raw spans/metrics/logs are *deliberately* dropped after 7–30d; there's no aggregate to snapshot. The industry reached for columnar OLAP (ClickHouse, Druid, Pinot) instead of event stores — write once, query dimensionally, drop on TTL.

If you need exact counts (revenue per request, refunds), use business events. If you need observability ("p99 latency by service over 5min"), use metrics. They are not substitutes.

## 9. The closest pure-ES use case: audit logs / SIEM

Security audit logs are the one place in this stack where ES applies cleanly and without caveats:

- **Immutable by mandate**, not convention — SOX, HIPAA, PCI-DSS, ISO 27001 all require append-only with tamper-evidence.
- **Replayable for forensics.** "Show me everything user X did between 02:00 and 03:00 on March 14" is exactly a stream-replay query.
- **Tamper-detection** via cryptographic hashing — entries can't be silently altered ([Audit Trails as Evidence](https://www.cybersecurityintelligence.com/blog/audit-trails-as-evidence-from-logs-to-proof-8989.html)).
- **Retention measured in years.**
- **Never the source of operational state** — a parallel forensic record. The operational system reads from its own state; the audit log answers "what did the system do, and who told it to."

Splunk, Elastic, Datadog, and cloud object stores all support append-only-with-hashing. The mental model is identical to banking's journal stream ([banking-and-finance.md §5](banking-and-finance.md#5-double-entry-ledger-treatment)).

## 10. Correlation IDs — stitching telemetry to business events

Every business event should carry telemetry correlation context:

```
PaymentCaptured {
  paymentId, amount, currency, capturedAt,
  traceId, spanId,                          # telemetry correlation
  sagaId, causationId, correlationId        # ES correlation triple
}
```

`traceId` lets a postmortem jump from "this payment was captured at 14:02:18" to the full trace of how it happened. `sagaId`/`causationId`/`correlationId` are the standard ES triple (see [../../implementation-patterns/subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md)) and let you walk the causal chain *between* business events across service boundaries. OpenTelemetry propagates trace context via W3C `traceparent`/`tracestate` headers automatically ([OTel Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/)); event-emission code only reads them off the current context and stamps them on the event. Telemetry tells you *how*; the event stream tells you *what*. Joining by `trace_id` is how you debug production.

## 11. Synthetic monitoring and CI/CD as ES candidates

Synthetic checks and CI/CD pipelines straddle the line. Each run is short-lived, structured, and lifecycle-shaped — but at high frequency they become telemetry.

- **Per-pipeline / per-deploy events** (`DeploymentStarted`, `RolloutAdvanced`, `DeploymentSucceeded`, `DeploymentRolledBack`) — ES applies. These drive Grafana annotations ([Grafana — Annotate visualizations](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/annotate-visualizations/)), fan out as Datadog events, and feed SLO change-attribution. They are the *bridge* events that show up on every metric timeline.
- **Synthetic check runs at 1Hz** — usually not. Aggregate into `SyntheticCheckWindow{from, to, successCount, failureCount, p99Latency}` summaries; raw runs are TSDB samples.

Distinguishing question: does anything downstream replay this to derive state? Deployments drive incident triage, change-failure-rate metrics, deploy-freeze policies — yes. Individual synthetic probes feed dashboards — no.

## 12. Real-world gotchas

- **Don't conflate the monitor with the alert.** A flapping monitor produces hundreds of firings; appending them all to one `monitor-{id}` stream is an unbounded firehose. Each firing is its own short-lived `alert-{alertId}` aggregate.
- **Auto-resolve vs manual resolve are different events.** `AlertAutoResolved` (metric returned to normal) is not the same as `AlertManuallyResolved` (human declared fixed). Different downstream consequences (incident closure, postmortem).
- **Incident-to-alert linkage is many-to-one and changes over time.** A single incident usually aggregates many alerts firing for the same root cause. Model `IncidentLinkedToAlert` as a separately-appendable event, not a constructor field.
- **SLO burn-rate alerts are derived events.** Fast-burn (14.4× over 1h) and slow-burn (1× over 6h) are projections over `BudgetConsumed`. Storing them *instead of* the underlying history loses the rollover semantics.
- **Deployment attribution to SLO budget is best-effort.** Model attribution as a separate `DeploymentAttributed` event that can be revised, never as a property of `BudgetConsumed`.
- **On-call overrides are easy to break.** `OverrideApplied` must carry both original and replacement userId plus the time range — otherwise you can't answer "who *should* have been paged at 02:14 last Tuesday."
- **Trace IDs are not idempotency keys.** A trace ID identifies a request flow, not a unique business operation. Retries of the same idempotent payment have *different* trace IDs. Don't dedupe on trace ID.
- **Wide-event ingestion ≠ ES.** Honeycomb-style wide structured events are a query optimisation, not an aggregate model. Emit business events to your event store from the same code paths.
- **Audit log retention vs PII deletion.** GDPR right-to-erasure collides with "audit log is immutable forever." Fixes: store hashes of PII (not raw values), or crypto-shred (per-subject key, delete the key on erasure — entry stays structurally intact but unreadable). Same pattern as [ecommerce-and-retail.md](ecommerce-and-retail.md); cross-domain treatment in [`../cross-cutting/compliance-pii-and-immutability.md`](../cross-cutting/compliance-pii-and-immutability.md).

## 13. Sources & case studies

- **OpenTelemetry** — [Overview](https://opentelemetry.io/docs/specs/otel/overview/), [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/) (Events as standardized LogRecords), [Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/), [Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/).
- **Honeycomb / Charity Majors** — [Structured Events Are the Basis of Observability](https://www.honeycomb.io/blog/structured-events-basis-observability), [Time to Version Observability: Observability 2.0](https://www.honeycomb.io/blog/time-to-version-observability-signs-point-to-yes); [All you need is Wide Events](https://isburmistrov.substack.com/p/all-you-need-is-wide-events-not-metrics).
- **Datadog** — [Event Management](https://docs.datadoghq.com/service_management/events/), [Events API](https://docs.datadoghq.com/api/latest/events/), [Metrics Types](https://docs.datadoghq.com/metrics/types/).
- **Prometheus** — [Remote-Write spec](https://prometheus.io/docs/specs/prw/remote_write_spec/); [Pull vs Push tradeoffs](https://www.groundcover.com/learn/observability/prometheus-scraping).
- **Trace storage** — [Jaeger vs Tempo (SigNoz)](https://signoz.io/blog/jaeger-vs-tempo/), [Why we migrated Jaeger to ClickHouse](https://dok.community/blog/why-we-decided-to-migrate-our-jaeger-storage-to-clickhouse/), [ClickHouse for OTel Collector data](https://clickhouse.com/resources/engineering/best-resources-storing-opentelemetry-collector-data), [Jaeger features](https://www.jaegertracing.io/docs/2.13/features/).
- **Columnar engines** — [ClickHouse on high-cardinality](https://clickhouse.com/resources/engineering/high-cardinality-slow-observability-challenge), [ClickHouse vs Druid vs Pinot](https://www.tinybird.co/blog/clickhouse-vs-druid), [SigNoz on ClickHouse + OTel](https://clickhouse.com/blog/signoz-observability-solution-with-clickhouse-and-open-telemetry).
- **Grafana annotations** — [Annotate visualizations](https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/annotate-visualizations/), [Automatic annotations with Loki](https://grafana.com/blog/2019/12/09/how-to-do-automatic-annotations-with-grafana-and-loki/).
- **PagerDuty / FireHydrant / incident.io** — [PagerDuty Incidents](https://support.pagerduty.com/main/docs/incidents), [PagerDuty Event-Driven Automation](https://www.pagerduty.com/resources/automation/learn/event-driven-automation/), [FireHydrant Lifecycle Phases](https://docs.firehydrant.com/docs/incident-milestones-lifecycle-phases), [FireHydrant Events Data Model](https://docs.firehydrant.com/docs/events-data-model), [incident.io vs FireHydrant](https://incident.io/blog/incident-io-vs-firehydrant-slack-native-incident-management-2025).
- **SLO / Nobl9** — [Understanding Error Budgets](https://www.nobl9.com/service-level-objectives/error-budget), [Complete Guide to Error Budgets](https://www.nobl9.com/resources/a-complete-guide-to-error-budgets-setting-up-slos-slis-and-slas-to-maintain-reliability), [Nobl9 + Datadog](https://docs.nobl9.com/sources/create-slo/datadog/).
- **Splunk / SIEM / audit** — [Audit Trails as Evidence](https://www.cybersecurityintelligence.com/blog/audit-trails-as-evidence-from-logs-to-proof-8989.html), [Immutable Audit Log Guide](https://www.hubifi.com/blog/immutable-audit-log-guide), [Splunk audit integration](https://hoop.dev/blog/how-splunk-audit-integration-and-deterministic-audit-logs-allow-for-faster-safer-infrastructure-access).
- **Closing the books** (cross-domain) — Oskar Dudycz, [Closing the Books in Practice](https://event-driven.io/en/closing_the_books_in_practice/); Mathias Verraes, [Summary Event pattern](https://verraes.net/2019/05/patterns-for-decoupling-distsys-summary-event/).

## Cross-references

- [../cross-cutting/unbounded-and-infinite-streams.md#c-high-frequency-telemetry--volume-not-lifetime-is-the-killer](../cross-cutting/unbounded-and-infinite-streams.md) — observability is explicitly called out as archetype C.
- [ride-sharing-and-mobility.md](ride-sharing-and-mobility.md) — GPS pings hot/cold pattern is the direct analogue of raw-telemetry / milestone-events here.
- [../../implementation-patterns/subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md) — correlation / causation / sagaId triple used to stitch business events to telemetry.
- [banking-and-finance.md §2](banking-and-finance.md#2-stream-id-naming-patterns) — period-sharded stream pattern used identically for `slo-{id}-{period}`.

## Key takeaway

Observability moves enormous volumes of data that all looks event-shaped, and very little of it should actually be event-sourced. Raw spans, metrics, and logs belong in columnar TSDB / wide-event stores designed for sampling, high cardinality, and short retention. ES applies cleanly to the *control plane above* the telemetry — alerts, incidents, SLO budget periods, monitor configs, on-call shifts, deployments, audit logs — where lifecycles are real, replay is meaningful, and the audit trail is the product. Keep them on opposite sides of a clean line: telemetry tells you *how*; the event stream tells you *what* and *who decided what to do about it*.
