# Hotel & Hospitality — Aggregate & Stream Decomposition

The hotel domain is the canonical reference for event-sourcing teaching because it stretches every modelling muscle: long-lived reservations vs short-lived stays, multi-aggregate sagas (the group checkout), reactive overbooking projections, and OTA channel-manager integration. Grounded primarily in Oskar Dudycz's `EventSourcing.NetCore/Sample/HotelManagement` (the de facto .NET reference), with industry context from Booking.com, Mews, and traditional PMSs.

## 1. Aggregate boundaries used in practice

Hotel domain experts (Khononov, Luontola, Dudycz) converge on the same decomposition. The critical insight: **"reservation" and "stay" are two different aggregates with different lifecycles** — confusing them is the canonical hospitality modelling mistake.

| Aggregate | Lifecycle | Consistency boundary | Why a separate aggregate |
|---|---|---|---|
| **Reservation** / `RoomReservation` | From `ReservationRequested` to `Confirmed` / `Cancelled` / `NoShow`. Lives mostly *before* the guest arrives. | Single booking record: who, what room type, which dates, which channel. | Lifecycle dominated by distribution and policy (cancellation windows, payment guarantee, channel-of-origin). Nothing to do with in-house operations. |
| **GuestStay** / **GuestStayAccount** | From `GuestCheckedIn` to `GuestCheckedOut`. Lives *during* the stay. | A ledger: charges in, payments in, balance, status. | Different invariants ("balance must be zero before checkout"), different actors (front desk, F&B, housekeeping), different command frequency. |
| **Room** (physical unit) | Permanent, per property. | Room number, type, attributes, current state (clean/dirty/OOO). | Physical inventory, attribute changes, maintenance/housekeeping status. |
| **Inventory / Allotment** (per `roomType` per `date`) | Per-day capacity bucket. | "How many rooms of type X on date D". Usually **projection-only** in event-sourced systems — derived from reservation events. | Cross-cuts many reservations; not a transactional consistency boundary. |
| **RatePlan** | Per property, long-lived. | Pricing rules, restrictions (min-LOS, CTA, CTD). | Independent change cadence (revenue manager updates). |
| **Guest** / `Guest` profile | Permanent, cross-property. | Identity, contact, preferences, loyalty. | GDPR/erasure boundary; cross-stay identity. |
| **GroupCheckout** | Short-lived saga state. | Tracks fan-out of N per-guest checkouts. | Distributed-process consistency: completion only when all child checkouts terminate. |
| **Folio / Invoice** | Snapshot/closing artefact. | Closed financial document, immutable after issue. | Tax/regulatory immutability — different from the open `GuestStayAccount` ledger. |
| **Housekeeping / RoomStatus** | Per-room per-day. | Dirty / clean / inspected / out-of-order. | Owned by a different team with own command stream; loosely coupled to stays. |
| **Property / Channel** | Configuration. | Connection state, mapping, distribution rules. | Bounded context boundary (distribution) vs. core PMS. |

### Why Reservation ≠ GuestStay (the load-bearing distinction)

In Oskar's sample (`HotelManagement/Reservations/RoomReservations/RoomReservation.cs`) the **Reservation** emits `RoomReserved`, `RoomReservationConfirmed`, `RoomReservationCancelled`. It is **never the same object** as the in-house ledger.

The **GuestStayAccount** (`HotelManagement/Sagas/GuestStayAccounts/GuestStayAccount.cs`) emits `GuestCheckedIn`, `ChargeRecorded`, `PaymentRecorded`, `GuestCheckedOut`, `GuestCheckoutFailed`. Note these are *different events*: charges only exist in-house, never on the reservation; cancellation only exists on the reservation, never on the stay.

This split mirrors how real PMSs (Mews, Opera, Cloudbeds) work: the booking is "in the books"; the stay is "on property". A guest can be in-house with no active reservation (walk-in), or have a reservation with no stay yet (booked tomorrow), or have an early-departure stay that ended before the reservation's `To` date.

## 2. Stream-id naming patterns

From the actual code in the sample:

```
reservation-{reservationId}                    # one stream per booking (UUIDv7)
gueststay-{guestStayId}                        # one stream per check-in instance (NOT per guest)
groupcheckout-{groupCheckoutId}                # one stream per group-checkout saga run
guest-{guestId}                                # long-lived guest profile
room-{propertyId}-{roomNumber}                 # physical room (housekeeping/maintenance)
ratePlan-{propertyId}-{ratePlanId}             # pricing
```

Notably **absent**:

```
# DO NOT do this:
availability-{propertyId}-{roomType}-{date}    # availability is a PROJECTION, not a stream
```

In the sample, `DailyRoomTypeAvailability` is a `MultiStreamProjection` keyed by `{RoomType}_{Date}`. It's rebuilt from `RoomReserved` events. Overbooking detection is also a reactive projection (`DailyOverbookingDetector` emits `DailyOverbookingDetected` whenever a daily bucket flips negative).

External IDs are explicit: `RoomReserved` carries `ExternalReservationId` (the Booking.com reference), and `GuestExternalId` uses prefixed namespacing like `BCOM/{externalGuestId}` for idempotent dedupe.

## 3. Key events per aggregate

### Reservation (`Reservations.RoomReservations`)
- `RoomReserved(ReservationId, ExternalReservationId, RoomType, From, To, GuestId, NumberOfPeople, Source, MadeAt)`
- `RoomReservationConfirmed(ReservationId, ConfirmedAt)` — internal-API bookings start `Pending` and confirm later; external (OTA) bookings are confirmed-on-arrival
- `RoomReservationCancelled(ReservationId, CancelledAt)`

Extensions a real PMS adds (not in the toy sample but standard in industry):
- `ReservationModified` (dates / room type / occupancy changed)
- `NoShowRecorded` — after the check-in window closes
- `ReservationChannelChanged` — rare but happens with corporate-rate overrides
- `ReservationGuaranteed` / `DepositCaptured`
- `ReservationWalked` — relocated to partner property

### GuestStayAccount (`HotelManagement.Sagas.GuestStayAccounts`)
- `GuestCheckedIn(GuestStayId, CheckedInAt)`
- `ChargeRecorded(GuestStayId, Amount, RecordedAt)`
- `PaymentRecorded(GuestStayId, Amount, RecordedAt)`
- `GuestCheckedOut(GuestStayId, CheckedOutAt, GroupCheckOutId?)`
- `GuestCheckoutFailed(GuestStayId, Reason {NotOpened|BalanceNotSettled}, FailedAt, GroupCheckOutId?)`

Production extensions:
- `RoomChanged` (mid-stay room move)
- `LateCheckoutGranted`
- `EarlyDepartureRecorded`
- `FolioSplit` / `FolioTransferred` (move charges between folios)

### GroupCheckout (`HotelManagement.Sagas.GroupCheckouts`)
- `GroupCheckoutInitiated(GroupCheckoutId, ClerkId, GuestStayIds[], InitiatedAt)`
- `GuestCheckoutsInitiated(GroupCheckoutId, InitiatedGuestStayIds[], InitiatedAt)`
- `GuestCheckoutCompleted(GroupCheckoutId, GuestStayId, CompletedAt)`
- `GuestCheckoutFailed(GroupCheckoutId, GuestStayId, FailedAt)`
- `GroupCheckoutCompleted(GroupCheckoutId, CompletedCheckouts[], CompletedAt)`
- `GroupCheckoutFailed(GroupCheckoutId, CompletedCheckouts[], FailedCheckouts[], FailedAt)`

### Inventory (projection, not stream)
- `DailyOverbookingDetected(RoomType, Date, OverBookedCount, OverBookedOverTheLimitCount)` — emitted by the projection's `IChangeListener` when a bucket goes negative.

## 4. Cross-aggregate processes / sagas

### 4a. The end-to-end happy path
```
ReservationRequested -> ReservationConfirmed
       (time passes)
GuestCheckedIn -> ChargeRecorded* + PaymentRecorded* -> GuestCheckedOut
       (eventually)
FolioClosed / InvoiceIssued
```
Note the **two different aggregates** (`reservation-{id}` then `gueststay-{id}`) — the linkage is by data (`ReservationId` on the `GuestCheckedIn` payload in production systems) not by being the same stream.

### 4b. The canonical Group Checkout saga

This is *the* hospitality example for teaching event-driven distributed processes ([Oskar — Event-driven distributed processes by example](https://event-driven.io/en/event_driven_distributed_processes_by_example/)). The sample ships **three implementations of the same business process** — saga, choreography, process manager — under:
- `HotelManagement/Sagas/GroupCheckouts/GroupCheckoutSaga.cs`
- `HotelManagement/Choreography/GroupCheckouts/GroupCheckout.cs`
- `HotelManagement/ProcessManagers/GroupCheckouts/GroupCheckoutProcessManager.cs`

Flow (saga variant, from the actual code):
1. Front desk fires `InitiateGroupCheckout(groupCheckoutId, clerkId, guestStayIds[])`.
2. `GroupCheckout` aggregate emits `GroupCheckoutInitiated`.
3. `GroupCheckoutSaga` listens for `GroupCheckoutInitiated` and schedules one `CheckOutGuest(guestStayId, groupCheckoutId)` command per guest, then `RecordGuestCheckoutsInitiation`.
4. Each `GuestStayAccount` independently produces `GuestCheckedOut(..., groupCheckOutId)` or `GuestCheckoutFailed(..., reason, groupCheckOutId)`.
5. The saga routes those back as `RecordGuestCheckoutCompletion` / `RecordGuestCheckoutFailure` commands on the `GroupCheckout`.
6. When the last child terminates, the aggregate self-finalises with `GroupCheckoutCompleted` or `GroupCheckoutFailed` (depending on whether any child failed).

The pattern Oskar emphasises: **business logic stays in the `GroupCheckout` aggregate; the saga is dumb — pure routing**. Compare to the `GroupCheckoutProcessManager` variant which collapses both into one class and is explicitly tagged "event-driven but not event-sourced".

See also [../implementation-patterns/multi-aggregate-commands-and-sagas.md](../implementation-patterns/multi-aggregate-commands-and-sagas.md) for the underlying pattern.

### 4c. Other industry sagas
- **Overbooking handling.** Reactive projection (`DailyOverbookingDetector`) raises `DailyOverbookingDetected`. A revenue/operations saga then either upsells, contacts guests for voluntary re-accommodation, or triggers `WalkGuestToPartnerHotel`. Production hotels intentionally overbook based on no-show predictions ([Mews — Hotel overbooking strategy](https://www.mews.com/en/blog/hotel-overbooking-strategy)).
- **Room assignment.** Reservation only books a *room type*; physical room assignment happens close to arrival via a separate `AssignRoom` command → `RoomAssigned` event on the stay.
- **Cancellation policy windows.** Free / first-night charge / 100% — modelled as a policy attached to the rate plan, evaluated when `RequestCancellation` is handled. The resulting `RoomReservationCancelled` and a `CancellationFeeCharged` are separate events.
- **Channel-manager outbox.** Every `RoomReserved` / `RoomReservationCancelled` is fanned out to OTAs by an integration saga.

## 5. Channel manager / OTA integration

External bookings enter via a translator. Concrete example from the sample (`Reservations/RoomReservations/ReservingRoom/BookingComRoomReservationMadeHandler.cs`):

- External event: `BookingComRoomReservationMade(ReservationId, RoomType, Start, End, GuestProfileId, GuestsCounts, MadeAt)`.
- Handler resolves the Booking.com `GuestProfileId` to an internal `GuestId` via `GetGuestIdByExternalId(FromPrefix("BCOM", bookingComGuestId))`.
- Issues `ReserveRoom.FromExternal(...)` which yields the same internal `RoomReserved` event but with `Source = External` and `ExternalReservationId` set. **External bookings auto-confirm** (`Status = Confirmed`, `ConfirmedAt = MadeAt`) — you can't tell Booking.com "we're holding it tentatively".

**Idempotency**: the prefixed external ID (`"BCOM/{externalGuestId}"`) plus the OTA's reservation reference is the dedupe key. If the same OTA event is re-delivered, the handler must be a no-op. In Kafka-based pipelines, the consumer group offset plus an inbox table (or a unique-constraint on external reservation id in the read model) provides this. See [Real-Time OTA Sync & Retry System](https://medium.com/@samaya.muduli/real-time-ota-sync-retry-system-for-a-hotel-channel-manager-ba33cc7f0495).

Channel manager outbound: ARI (Availability / Rate / Inventory) push is a projection consumer that converts `RoomReserved`, `RoomReservationCancelled`, and rate-change events to per-channel XML/JSON pushes ([SiteMinder channel manager overview](https://www.siteminder.com/r/ota-channel-manager/)).

## 6. Real-world gotchas

1. **"Nights" not "days".** A 1-night stay has `From = 2026-05-22`, `To = 2026-05-23` but is **one** chargeable night. Iterate `From.DayNumber .. To.DayNumber - 1` to enumerate nights. The sample's `DailyRoomTypeAvailabilityProjection` uses `Enumerable.Range(0, e.To.DayNumber - e.From.DayNumber)` — note the exclusive upper bound.
2. **Check-in / check-out windows ≠ midnight.** Standard 15:00 / 11:00 in property-local time. A "stay date" is the *arrival night*. Night audit is the daily roll at ~03:00 local; events use `DateTimeOffset` (UTC + zone) but the *business date* needs the property's IANA zone — never the server's.
3. **Overbooking is deliberate, not a bug.** Don't reject reservations when availability < 0; mark the bucket overbooked and let the revenue saga handle it. The sample uses `AllowedOverbooking` capacity and only flags `OverbookedOverTheLimit` as a real problem.
4. **Length-of-stay / CTA / CTD restrictions** belong to the rate plan, not the reservation. They are read at booking time but should be captured as data on `RoomReserved` so policy changes don't retroactively invalidate the booking.
5. **Mid-stay rate changes.** Corporate-rate overrides applied at check-in (or even mid-stay) → emit `RateOverridden` on the stay, not on the reservation. The folio recomputes from rate events, not a snapshot.
6. **Group bookings: shared folio vs individual.** Group reservation = parent reservation + N child stays. The conference master account is its own `Folio` aggregate that accepts `ChargeTransferred` events from individual stays. GroupCheckout aggregates this on departure.
7. **Cancellation after check-in = early departure**, *not* cancellation. The reservation is consumed; an `EarlyDepartureRecorded` event on the stay triggers a (configurable) early-departure fee.
8. **Property time zones.** Multi-property chains *must* store the property's IANA zone with every event payload (or derive at projection time). A single Marriott portfolio spans every timezone.
9. **Walk-the-guest.** When all rooms of a type are sold and a confirmed guest arrives, the property has an obligation to relocate them to a comparable partner hotel — model as `ReservationWalked(partnerProperty, compensationAmount)` plus a folio entry for the compensation. Ops choose *whom* to walk by rules: never walk loyalty elites or guaranteed bookings.

## 7. Sources & case studies

- **Oskar Dudycz — EventSourcing.NetCore HotelManagement sample**: [GitHub](https://github.com/oskardudycz/EventSourcing.NetCore/tree/main/Sample/HotelManagement) — canonical event-sourced hotel reference, three variants (saga / choreography / process manager) of GroupCheckout.
- **event-driven.io — Event-driven distributed processes by example**: https://event-driven.io/en/event_driven_distributed_processes_by_example/ — the article explaining the GroupCheckout saga.
- **event-driven.io — Should you record multiple events from business logic?**: https://event-driven.io/en/one_or_more_event_that_is_the_question/ — uses `GuestCheckedIn` examples.
- **luontola/cqrs-hotel** (Esko Luontola): https://github.com/luontola/cqrs-hotel — no-frameworks CQRS+ES hotel reservation app; good aggregate-root reference.
- **robertreppel/eventsourcing-hotelreservations**: https://github.com/robertreppel/eventsourcing-hotelreservations — C# CQRS+ES hotel reservations demo.
- **jet/dotnet-templates — propulsion-hotel**: https://github.com/jet/dotnet-templates/blob/master/propulsion-hotel/README.md — Equinox/Propulsion hotel template (F#, .NET).
- **Mews — Hospitality management software**: https://www.mews.com/en
- **Mews — What is a hotel folio?**: https://www.mews.com/en/blog/hotel-folio — production PMS perspective on real entities (folio, ledger, night audit).
- **Mews — Hotel overbooking strategy**: https://www.mews.com/en/blog/hotel-overbooking-strategy.
- **Booking.com Tech Blog**: https://blog.booking.com/
- **Booking.com + Honeycomb (observability)**: https://www.honeycomb.io/blog/booking-com-journey-enhanced-observability
- **Booking.com + Confluent / Kafka**: https://www.confluent.io/customers/booking-com/
- **TUI MM Engineering — Architecture Patterns For Booking Management Platform**: https://medium.com/tuimm/architecture-patterns-for-booking-management-platform-53499c1e815e
- **Solving Double Booking at Scale**: https://itnext.io/solving-double-booking-at-scale-system-design-patterns-from-top-tech-companies-4c5a3311d8ea
- **Real-Time OTA Sync & Retry System for a Hotel Channel Manager**: https://medium.com/@samaya.muduli/real-time-ota-sync-retry-system-for-a-hotel-channel-manager-ba33cc7f0495
- **SiteMinder — OTA channel manager**: https://www.siteminder.com/r/ota-channel-manager/

## Local code references (rich, worth reading)

- **C# (richest)**: `repos_cloned/oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/` — three variants of the GroupCheckout process side by side.
- **Java**: `repos_cloned/oskardudycz_EventSourcing.JVM/samples/distributed-processes/src/main/java/io/eventdriven/distributedprocesses/hotelmanagement/` — same domain, JVM.
- **Bookings + Payments (multi-service)**: `repos_cloned/eventuous_eventuous/samples/postgres/Bookings/` — Bookings.Domain has value objects (`Money`, `StayPeriod`, `RoomId`) worth lifting.
