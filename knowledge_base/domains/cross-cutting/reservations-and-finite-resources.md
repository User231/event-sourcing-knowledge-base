# Reservations & Finite-Resource Booking

Hotel rooms. Airline seats. Restaurant tables. Doctor appointments. Concert tickets. Conference rooms. Charging stations. Cinema seats. Rental cars. SKU units in a flash sale. Available balance on a card. Phone numbers in a number pool. Container-ship slots. Operating-room time. — They all run the same engine:

> **A finite resource (capacity, time-slot, identity, balance) gets held tentatively, then either confirmed or released by a deadline.** The hold is a first-class aggregate. The capacity is a *projection*, not an aggregate. Cancellation policy is graded by time. Overbooking is sometimes deliberate policy, not a bug. And when reality oversells the resource, *somebody gets walked*.

This doc unifies a pattern that appears in every domain in `specific/` and that almost every team re-derives independently. The deep dive on hotels lives in [`../specific/hotel-and-hospitality.md`](../specific/hotel-and-hospitality.md); on e-commerce inventory in [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md); on auth-holds-as-reservation-of-balance in [`../specific/banking-and-finance.md`](../specific/banking-and-finance.md). This is the cross-domain treatment.

## Where reservation semantics actually appear

| Domain | The resource | The hold | Confirmation | Failure mode |
|---|---|---|---|---|
| **Hotel** | Room of type X on date D | `RoomReserved` (incl. OTA-confirmed-on-arrival) | Check-in → `GuestStay` aggregate | Overbook → walk-the-guest |
| **Airline / rail** | Seat on flight F (and seat-map cell) | `SeatHeld` during booking flow → `TicketIssued` | Boarding | Overbook → bump-and-compensate |
| **Restaurant** | Table for N at time T | `TableReserved` (OpenTable, Resy) | Guest arrival | No-show fee; waitlist resequencing |
| **Doctor / clinic** | 30-min slot with provider P | `AppointmentBooked` | Patient arrives, visit completed | No-show fee; same-day rebook |
| **Car rental** | Vehicle category at branch B on dates D1..D2 | `RentalReserved` | Vehicle handover | Upgrade if oversold |
| **Sports / event tickets** | Specific seat in venue | `SeatLocked` (5–10 min cart hold) → `TicketIssued` | Scan at gate | Ticketmaster: lock-expiry on cart abandonment |
| **Cinema** | Seat in screening | Same as event tickets, shorter cart TTL | Ticket scanned | Walk-up sells empty seats post-curtain |
| **Conference rooms / co-working** | Room R from T1 to T2 | `RoomBooked` | Usage / no-show | Auto-release after grace period |
| **EV charging / parking** | Stall S from T1 for duration D | `StallReserved` (ChargePoint, Tesla Supercharger queue) | Plug in by deadline | Idle fee if past target SoC |
| **Cruise / tour** | Cabin/spot on itinerary I | `ReservationConfirmed{depositPaid}` | Embarkation | Cancellation tiers by days-to-sail |
| **Equipment / instrument time** | Telescope hour, lab device, recording studio | `SlotBooked` | Begin session | Reassign on no-show |
| **Service appointments** (Mindbody, GlossGenius, hairdresser) | Provider P slot on day D | `AppointmentBooked` | Service rendered | No-show fee; rebook |
| **E-commerce inventory** | SKU unit at warehouse W | `StockReserved{expiresAt}` (10–30 min TTL) | `StockAllocated{orderId}` after payment | `StockReleased{reason: expiry}` |
| **Banking — auth hold** | Available balance | `WithdrawalAuthorized{holdId, expiresAt}` | `WithdrawalPosted` on clearing | `WithdrawalReleased` on hold expiry |
| **Number pools** (DID phone numbers, IPv4, license keys, vanity URLs) | A unique identifier | `NumberReserved{ttl}` | `NumberAssigned` | `NumberReleasedBackToPool` |
| **Container / logistics slots** | Ship/truck/aircraft cargo capacity | `SlotBooked` | Cargo handed over | Bumped to next sailing |

The unifying shape: **`X-Reserved{expiresAt}` → (`X-Confirmed` | `X-Released{reason}`)**. The deadline is non-optional; the "soft" version of this pattern is what makes capacity feel available to many customers simultaneously without lying.

## The six recurring patterns

### 1. Hold-then-confirm with TTL (the universal skeleton)

```
ResourceReserved { reservationId, resourceRef, expiresAt, holderId, intent }
ResourceConfirmed { reservationId, confirmedAt }       -- "I'm taking it"
ResourceReleased  { reservationId, reason: expiry|cancel|payment_failed }
```

The hold reserves capacity *optimistically* against the projection (§2). The TTL is what lets a single resource be shown to many shoppers without overselling: at most one wins the confirm; the others auto-release. This is the same shape as banking's `WithdrawalAuthorized{expiresAt}` → `WithdrawalPosted` | `WithdrawalReleased`, and e-commerce's `StockReserved{expiresAt}` → `StockAllocated` | `StockReleased`.

**TTL ranges in production:**
- Cinema / event tickets: 5–10 min (cart timeout)
- E-commerce inventory: 10–30 min (checkout duration)
- Hotel OTA hold: minutes to hours
- Banking auth: 7–30 days (card-network rules)
- Conference room: until 15 min past start (auto-release)

**The TTL choice is a product decision**, not an engineering one — long TTL = better completion rate but more apparent unavailability; short TTL = better availability but worse conversion.

### 2. Capacity as projection, not aggregate

A common modelling mistake: trying to make "rooms-of-type-X-on-date-D" or "seats-on-flight-F" the aggregate. It's not. **It's a projection over the reservation stream.**

```
RoomReserved        (reservation-{id} stream)
   ↓
DailyRoomTypeAvailability (projection keyed by {roomType}_{date})
   ↓  emits when bucket flips negative
DailyOverbookingDetected
```

In Dudycz's hotel sample (`DailyRoomTypeAvailability` as a `MultiStreamProjection`), availability is rebuilt from `RoomReserved` events. Same pattern in retail's `availability-{sku}-{warehouseId}` ATP projection (Walmart, Salesforce OCI), in airline seat-maps, in event-ticketing inventory.

The reason: capacity needs to be **queried from many places** (search, recommendations, the reservation flow itself, revenue management dashboards), and **rebuilt on different bases** (per day, per channel, per fare class, per loyalty tier). An aggregate gets you one answer; a projection lets you have several.

**Hot-resource contention** (flash-sale SKU, concert on-sale, popular Saturday-night dinner slot) still bites because every reservation appends to a stream whose projection is the same hot row. The escapes are the standard ones: shard by sub-resource (`inventory-{sku}-{warehouseId}-{shard}`), pre-reserve via Redis DECR with periodic ES reconciliation, optimistic concurrency on the projection row (Salesforce OCI's approach).

### 3. Available-to-Promise (ATP) — the universal formula

Retail crystallised this; other domains use the same arithmetic without naming it:

```
ATP = on_hand + scheduled_supply − reserved − allocated − safety_stock
```

- **on_hand** — physical units / seats / slots present today
- **scheduled_supply** — restock, future inventory, additional sessions being scheduled
- **reserved** — soft holds (cart, in-flight checkout)
- **allocated** — hard commits (paid, ticketed, confirmed)
- **safety_stock** — deliberate buffer (overbooking inverse — reserved-back capacity)

Read the same triple in airline (capacity − sold − held + planned-equipment-changes), in hotels (rooms − confirmed − held + walk-in-buffer), in clinical scheduling (slots − booked − held + emergency-buffer). Per [Microsoft Dynamics ATP](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-visibility-available-to-promise) and [Shopify's ATP guide](https://www.shopify.com/blog/available-to-promise).

The three-balance view from banking — `pending`, `available`, `settled` — is the same formula with renamed slots: pending = held, available = ATP, settled = on_hand after clearing.

### 4. Overbooking as deliberate policy (not a bug)

Hotels overbook based on no-show predictions. Airlines overbook based on historical missed-flight rates. Restaurants over-reserve to fill cancellations. This is **revenue management**, not a failure mode, and it must be modelled as such.

Two failure modes follow:
- **Cosmetic overbook** — within tolerance (`AllowedOverbooking`). Most no-shows mean no actual problem at service time. Model: `DailyOverbookingDetected{count, withinTolerance: true}`.
- **Real overbook** — `OverbookedOverTheLimit`. Now somebody gets walked. Triggers a saga.

The hotel sample uses `AllowedOverbooking` capacity buckets and only flags `OverbookedOverTheLimit` as a real problem ([Mews — Hotel overbooking strategy](https://www.mews.com/en/blog/hotel-overbooking-strategy)). The same line exists in airline pricing software (the "spill model"), in OpenTable's restaurant tooling, and in scheduling software for clinics that aggressively double-book providers.

**Engineering consequence:** the reservation aggregate should *not* reject `RoomReserved` when projected availability < 0. Mark the bucket overbooked and let the revenue/operations saga handle it. Refusing the booking at the wire is a different policy choice and usually the wrong one.

### 5. Walk / bump / compensation

When the resource physically can't accommodate the confirmed reservation, somebody gets compensated. Always a first-class event with a structured payload:

| Domain | Event | What it captures |
|---|---|---|
| Hotel | `ReservationWalked{partnerProperty, compensationAmount}` + folio entry | Where they ended up, how much we paid |
| Airline | `PassengerBumped{flight, compensationVoucher, rebookedOn}` | Industry has fixed regs on amount (US: 4× one-way fare cap) |
| Restaurant | `ReservationApologized{compTokens}` | Free dessert, future credit |
| Event tickets | `SeatUpgradedCompedDueToOversell{originalSeat, newSeat}` | Often upgrade rather than refund |
| Car rental | `RentalUpgradedDueToShortage{originalCategory, upgradedTo}` | Standard "free upgrade" disguise |
| Healthcare | `AppointmentRescheduledByProvider{reason, replacementSlot}` | Sometimes triggers no-show waiver |

The rule of thumb from hospitality: **never walk loyalty elites or guaranteed bookings.** That's domain logic — encode it. The saga that *picks who to walk* is choice-of-loser logic (FIFO of placement, lowest tier, longest stay potential), often as opaque to customers as the airline overbook algorithm.

### 6. Cancellation policy graded by stage

Refund and penalty depend on how far through the resource's *commitment timeline* the cancellation arrives.

```
Free-cancel deadline ──── Partial-refund window ──── No-refund window ──── Resource consumed
       T-7 days                T-48h                    T-24h                  Day-of
```

| Domain | Stage anchor | Policy gradient |
|---|---|---|
| Hotel | `Reservation.From` | Free until 48h before; one-night charge after; full charge no-show |
| Airline | Flight `departureTime` | Refundable fare vs. credit-only; change fee until T-24h |
| Restaurant | `reservation.time` | Free until 24h; deposit forfeit after; no-show fee |
| Event tickets | Event start | Mostly non-refundable; resale market is the secondary cancel mechanism |
| Doctor | Appointment time | Free until 24h; no-show fee after |
| Food delivery | Order `acceptedAt`, then `preparedAt` | Pre-accept free; post-accept partial; post-prep no refund (see [`../specific/food-ordering-and-delivery.md`](../specific/food-ordering-and-delivery.md)) |

Modelling: every cancellation event carries the stage it occurred in and the resulting policy outcome. **Don't compute refund-or-not at query time** — it should be a fact recorded with the cancellation, because the policy may change tomorrow.

```
ReservationCancelled {
  reservationId,
  cancelledAt,
  cancelledBy: customer|provider|system,
  stage: pre_window|partial_window|no_refund_window,
  refundAmount,
  penaltyAmount,
  policyVersion
}
```

## Multi-resource group bookings — fan-out reservation

The "group checkout" in hotels is the canonical fan-out reservation saga: N guests, each with their own reservation/stay, completing as one operation. The same shape appears in:
- **Airline group bookings** (sports team, conference attendees) — group PNR with N tickets.
- **Restaurant private events** — multiple tables in one room.
- **Event-ticket group buys** (Ticketmaster fan club allocations).
- **Conference travel** (hotel block + flight bookings + ground transport).
- **University class registration** (course + lab + recitation as a package).

The pattern: a `GroupBooking` aggregate that initiates N child reservations, collects their outcomes, and finalises only when all terminate (success, partial, or with documented failures). This is the canonical fan-out / scatter-gather saga from [`sagas-and-multi-step-workflows.md`](sagas-and-multi-step-workflows.md).

## Soft hold vs hard allocation — the two-tier reservation

Many production systems have **two** layers of reservation:

1. **Soft hold** — in a fast in-memory store (Redis, Memcached, an in-process map). DECR on a counter, set a TTL. Fast (<1ms), tolerant of crash-loss because the TTL bounds the bleed.
2. **Hard allocation** — appended to the event store as `StockReserved` / `ResourceConfirmed`. Authoritative; durable; the audit trail.

Soft holds absorb the burst (Ticketmaster's "Smart Queue"; Salesforce OCI's Redis DECR + periodic reconciliation against the event log). Periodic reconciliation projects the durable allocations back into the in-memory counter, fixing drift caused by lost holds, double-consumption, or crashes.

**Choose the split by latency budget.** If P99 reservation latency must be <50 ms (event-ticket onsales, flash-sale checkout), you have to put the hot path in memory. If you have 200 ms to spare (most hotel/restaurant bookings), the event store can be the only thing.

## Five failure modes reservation systems re-derive the hard way

1. **The fraud hold problem.** Stock is reserved, payment is pending fraud review, the TTL expires, stock auto-releases, payment then clears — and you've oversold (and the customer thinks they bought it). Fix: fraud hold is a **pause state**, not a compensation; it must extend or freeze the reservation TTL.
2. **The double-clicked checkout.** Two `Reserve` commands for the same cart with the same idempotency key arrive at near-identical times against different replicas. One wins; the other must dedupe to no-op (not retry against fresh state and double-reserve).
3. **The deleted resource problem.** A hotel takes a room out of service for maintenance; reservations against that room exist; you must reassign or walk them. The room aggregate's lifecycle events must drive a reservation-level audit/reaccommodation saga — not silently disappear from search.
4. **The reschedule-as-edit anti-pattern.** Editing `ReservationConfirmed{from, to}` to change dates is wrong — you've destroyed the audit trail of "what was the original commitment?" Instead: `ReservationRescheduled{fromOld, toOld, fromNew, toNew, reason}` as a new event.
5. **The overbooking projection lag.** Projection updates lag the event store by milliseconds; two concurrent reservations both see ATP=1 and both reserve, oversold by exactly one. Either (a) accept oversold-by-one as within tolerance and let the overbooking saga handle it (the hotel/airline approach), or (b) put the contention check on the projection itself with optimistic concurrency (Salesforce's approach).

## Patterns that survive contact with production

- **Reservation ≠ Stay / Cart ≠ Order / Auth ≠ Posted.** The "request" and the "thing requested" are always different aggregates. Conflating them is the #1 modelling mistake in this archetype — see the corresponding [README §"Patterns that recur"](../README.md) item.
- **Capacity is a projection, not an aggregate.** Multiple projections off the same reservation stream are normal (per-day, per-channel, per-class).
- **Hold has a TTL, always.** No infinite holds. The TTL is the product knob.
- **Overbooking is policy, not error.** Distinguish `OverbookedWithinTolerance` from `OverbookedOverTheLimit`. Refusing a reservation when projected ATP < 0 is one choice; admitting it and managing is another, usually better one.
- **Cancellation policy graded by stage, captured at the moment.** Don't recompute the refund later; record the policy version.
- **Compensation events for the walked party are first-class.** `ReservationWalked{compensation}`, `PassengerBumped{voucher}`. They go in the audit trail.
- **Soft hold in memory + hard allocation in ES + periodic reconciliation.** When latency matters. Don't go full ES for hot-resource flash sales; don't go full Redis for the durable booking record.
- **Idempotency on every reservation command.** Re-clicked "Book" buttons, retried API calls, redelivered webhooks. Banking, ride-share, and ecommerce all confirm: this is non-optional.

## Where to look in the cloned repos

- **`oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/`** — the canonical reservation-as-aggregate-with-projection-availability codebase. Reservation, GuestStayAccount, DailyRoomTypeAvailability projection, DailyOverbookingDetector reactive projection, three saga variants of GroupCheckout. The richest single sample in this directory.
- **`oskardudycz_EventSourcing.NetCore/Sample/ECommerce/`** — Reservation aggregate with TTL for stock holds; integrates with Payment for the confirm-or-release decision.
- **`AxonFramework_AxonFramework/examples/university-java/`** — course bookings with capacity invariants. Reservation-like flow in an academic-scheduling context.
- **`eventuous_eventuous/samples/postgres/Bookings/`** — multi-service booking + payment.

## Related docs

- [`../specific/hotel-and-hospitality.md`](../specific/hotel-and-hospitality.md) — the canonical reservation domain: Reservation ≠ Stay split, overbooking projections, OTA channel-manager outbox, walk-the-guest, GroupCheckout in three implementations.
- [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) — Reservation (cart-stage) and Allocation (post-payment) — same hold-then-confirm pattern with the ATP formula in the open.
- [`../specific/banking-and-finance.md`](../specific/banking-and-finance.md) — the `WithdrawalAuthorized` / `WithdrawalPosted` / `WithdrawalReleased` triple is the auth-hold form of the same pattern; pending/available/settled balances mirror reserved/ATP/on-hand.
- [`../specific/food-ordering-and-delivery.md`](../specific/food-ordering-and-delivery.md) — graded cancellation policy by stage; 86'ing (`MenuItemAvailability`) is a real-time capacity stream of its own.
- [`sagas-and-multi-step-workflows.md`](sagas-and-multi-step-workflows.md) — the fan-out / scatter-gather saga family that powers group bookings.
- [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md) — the "three balances" pattern (pending, available, settled) cross-references inventory's reserved/allocated/on-hand.
- [Walmart — Design Inventory Availability with Event Sourcing](https://medium.com/walmartglobaltech/design-inventory-availability-system-using-event-sourcing-1d0f022e399f).
- [Salesforce Engineering — Event Sourcing for Inventory Availability (OCI)](https://engineering.salesforce.com/event-sourcing-for-an-inventory-availability-solution-3cc0daf5a742/).
- [Oskar Dudycz — HotelManagement sample](https://github.com/oskardudycz/EventSourcing.NetCore/tree/main/Sample/HotelManagement).
- [Mews — Hotel overbooking strategy](https://www.mews.com/en/blog/hotel-overbooking-strategy).
