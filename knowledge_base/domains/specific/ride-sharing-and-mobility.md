# Ride-Sharing & Mobility — Aggregate & Stream Decomposition

How real companies (Uber, Lyft, Grab, DoorDash, Bolt) decompose ride-sharing and on-demand mobility into aggregates and event streams. The defining tension in this domain: **not everything should be event-sourced**. Hot-path matchmaking lives in memory; only milestones become durable events.

Ride-sharing is the canonical two-sided marketplace. The cross-domain treatment of marketplace mechanics (Demand/Supply/Match anchor aggregates, match-as-CAS, offer pattern, surge as projection, two-sided reputation, multi-party settlement, cancellation by any party, cold-start dynamics) is in [`../cross-cutting/marketplaces-and-matching-engines.md`](../cross-cutting/marketplaces-and-matching-engines.md) — this doc is the ride-specific deep dive.

## 1. Aggregate boundaries used in practice

Real systems converge on a small set of aggregates because lifecycle, contention, and consistency requirements differ sharply between them. Uber's Fulfillment Platform is the most public reference — they explicitly model **Trip** (the unit of work) and **Supply** (the worker/vehicle) as the two anchor entities, each backed by a hierarchical statechart ([Uber blog](https://www.uber.com/blog/fulfillment-platform-rearchitecture/)).

| Aggregate | Why a boundary | Lifecycle / contention notes |
|---|---|---|
| **Trip** (a.k.a. `Booking` at Grab, `Order` at DoorDash, `Job` in Uber Fulfillment) | Strong invariants: a trip has exactly one assigned driver, one fare, one payment outcome. Multi-step state machine. | Aggregate root. Long-lived (minutes-hours). Composed of waypoints (pickup/drop-off/via). Optimistic locking on state transitions. |
| **Driver / Supply** | Independent lifecycle (online/offline/on-trip). High write rate from app heartbeats. | Distinct from `Trip` because a driver outlives any single trip. Internally split: cold state in the aggregate, hot state (location, online flag) in Redis/Spanner row. |
| **Rider** | Owns auth, payment methods, saved places, ratings. | Low write rate. Often CRUD, not event-sourced — only `RiderRegistered`, `PaymentMethodAdded`, `RiderBanned` etc. live in a stream. |
| **Vehicle** | Capacity, product class (UberX/XL/Black), inspection state. | Separate from driver because rental fleets, scooters, and bikes are vehicle-centric without a permanent operator. Lime/Bird treat **Vehicle** as the primary aggregate. |
| **Dispatch / Offer** | Short-lived, high contention. One trip may produce N offers to N drivers with TTLs. | Uber models this as an **Offer** entity inside Fulfillment — created, accepted, declined, expired. Lives seconds-to-minute. |
| **Pricing / Surge cell** | Aggregated by geo-cell (H3 hex), not by trip. Per-cell supply/demand ratios. | Not event-sourced in the DDD sense — it's a streaming aggregation (Flink) over location and request events, with a multiplier *snapshot pinned to a `TripRequested` event* for fare integrity. |
| **Payment / Charge** | Strong consistency with PSP, idempotency keys, refund/dispute lifecycle. | Always separate. Trip emits `TripCompleted`; payment saga authorises/captures asynchronously. |
| **DriverShift / EarningsPeriod** | Daily/weekly rollup boundary; tax & payout semantics. | Aggregates many trip-derived earning events. DoorDash's "Earn by Time" mode is a shift-level state machine on top of delivery events. |
| **Rating** | Separate aggregate per direction (`RiderRatedDriver`, `DriverRatedRider`). | Decoupled because ratings arrive minutes-to-hours after trip completion and must not block trip closure. |

### Why `Location` is typically NOT event-sourced

Driver GPS pings arrive at ~1–4 Hz per active driver, multiplied by millions of drivers. The historical value of an individual ping is near zero, and the volume would dwarf every other event stream. Uber, Lyft, and Grab all keep live driver location in an in-memory geo-index (H3 hex shards, Redis-backed) and only **milestone** events — `DriverArrivedAtPickup`, `TripStarted`, `TripCompleted`, `WaypointReached` — are appended to the trip stream. The raw GPS trace is persisted to a cheap columnar store (Hadoop/Parquet) for ML and disputes, not to the event store.

## 2. Stream-id naming patterns

| Pattern | Used for | Notes |
|---|---|---|
| `trip-{tripId}` / `booking-{bookingId}` | Trip aggregate stream | Stable for life of trip; archived after completion + retention window. |
| `driver-{driverId}` | Driver lifecycle (onboarding, online/offline, suspensions) | One stream per driver, append-only for years. Heartbeat pings do NOT go here. |
| `rider-{riderId}` | Rider profile/account events | Low volume. |
| `vehicle-{vehicleId}` | Vehicle/scooter/bike events | Primary stream in micromobility (Lime, Bird). |
| `dispatch-{tripId}` or `offer-{offerId}` | Match attempts for a single trip | Short-lived; can be sub-stream under `trip-{tripId}` or its own stream depending on retention policy. |
| `shift-{driverId}-{date}` | Daily shift / earnings rollup | Materialised from trip-payout events. |
| `payment-{tripId}` or `charge-{chargeId}` | Payment saga state | Separate stream so PCI scope is isolated. |
| `surge-cell-{h3Index}-{minuteBucket}` | Time-bucketed surge snapshots | Rarely a true stream — usually a key in a time-series store. |

Grab's fare-storage system follows this pattern: a stream of `ADD`/`SUB`/`SET` fare events per booking, where replaying yields the current fare and the audit trail simultaneously ([Grab Engineering](https://engineering.grab.com/democratising-fare-storage-at-scale-using-event-sourcing)).

## 3. Key events per aggregate

### `trip-{tripId}` (the core stream)

| Event | Typical fields |
|---|---|
| `TripRequested` | `riderId, pickup{lat,lng,h3}, dropoff{lat,lng,h3}, productType, surgeMultiplier, upfrontFare, requestedAt` |
| `DriverOffered` | `offerId, driverId, etaSeconds, expiresAt` |
| `DriverOfferDeclined` / `DriverOfferExpired` | `offerId, driverId, reason` |
| `DriverMatched` | `driverId, vehicleId, etaSeconds, acceptedAt` |
| `DriverArrivedAtPickup` | `driverId, arrivedAt, gpsAccuracy` |
| `TripStarted` | `startedAt, originLocation, odometerStart` |
| `WaypointReached` | `waypointIndex, reachedAt, location` |
| `TripCompleted` | `endedAt, distanceMeters, durationSeconds, computedFare, route` |
| `TripCancelled` | `cancelledBy{rider|driver|system}, reason, cancellationFee, atState` |
| `TripNoShow` | `declaredBy=driver, waitedSeconds` |
| `TripForceCompleted` | `byOperatorId, reason` (ops override for stuck trips) |
| `FareAdjusted` | `delta, reason{toll|wait_time|route_change|dispute_credit}` (compensating event, never an edit — the marketplace-ledger rule from [`../cross-cutting/ledgers-and-double-entry.md`](../cross-cutting/ledgers-and-double-entry.md)) |
| `RatingSubmitted` | `byParty, score, comment` (often projected from rating aggregate) |

### `driver-{driverId}`
`DriverRegistered`, `DriverDocumentVerified`, `DriverApproved`, `DriverWentOnline{location, productType}`, `DriverWentOffline{reason}`, `DriverSuspended`, `DriverReinstated`, `DriverVehicleAssigned`, `DriverPayoutSettled`.

Note: `DriverLocationUpdated` is intentionally absent — pings live in the hot store.

### `vehicle-{vehicleId}` (especially for scooters/bikes)
`VehicleAddedToFleet`, `VehicleDeployed`, `VehicleReserved`, `RentalStarted`, `RentalEnded`, `VehicleReportedDamaged`, `VehicleRetrieved`, `BatterySwapped`, `VehicleRetired`.

### `dispatch-{tripId}` / `offer-{offerId}`
`OfferCreated`, `OfferDelivered`, `OfferAccepted`, `OfferDeclined`, `OfferExpired`, `OfferRebroadcast`, `MatchingExhausted` (no driver after N rounds).

### `payment-{tripId}`
`PaymentAuthorizationRequested`, `PaymentAuthorized` (pre-trip hold), `PaymentCaptured`, `PaymentFailed`, `RefundIssued`, `TipAdded`, `ChargebackOpened`, `DisputeResolved`.

### `shift-{driverId}-{date}`
`ShiftStarted`, `TripEarningRecorded`, `BonusApplied` (quest, surge guarantee), `IncentiveEarned`, `TipReceived`, `ShiftEnded`, `EarningsFinalized`, `PayoutInitiated`.

## 4. Cross-aggregate processes / sagas

Dispatch is the canonical "hot-path saga" (sub-second matching against a hot in-memory index, decisions persisted as events); payment, shift/earnings, and fare-adjustment are slower compensation-heavy sagas behind it. For the cross-domain inventory of saga families, see [`../cross-cutting/sagas-and-multi-step-workflows.md`](../cross-cutting/sagas-and-multi-step-workflows.md).

### 4.1 Request → Match → Accept (with timeouts)

```
Rider.RequestRide (command)
  -> Trip.TripRequested
  -> DispatchProcessManager picks up event
      -> query hot location index (H3 hex) for nearby drivers
      -> Dispatch.OfferCreated -> push to driver app
      -> wait for OfferAccepted with TTL (~15s)
          if expired or declined:
            -> OfferExpired / OfferDeclined
            -> rebroadcast: next candidate(s)
          if N rounds without accept:
            -> MatchingExhausted
            -> Trip.TripCancelled(reason=no_driver_found, by=system)
  -> on OfferAccepted:
      -> Trip.DriverMatched
      -> Driver.DriverStartedTrip (lock driver to trip)
```

The dispatch process is the canonical "hot path saga": it lives partly in memory (Lyft computes a bipartite ILP recomputed every few seconds — [Solving Dispatch in a Ridesharing Problem Space](https://eng.lyft.com/solving-dispatch-in-a-ridesharing-problem-space-821d9606c3ff)), but its decisions are recorded as durable events on the `trip-{tripId}` and `dispatch-{tripId}` streams.

### 4.2 Trip lifecycle → fare calculation → payment

```
TripStarted -> (driver app reports waypoints) -> TripCompleted
TripCompleted (with raw distance/duration/route)
  -> FareCalculationProcess
      reads: surge snapshot pinned at request, productType, tolls, wait time
      emits: Trip.FareCalculated{base, surge, tolls, fees, total}
  -> PaymentSaga
      Payment.AuthorizationCaptured (using earlier hold)
      on fail: Payment.RetryScheduled / PaymentFailed -> Trip.PaymentOutstanding
  -> DriverEarningsProcess
      -> Shift.TripEarningRecorded
```

Uber's Schemaless used a column-trigger mechanism: when the `BASE` cell of a trip row was written, billing fired ([Schemaless Part 3](https://www.uber.com/blog/schemaless-part-three-datastore-triggers/)). In event-sourced terms, that's `TripCompleted` on the trip stream subscribed to by the billing service.

### 4.3 Cancellation flow (with fees)

```
RiderCancel / DriverCancel (command)
  -> Trip.TripCancelled{by, atState}
  -> CancellationFeePolicy reads atState
      if state in {DriverEnRoute(>2min), DriverArrived}:
        Trip.CancellationFeeApplied{amount}
        Payment.AuthorizationCaptured(amount)
        Shift.DriverCancellationCompensation
      else:
        no fee
```

The fee is always a separate event — never a mutation of the trip's fare — so the audit trail is intact for disputes.

### 4.4 Driver shift & earnings rollup

`DriverWentOnline` opens a `shift-{driverId}-{date}` stream. Each `TripCompleted` fans out → `TripEarningRecorded`. `DriverWentOffline` (or end-of-day) closes the shift and triggers `EarningsFinalized`, which becomes the input to the payout saga. DoorDash's "Earn by Time" is structurally identical, just with a per-second active-time accumulator.

## 5. Hot-path vs cold-path

Not everything is event-sourced. The split looks roughly like this:

| Concern | Store | Why |
|---|---|---|
| Driver live GPS (1–4 Hz) | Redis / in-memory H3 grid (sharded by hex) | Volume; only "now" matters for matching. |
| Matching graph (driver × rider edges, weights) | In-memory at dispatch service | Recomputed every batch (Lyft batches every few seconds). |
| Surge multiplier per H3 cell | In-memory + time-series store, fed by Flink | Aggregation over a 1–5 minute rolling window. |
| Trip state & milestones | Event store (Schemaless / Spanner / Kafka log + projection) | Source of truth; audit; replay. |
| Fare events | Event store (Grab uses ES explicitly) | Audit trail, dispute support. |
| Payments | Event store + PSP idempotency keys | Money. |
| Raw GPS trace | Columnar warehouse (Hadoop/Parquet) | Disputes, ML, route reconstruction. Cold. |

**Integration**: the hot dispatch service consumes the **commands** (`RequestRide`) and reads the **projections** (driver location, vehicle availability), but writes its decisions back as **events** on the trip stream (`DriverMatched`, `OfferExpired`). The event stream is the system of record; the hot stores are caches that can be rebuilt from the stream.

Uber's Fulfillment Platform makes this explicit: the **Business Transaction Coordinator** writes across multiple statechart entities atomically (Spanner-backed), then the **Fireball** service consumes state-change events and decides what push notifications to send.

## 6. Real-world gotchas

- **Long-running trips.** Inter-city or airport trips can run 2+ hours. The aggregate must tolerate process restarts and snapshot. Snapshots every N events (e.g. every 50) are common.
- **Offline drivers mid-trip.** A driver tunnel/airplane-mode gap means the driver app buffers events locally and replays on reconnect. Events must carry both `occurredAt` (device time) and `recordedAt` (server time). Server is the tiebreaker on conflicts.
- **GPS drift.** Don't trigger `DriverArrivedAtPickup` solely from a geofence — debounce with a dwell timer or an explicit "I'm here" tap. Otherwise you emit/retract events.
- **Dual-app state divergence.** Rider sees "Driver arriving" while driver hasn't tapped "Start trip". Treat the canonical state as the server stream; the apps render projections with optimistic UI and reconcile.
- **Fare adjustments after the fact** (toll auto-applied, route audit, customer-service credit). Always emit a **`FareAdjusted`** compensating event. Never go back and mutate `TripCompleted.fare`. This is what makes Grab's event-sourced fare store work as the legal/audit source of truth.
- **Ratings.** Submitted minutes-to-days later, sometimes never. Modelled as a separate aggregate so a missing rating doesn't keep the trip stream "open". A projection joins ratings to trips for the UI.
- **Tips, tolls, surcharges.** Each is its own event type (`TipAdded`, `TollAssessed`, `AirportSurchargeApplied`) appended after `TripCompleted`. Payment captures may run in two phases — initial fare at trip end, tip captured up to 24h later.
- **Force-completed by ops.** When a driver is unreachable but evidence says the trip finished, an operator emits `TripForceCompleted{byOperatorId, reason}`. Useful for SLAs and post-mortems.
- **Idempotency at the edges.** Driver/rider apps retry; every command carries a client-generated `requestId` used as the dedup key when appending the resulting event.

## 7. Sources & case studies

- **Uber Fulfillment Platform** — [Rearchitecture](https://www.uber.com/blog/fulfillment-platform-rearchitecture/) and [Building Uber's Fulfillment Platform for Planet-Scale](https://www.uber.com/blog/building-ubers-fulfillment-platform/) — entity model (`Trip`, `Supply`, `Offer`, `Waypoint`), statecharts, Business Transaction Coordinator, Fireball push service.
- **InfoQ summary** — [Uber's Fulfillment Re-architecture](https://www.infoq.com/news/2021/08/uber-rearchitecture/).
- **Uber Schemaless (Trip Datastore)** — [Part 2 Architecture](https://www.uber.com/blog/schemaless-part-two-architecture/) and [Part 3: Datastore Triggers](https://www.uber.com/blog/schemaless-part-three-datastore-triggers/) — append-only cells, triggers as an event bus.
- **Uber H3 Hexagonal Spatial Index** — [H3 blog](https://www.uber.com/blog/h3/) — the geo-cell scheme used as both sharding key and pricing aggregation key.
- **Lyft Dispatch** — [Solving Dispatch in a Ridesharing Problem Space](https://eng.lyft.com/solving-dispatch-in-a-ridesharing-problem-space-821d9606c3ff) — bipartite matching, batching, hot-path side of the architecture.
- **Grab Fare Storage** — [Democratising Fare Storage at Scale Using Event Sourcing](https://engineering.grab.com/democratising-fare-storage-at-scale-using-event-sourcing).
- **Grab Supply/Demand** — [Understanding Supply & Demand in Ride-hailing](https://engineering.grab.com/understanding-supply-demand-ride-hailing-data).
- **DoorDash event system** — [InfoQ: Zero to a Hundred Billion](https://www.infoq.com/presentations/doordash-event-system/).
- **Eugene Khyst — postgresql-event-sourcing (ride-hailing reference)** — [GitHub](https://github.com/eugene-khyst/postgresql-event-sourcing) — runnable reference impl of an event-sourced ride-hailing domain in Spring Boot.
- **Akshay Ghalme — How Uber's Surge Pricing Actually Works** — [blog](https://akshayghalme.com/blogs/how-uber-surge-pricing-actually-works/).

## Key takeaway

The robust pattern across Uber, Lyft, Grab, and DoorDash: model **Trip** and **Driver/Supply** as event-sourced aggregates with explicit statecharts; keep **Offer/Dispatch** as a short-lived aggregate sitting next to a hot in-memory matcher; keep **Location** out of the event store and project milestones in; treat **Payment**, **Rating**, and **Shift/Earnings** as independent aggregates connected by sagas; and never mutate past events — fare adjustments, tips, refunds, and force-completions all arrive as compensating events appended to the same trip stream.
