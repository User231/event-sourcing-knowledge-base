# Sagas, Process Managers & Multi-Step Workflows — The Domain Landscape

The mechanics of sagas (one command per aggregate, choreography vs orchestration, the three saga-state storage shapes) are in [`../../implementation-patterns/multi-aggregate-commands-and-sagas.md`](../../implementation-patterns/multi-aggregate-commands-and-sagas.md). **This doc is the inventory:** which sagas show up in which industries, what their compensation events look like, what their distinctive failure modes are, and which engines (Cadence, Temporal, custom, aggregate-native) tend to back them.

Every transactional domain in `specific/` has 5–15 canonical sagas, but they get described one doc at a time. Pulled together, six saga *families* recur — once you've seen the shape, you can drop the same skeleton into a new domain.

## The six saga families that recur

| Family | Shape | Canonical examples |
|---|---|---|
| **Fan-out / scatter-gather** | Initiator emits N child commands, collects N results, terminates when all done (or timed out). | Hotel group checkout, multi-shipment order fulfillment, batch payout, mass-broadcast, multi-leg trip. |
| **Linear state machine** | Strict step sequence A→B→C→D; any step can fail and trigger a reverse cascade. | Order placement, KYC verification, claims processing, dispatch, money transfer. |
| **Time-driven retry loop** | Wait → attempt → on-fail wait-longer → eventual giveup; a clock is one of the input events. | Dunning, ACH retry, push-notification escalation, scheduled renewals, lease expiry. |
| **External-system integration** | Local aggregate ↔ external API where the external system has its own state machine and webhooks. | Payment processors, OTA channel managers, government filings, carrier (UPS/FedEx) tracking, identity providers. |
| **Multi-party coordination** | Two or more independent aggregates need to converge on a single decision (match, contract, settlement). | Marketplace dispatch (rider↔driver), cross-border payment, escrow release, double-opt-in. |
| **Compensation cascade** | A late-arriving event invalidates a sealed flow; downstream effects must be reversed (or apologised for). | Returns, refunds, chargebacks, oversold remediation, walked-guest relocation, fare adjustment after dispute. |

Most real domains run several families simultaneously. The order-placement saga in e-commerce is a linear state machine that *embeds* a fan-out (multi-shipment), an external integration (payment), and triggers a compensation cascade on cancel.

## Canonical sagas by industry

| Domain | Sagas of note | Where described |
|---|---|---|
| **Banking / payments** | Money transfer (debit→credit→settle), card auth→capture→settle, ACH lifecycle (4–5 banking days with retry windows), chargeback, FX conversion, batch payout | [`specific/banking-and-finance.md`](../specific/banking-and-finance.md) §4 |
| **E-commerce / retail** | Order placement (reserve→authorise→ship→capture), returns, multi-shipment fulfillment, oversold remediation, fraud hold (a *pause* not a compensation) | [`specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) §4 |
| **Subscriptions / billing** | Renewal, plan-change with proration, dunning (multi-week state machine), trial→paid conversion, eligibility re-verification, pause/resume | [`specific/long-running-subscriptions.md`](../specific/long-running-subscriptions.md) §4 |
| **Hotel / hospitality** | Group checkout (canonical fan-out, three implementations in Dudycz's sample), overbooking remediation, channel-manager outbox, walk-the-guest, no-show cancellation | [`specific/hotel-and-hospitality.md`](../specific/hotel-and-hospitality.md) §4 |
| **Food delivery / ordering** | Checkout (fraud→pay→delivery→merchant), multi-stage cancellation (pre-accept / post-accept / post-prep), reassignment, refund | [`specific/food-ordering-and-delivery.md`](../specific/food-ordering-and-delivery.md) §4 |
| **Ride-sharing / mobility** | Dispatch (the "hot-path saga"), trip→payment, driver-shift→earnings→payout, fare adjustment, driver cancellation compensation | [`specific/ride-sharing-and-mobility.md`](../specific/ride-sharing-and-mobility.md) §4 |
| **Chat / messaging** | Message fan-out (per-recipient delivery), push-notification routing, read-receipt propagation, federation backfill, edit/delete propagation across replicas | [`specific/chat-and-messaging.md`](../specific/chat-and-messaging.md) §4 |
| **Social feeds** | Fan-out-on-write (celebrity post → 100M timelines), follow-graph reconciliation, content moderation queue | [`specific/social-feeds.md`](../specific/social-feeds.md) |
| **Observability / incidents** | Incident lifecycle (declared→investigating→identified→monitoring→resolved→postmortem), runbook execution, deploy rollback | [`specific/observability.md`](../specific/observability.md) §3 |
| **Multi-region** | Any of the above where steps cross regions: the saga inherits cross-region RTT as a *floor* on step time | [`specific/multi-region-replication.md`](../specific/multi-region-replication.md) §5 |

The cross-cut: **the transfer saga in banking, the order saga in ecommerce, the renewal saga in subscriptions, and the group-checkout saga in hospitality are structurally the same skeleton** — initiator aggregate, process-manager state, per-step child aggregates, compensation events. The *invariants* differ; the topology doesn't.

## Compensation is event-shaped, not rollback-shaped

The single most-violated rule. A failed saga step does not "undo" earlier events; it appends new ones:

| Failed step | Compensation event (appended forward, never deletes) |
|---|---|
| Payment auth declined after stock reserved | `StockReleased` |
| Credit failed after debit posted | `WithdrawalReleased` (Monzo / Proto.Actor pattern) |
| Customer cancels post-shipment | `OrderShipmentRecalled` + `RefundIssued` |
| Toll arrives 3 days after trip closed | `FareAdjusted{delta, reason: "toll"}` — never edit `TripCompleted.fare` |
| Dispute credit after settled charge | `ChargeAdjusted{delta, reason: "dispute"}` |
| Group-checkout child failed | `GuestCheckOutFailed` → process-manager records failure, group still finalises |

Naming conventions that survive code review: `*Released`, `*Reversed`, `*Voided`, `*Adjusted`, `*Cancelled`, `*Recalled`. **Avoid `*Undone`** — it implies the original event is gone.

**Edge cases that aren't true compensation:**
- **Pause, not compensate.** Fraud holds in ecommerce keep stock reserved while ops investigate. Releasing stock too early is the canonical bug. `OrderFraudHeld` is a *state event*, not a compensation.
- **Partial compensation.** Post-prep food-delivery cancellation refunds delivery cost but forfeits food cost — `PartialRefund` is itself a domain-modelled event with its own policy.
- **Impossible compensation.** You can't unsend a push notification or unprint a shipping label. Compensate with a *follow-up* communication (`MerchantNotifiedOfCancel`, `CustomerApologySent`) rather than pretending the original didn't happen.
- **Walk-the-guest compensation.** Hotel: overbooked guest gets relocated to a partner property *plus* compensation. Modelled as `ReservationWalked{partnerProperty, compensationAmount}` + folio entry — two events for one compensation.

## Idempotency is the universal precondition

Every saga step is at-least-once in practice (network retry, processor webhook redelivery, kafka consumer rebalance). Every command into an aggregate must carry an idempotency key, and every aggregate must reject duplicates as a no-op.

**Where the key comes from:**
- **Client-generated request id** (chat `clientMsgId`, ride-share `requestId`) — the user's typed message exists once; the client retries the same id on network failure.
- **Upstream system id** (PSP `paymentIntentId`, OTA `BCOM/{reservationId}`, carrier tracking number) — the external party assigns it; we dedupe on it.
- **Content hash** — when no natural key exists; risky if "same content, different intent" is possible (two genuine `Increment(1)` commands).
- **Saga step id** — the orchestrator generates a per-step key the participant aggregate dedupes on.

Mercado Libre invested heavily in event deduplication on Spanner specifically because their checkout sagas couldn't tolerate duplicate orders. Monzo's payment-processing post stresses the same: the same instruction may arrive twice from upstream rails and the ledger must remain balanced.

## Choreography vs orchestration — domain heuristics

The mechanics doc covers the dichotomy. In practice, the choice is forced by:

| Pick **choreography** when | Pick **orchestration** when |
|---|---|
| ≤3–4 services in the flow | 5+ services |
| Compensation is local (one undo per step) | Compensation chains across steps |
| Steps are independent (any order works) | Strict ordering matters |
| Ops doesn't need a "where's the saga at?" view | Operators need to inspect / intervene live |
| Each service owns its own retry policy | Retry policy is a global concern |
| The flow rarely changes | The flow evolves frequently (need a single place to edit) |

Dudycz's hotel sample [ships three implementations of the same group-checkout flow](https://event-driven.io/en/event_driven_distributed_processes_by_example/) — saga (stateless routing + tracking aggregate), choreography (each aggregate reacts directly), and process manager (state + routing in one class, "event-driven but not event-sourced"). The trade-offs are visible side-by-side; it's the single best repo for this comparison.

## Workflow engines vs aggregate-native sagas

A second axis, orthogonal to choreography/orchestration:

| | **Workflow engine** (Cadence, Temporal, Step Functions, Camunda) | **Aggregate-native** (Eventuous, Commanded, Axon SagaManager, Dudycz-style) |
|---|---|---|
| Saga state lives in | Engine's own DB (Cassandra for Temporal, etc.) | An event-sourced aggregate in the same event store as everything else |
| Code shape | Imperative workflow function with `await activity()` calls | Event-handler functions that emit commands |
| Durable timers | First-class | Need a scheduler (Quartz, Marten's scheduled events, a `due-events` projection) |
| Retries / backoff | Configured per activity | Handler implements |
| "Where is this saga?" | Engine UI | Projection over saga aggregate stream |
| Truth of progress | Engine + your events (two truths to reconcile) | Your event stream (one truth) |
| Deploy mid-flow | Engine versions workflow code per started instance | Aggregate replay handles old events; saga must remain backward-compatible |

**Production reality:** DoorDash and Uber run Cadence/Temporal in front of aggregates ([DoorDash — Building a More Reliable Checkout Service](https://careersatdoordash.com/blog/building-a-more-reliable-checkout-service-with-kotlin/)); Stripe runs a custom orchestrator; Netflix runs Conductor; smaller teams using Marten / Eventuous / Axon usually go aggregate-native. The workflow engine wins on tooling and on flows that span dozens of steps with rich retry semantics; the aggregate-native approach wins on single-truth-of-record and on flows where the saga *is* the business event.

A common hybrid: **workflow engine drives the orchestration; each step is an aggregate command, and the engine's job is just "send command, wait for resulting event, send next command."** The event store remains the truth; the engine is durable plumbing.

## The five failure modes saga textbooks don't cover

1. **Processor webhook arrives twice; saga acks twice.** Stripe and Adyen warn webhooks may redeliver. If your saga handles `payment.succeeded` by emitting `ChargeCaptured` without checking idempotency on the event id, you've double-credited the merchant.
2. **Saga state and aggregate state disagree after a deploy mid-flow.** A new step gets added between B and C. Sagas started under the old code are at step B, expecting to go to C; the new code routes B→B'. Versioning saga code (Temporal does this natively; aggregate-native requires explicit version branching in the handler).
3. **The compensation step itself fails.** `ReleaseStock` fails because the stock service is down. Now you have authorised payment with no stock and a stuck saga. Recovery: durable retry queue for compensations + an alert + a manual-intervention `SagaPaused{reason}` event that ops can resolve.
4. **A new event type lands mid-flow because a teammate added a step.** Choreography flows are especially vulnerable: an aggregate emits a new event, an existing saga that subscribes to "all order events" reacts in an unintended way. Discipline: saga subscribes to a *named, versioned* set of events; new events default to ignored.
5. **Cross-region saga sees its initiator-region partition.** The saga state is in region A; step 3 is in region B. Region A drops off the network. Region B sees `Step3Requested` but the saga can't progress. Two regions running the same `transferId` saga is multi-region split-brain ([`specific/multi-region-replication.md`](../specific/multi-region-replication.md) §5). Solution: one region *owns* the saga; others are participants.

## Patterns that survive contact with production

- **Outbox is non-negotiable.** Never call a sibling service synchronously from a command handler — write to an outbox table in the same transaction as the aggregate append, then a relay publishes. Same applies in-region and triply in cross-region.
- **The saga itself is event-sourced.** `SagaStarted`, `StepRequested`, `StepCompleted`, `StepFailed`, `CompensationRequested`, `SagaCompleted`, `SagaPaused`. Then "where is this saga?" is a projection, not a query against engine internals.
- **Status query is a projection, not a saga method.** Customer support asks "where's order 12345?" — answer comes from the read model, not by replaying the saga.
- **Manual-intervention is a first-class state.** `SagaPaused{reason: "manual_review"}` and `SagaResumed{by: opsUserId, decision}` belong in the event log. Don't make ops twiddle a database column.
- **Saga ID is part of the correlation triple.** `(correlationId, causationId, sagaId)` stamped on every emitted event — see [`../../implementation-patterns/subscription-checkpoints-and-ordering.md`](../../implementation-patterns/subscription-checkpoints-and-ordering.md). This is what lets you join a postmortem trace to a business outcome.
- **Timeouts must be region-aware.** A 30 s single-region timeout becomes minutes across an ocean. Misconfigured timeouts mark steps "failed" while they're still running — duplicate writes follow.
- **Reserve aggressively, commit at the end.** The "reserve→authorise→commit" pattern (stock reservation, payment authorisation, settlement) lets you fail cheaply mid-flow. If you commit at every step, every step is a saga-level compensation problem.

## Where to look in the cloned repos

- **`oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/`** — three implementations of GroupCheckout (saga, choreography, process manager). The single best teaching resource for the dichotomy.
- **`oskardudycz_EventSourcing.NetCore/Sample/ECommerce/`** — ShoppingCart → Order → Shipment → Payment with realistic compensations.
- **`oskardudycz_EventSourcing.JVM/samples/distributed-processes/`** — JVM port of the same patterns.
- **`eventuous_eventuous/samples/postgres/Bookings/`** — multi-service booking + payment saga in Eventuous.

## Related docs

- [`../../implementation-patterns/multi-aggregate-commands-and-sagas.md`](../../implementation-patterns/multi-aggregate-commands-and-sagas.md) — the mechanics (one command per aggregate, choreography vs orchestration, three storage shapes).
- [`../../implementation-patterns/subscription-checkpoints-and-ordering.md`](../../implementation-patterns/subscription-checkpoints-and-ordering.md) — correlation/causation/sagaId triple, at-least-once semantics.
- [`../../implementation-patterns/subscriber-failure-strategies.md`](../../implementation-patterns/subscriber-failure-strategies.md) — retry, dead-letter, poison-pill handling for the saga's event subscribers.
- [`unbounded-and-infinite-streams.md`](unbounded-and-infinite-streams.md) — when the saga aggregate itself becomes unbounded (long-running dunning, multi-decade insurance claim).
- [Oskar Dudycz — Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/) — the practitioner reference cited throughout.
