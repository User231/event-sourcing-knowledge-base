# Marketplaces & Matching Engines

A marketplace looks superficially like an e-commerce app — but the moment you have *independent supply* (drivers, couriers, hosts, freelancers, sellers, advertisers) on one side and *independent demand* on the other, with the platform brokering the match and taking a cut, you've entered a category with its own ES vocabulary: **Demand aggregate**, **Supply aggregate**, **Match aggregate** (also called *Offer*, *Booking*, *Trip*, *Job*, *Dispatch*, *Auction*, *Trade*), **payout split**, **two-sided reputation**, **surge as derived projection**.

This doc collects the patterns that recur across every two-sided platform in `specific/` — ride-sharing, food delivery, ad exchanges, freelance, lodging, dating, financial exchanges — and the failure modes that bite each one.

## The platforms this applies to

| Marketplace | Demand | Supply | Match aggregate | Match latency budget |
|---|---|---|---|---|
| **Ride-sharing** (Uber, Lyft, Grab, Bolt) | Rider request | Driver online + nearby | Trip + Offer/Dispatch | 100ms–10s |
| **Food / grocery delivery** (DoorDash, UberEats, Wolt, Instacart, Deliveroo) | Order placed | Courier online | Delivery + Dispatch | seconds–minutes |
| **Lodging** (Airbnb, VRBO, Booking.com) | Search + book | Listing + calendar | Reservation | seconds (search), instant book or hours (host-approval) |
| **Freelance** (Upwork, Fiverr, Toptal, 99designs) | Job post / brief | Freelancer profile + bid | Contract / Project | hours–days |
| **Service tasks** (TaskRabbit, Thumbtack, Handy, Mindbody) | Service request | Tasker / pro availability | Booking | minutes–hours |
| **E-commerce marketplaces** (eBay, Etsy, Amazon Marketplace, Mercado Libre) | Buy intent / bid | Listing + inventory | Order (auction: WinningBid) | seconds (BIN), 1d–10d (auctions) |
| **Ad exchanges** (Google AdX, OpenRTB, AppNexus, TheTradeDesk) | Impression / opportunity | Advertiser bid | WinningBid → Impression | 50–120 ms (real-time bidding) |
| **Dating apps** (Tinder, Bumble, Hinge) | Swipe / like | Profile | Match (mutual like) | minutes–days |
| **Financial exchanges** (NYSE, Nasdaq, Coinbase, Binance) | Buy order | Sell order (orderbook) | Trade | microseconds |
| **Lending marketplaces** (LendingClub, Funding Circle, Kiva) | Loan request | Investor commitment | LoanFunded | hours–days |
| **Carpooling** (BlaBlaCar, Waze Carpool) | Passenger request | Driver route + seats | Booking | hours–days |
| **B2B marketplaces** (Flexport, Convoy, Faire, Alibaba) | Buyer RFQ / spot rate | Carrier / supplier capacity | Booking / PO | minutes–hours |

Three observations from the table:
1. **Match latency varies by 9 orders of magnitude** — from microseconds (HFT) to days (lending). The match-aggregate design follows from this.
2. **Every row has at least three distinct aggregates: Demand, Supply, Match.** Conflating any pair is the #1 marketplace modelling mistake.
3. **"Independent supply" is the load-bearing word.** If you (the platform) own the supply (Amazon's first-party fulfillment), you're a retailer running e-commerce. If supply is independent agents you don't employ, you're a marketplace and need this doc.

## The three (or more) anchor aggregates

### Demand aggregate

The customer-side request. Carries intent, constraints, willingness-to-pay, and crucially **a snapshot of any matching-relevant parameters at request time** (surge multiplier, currency, region, deadline) so later fare/price adjustments are auditable rather than mysterious.

| Marketplace | Demand aggregate | Key fields |
|---|---|---|
| Ride-sharing | `Trip` / `TripRequest` | `pickup/dropoff`, `productType`, `surgeMultiplier@request`, `upfrontFare` |
| Food delivery | `Order` | Cart, address, scheduled-for, tip |
| Lodging | `Reservation` | `propertyId`, dates, guests, totalPrice |
| Freelance | `JobPost` / `Brief` | Skills required, budget, deadline |
| Ad exchange | `BidRequest` / `Impression` | Floor price, targeting, viewability |
| Dating | `Like` / `Swipe` | Target profile id, opt-in for super-like |
| Exchange | `Order` (buy) | Symbol, qty, limit/market, TIF |

### Supply aggregate

The provider-side identity + availability. Long-lived (years across many trips/orders/bookings), independent lifecycle from any single transaction. The same hot-vs-cold split as elsewhere: long-lived identity in ES, hot operational state (online flag, current location, queue depth) in Redis/memory.

| Marketplace | Supply aggregate | Hot state (off-ES) |
|---|---|---|
| Ride-sharing | `Driver`, `Vehicle` | Current location, online flag |
| Food delivery | `Courier`, `Restaurant` (with `MenuItemAvailability`) | Location, accepting-orders flag, 86'd items |
| Lodging | `Listing` | Calendar availability, instant-book flag |
| Freelance | `Freelancer` profile | Logged-in flag, current capacity |
| Ad exchange | `AdvertiserCampaign`, `Creative` | Budget remaining today, pacing |
| Dating | `Profile` | Last-active time, current location |
| Exchange | (limit orders on the book) | Real-time orderbook |

### Match aggregate

The convergence event. Where Demand meets Supply. This is the consequential aggregate — once a `MatchOccurred` is written, money will move and reputation will accumulate.

| Marketplace | Match aggregate | What it records |
|---|---|---|
| Ride-sharing | `Trip` post-`DriverMatched` (same aggregate, state-transition) or separate `Dispatch` | driver, ETA, accepted-at |
| Food delivery | `Dispatch` + `Delivery` | courier assignment, route, batched-with |
| Lodging | `Reservation` post-`HostAccepted` | host approval, deposit, check-in details |
| Freelance | `Contract` | terms, milestones, escrow |
| Ad exchange | `WinningBid` → `Impression` | clearing price, second-price details |
| Dating | `Match` | mutual-like, opened-chat |
| Exchange | `Trade` | trade price, time, both order ids |

**The match is structurally a balanced ledger entry** — a transaction touching at least three accounts (demand-pays, supply-receives, platform-takes). See [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md) for the multi-party settlement treatment.

## The match: compare-and-swap on a scarce resource

The defining technical challenge of marketplace matching: the same supply unit (driver, courier, seat, slot, share, ad impression) can be claimed by exactly one piece of demand, but multiple pieces of demand are *trying simultaneously*. **The match is a compare-and-swap.**

```
Hot in-memory matcher (geo-index / orderbook / candidate set)
        |
        | proposes: dispatch driver-D to trip-T
        v
Atomic Compare-and-Swap on Supply or Match aggregate
        |
        +--- success: append MatchOccurred to ES; supply marked occupied
        |
        +--- conflict: another trip won; matcher retries with fresh state
```

How each domain implements this:

| Marketplace | The CAS substrate | Latency tolerance |
|---|---|---|
| **Uber Fulfillment** | Statechart on `Trip` + `Supply`, "Business Transaction Coordinators" over Spanner | 100ms–s |
| **Lyft Dispatch** | Bipartite ILP recomputed every 1–5s; result is the proposed match, written via optimistic-locking on `Trip` | 1–5s |
| **DoorDash DeepRed** | Two-tier: real-time ML scoring + Cadence workflow committing the decision | seconds |
| **Stock exchanges (LMAX Disruptor)** | Single-threaded matching engine; the *thread* IS the serialiser; trades are events emitted post-match | microseconds |
| **Ad exchange (RTB)** | Auction held in-memory at the exchange; winning bid persisted as event | <120ms (Google AdX timeout) |
| **Airbnb instant-book** | Optimistic concurrency on calendar; conflict = "those dates just got booked" | seconds |
| **Etsy / eBay BIN** | Optimistic lock on listing.qty | seconds |
| **Tinder** | Asymmetric — left-swipe doesn't lock anything; mutual-like is a join projection that emits `Match` | minutes |

The CAS pattern is the same as the [reservation pattern](reservations-and-finite-resources.md) — except the "resource" is the supply unit, not capacity. **Stock exchanges and ride-sharing are structurally the same problem at very different latency budgets.**

### Hot-path matcher OFF the event store; only milestones ON

Driver GPS pings, orderbook diffs, advertiser-budget pacing, courier proximity — these arrive at 1–100 Hz × millions of agents. **The event store cannot absorb that volume and isn't the right home for it.** Hot state lives in geo-indexes (Redis with H3 hex sharding for Uber/Lyft, similar for delivery platforms), in-memory orderbooks (LMAX-style), or streaming engines (Flink). Only milestone events — `DriverWentOnline`, `DriverMatched`, `TripStarted`, `TripCompleted`, `OrderbookSnapshot @ T`, `Trade` — go on the event store.

Cross-link: this is archetype C in [`unbounded-and-infinite-streams.md`](unbounded-and-infinite-streams.md#c-high-frequency-telemetry--volume-not-lifetime-is-the-killer) and the same hot-path / cold-path pattern that every transactional platform with physical-world telemetry uses.

## The Offer pattern — short-lived auction-shaped aggregate

When the match isn't immediate (multi-driver broadcast, multi-bidder ad auction, multi-courier dispatch), production systems insert an explicit short-lived `Offer` aggregate between Demand and Supply:

```
TripRequested  -> create N OfferCreated, each TTL=15s
                  +-> OfferDelivered (push to driver)
                  +-> OfferAccepted | OfferDeclined | OfferExpired
                  +-> If accepted first: trip moves to DriverMatched
                       else other offers auto-expire
```

Same shape in ad exchanges (`BidRequest` broadcast → N `Bid`s → `AuctionWon`), in freelance platforms (`JobPosted` → N `ProposalSubmitted` → `ProposalAccepted`), in B2B freight (RFQ → quotes → award).

**The Offer is a first-class aggregate** because the audit trail of "who got asked, who responded, what TTL ran out" matters operationally and for fairness/audit. Some platforms shorten the life of an offer to seconds; some keep it for days. The shape is the same.

## Surge / dynamic pricing — a derived projection, not an aggregate

The price multiplier (Uber surge, Lyft prime time, DoorDash peak pay, Airbnb smart pricing, ad-exchange floor prices) is **a streaming aggregation over recent demand + supply events** — not a separate aggregate. Modelling it as an aggregate creates artificial write contention on a thing that fundamentally derives from history.

Ride-sharing aggregates by H3 hex cell: `surge-cell-{h3Index}-{minuteBucket}` is a key in a time-series store (Pinot, Druid, ClickHouse), populated by Flink jobs reading `TripRequested` + `DriverWentOnline` + `DriverMatched` events.

The critical pattern: **pin the multiplier at request time**. The `TripRequested` event carries `surgeMultiplier@request` so the fare is auditable even if surge has since dropped. Without this, every fare dispute becomes a "what was the multiplier at 14:02:07.453?" forensic exercise.

Same principle in ad exchanges (`ClearingPrice` recorded with each `Impression`), in lodging (`nightlyRate@booking`), in financial markets (`tradePrice` immutable post-trade).

## Two-sided reputation — separate aggregates per direction

Ratings appear *both ways* in every marketplace: rider rates driver, driver rates rider; customer rates restaurant, restaurant rates customer (DoorDash blocks problem customers); employer rates freelancer, freelancer rates employer.

**Each direction is a separate aggregate** because:
- They have different rules (driver ratings affect deactivation thresholds; rider ratings affect future trip priority).
- They arrive at different times (rider often rates immediately; driver may rate hours later).
- They have different privacy/visibility rules (Uber: drivers see rider's running rating; riders see driver's running rating; both are aggregates of many ratings; raw rating is not exposed).

Stream id pattern: `rating-{tripId}-rider-of-driver` and `rating-{tripId}-driver-of-rider` (or a join projection if the ratings are a single combined aggregate per match).

A single `RatingSubmitted{score, comment, byParty}` event per direction; projections aggregate to per-supply running scores. Rating updates *never* mutate the original event — corrections are new appended events. Same immutability discipline as compensating ledger entries.

## Multi-party settlement — the marketplace ledger

Every match generates a balanced multi-leg journal entry:

```
TripCompleted fare=$14.50 tip=$2.00
  -> JournalEntryPosted:
       debit  rider-payment-method     $16.50
       credit platform-commission       $3.50
       credit driver-earnings          $11.00
       credit driver-tip                $2.00
```

Each credit account participates in its own downstream payout cycle (driver weekly payout, platform daily commission roll-up, tip held separately for tax). This is the deep reason marketplace teams should adopt journal-as-truth (Camp B in [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md)) from day one — every single transaction is multi-party.

Variants of complexity:
- **Tax withholding** at point of match (TaskRabbit, Etsy in some jurisdictions) — adds tax-authority leg.
- **Platform-funded incentives** (driver quest bonus, customer first-ride credit) — adds promo-budget leg.
- **Third-party split** (Spotify song-stream split between platform, label, songwriter, publisher) — N-leg journal entries.

See [`../specific/ride-sharing-and-mobility.md`](../specific/ride-sharing-and-mobility.md) for the canonical ride-sharing version; same shape at Etsy, Airbnb (host payout - service fee - VAT - cleaning fee), Upwork (escrow held until milestone approval).

## Cancellation by any party

Two-sided platforms have at least two cancel sources; food-delivery has four (customer/merchant/courier/platform); B2B marketplaces sometimes have five. Each cancel has different downstream effects:

| Cancelled by | Compensation logic | Reputational effect |
|---|---|---|
| **Customer (demand)** | Cancel fee scales with stage (free → partial → full); supply may get partial earnings for time wasted | Customer rating may drop with repeated cancels |
| **Supply** | Often free for supply early; penalty late (DoorDash hard-deactivates couriers with high cancel rates); demand gets re-dispatched | Supply reputation drops; deactivation threshold |
| **Platform** | Customer fully refunded; supply often comped for the inconvenience; root-cause logged | None for the user; ops triage |
| **System** (timeout, fraud) | Same as platform but auto-attributed | None |

Model: a single `Cancelled{by, reason, stage, refund, compensation}` event, not separate event types per source. `by` is a domain field, not a type discriminator. Idempotent terminal state — duplicate cancels are no-ops with the same `cancelledBy`.

Refund/penalty graduation follows the cancellation-policy-by-stage pattern from [`reservations-and-finite-resources.md`](reservations-and-finite-resources.md) §6 — pre-accept free, post-accept partial, post-prep no refund (food delivery's classic gradient).

## Five failure modes marketplace platforms re-derive the hard way

1. **Matching split-brain.** Two riders both think they got the same driver. Two trades both think they hit the same limit-order quote. **Fix:** the match has to be a CAS on the supply unit or the orderbook level; in-memory matchers must serialise at the same point that durable allocation happens, *not* in parallel.
2. **Supply gone dark between offer and accept.** Driver's phone dies, courier's app crashes, ad-server times out at 95ms in a 100ms auction. **Fix:** every offer has a TTL; the ES `OfferExpired{reason}` event triggers re-dispatch; the demand-side UX must tolerate the latency added by retries.
3. **Cold start in a new city/category.** New marketplace launches in Boise; zero supply; demand requests fail; demand churns; supply doesn't see demand and doesn't onboard. **Fix:** supply-side incentives event-modelled (`SupplyOnboardingBonusGranted`, `SupplyGuaranteedEarnings`), so analytics can attribute and finance can budget. Cold-start failure is *a known marketplace phase*, not a bug — make it a first-class aggregate state.
4. **Surge feedback loop / pricing oscillation.** Surge ↑ → fewer riders → driver supply rebalances → surge ↓ → demand spikes → surge ↑ again. **Fix:** smooth the multiplier over a window in the *projection*, not the underlying events; emit `SurgeMultiplierApplied{value, smoothedFromWindow}` so the audit is honest.
5. **Sybil / bot attacks on reputation and matching.** Fake drivers accept rides and cancel for cancellation fees; bot bidders distort ad-exchange prices; sock-puppet ratings inflate listings. **Fix:** trust signals as separate aggregates fed by anti-abuse pipelines; `SupplyTrustScoreUpdated` events feed matcher scoring; never trust an actor's self-reported state.

## Cold-start: chicken-and-egg as ES events

The least-recognised marketplace property: **for the first year of a new city / category / vertical, the dynamics are completely different from steady-state.** Modeling helps:

- `MarketLaunched{geo, vertical, launchedAt, initialBudget}`
- `SupplyIncentivized{supplyId, programId, guaranteedEarnings}` — model the bonus, don't bury it in finance
- `DemandSubsidized{demandId, programId, discount}` — same for the customer-side
- `MarketLiquidityMilestoneReached{geo, supplyCount, demandRate, surgeMultiplier=1.0_for_N_days}` — the moment you can stop subsidising

DoorDash's launch playbook, Uber's market-by-market expansion, and the launch of every freelance vertical follow this pattern. Without explicit events, the cost of a launch is buried in COGS and impossible to learn from.

## Workflow engines vs aggregate-native — by latency tier

The match latency budget largely determines the architecture:

| Latency budget | Architecture | Examples |
|---|---|---|
| **<1ms** | Single-threaded matching engine (LMAX Disruptor); event log post-match | NYSE, Nasdaq, Coinbase |
| **<150ms** | In-process auction with ES outbox | Google AdX, OpenRTB exchanges |
| **<10s** | Hot in-memory matcher (Lyft ILP) + ES for trip aggregate | Ride-sharing |
| **seconds-minutes** | Workflow engine (Cadence, Temporal) coordinating ES aggregates | DoorDash dispatch, UberEats |
| **minutes-hours** | Pure aggregate-native sagas | Airbnb, Etsy, Upwork |
| **hours-days** | Human-in-the-loop sagas with explicit `*WaitingForReview` states | Freelance contract awards, lending |

See [`sagas-and-multi-step-workflows.md`](sagas-and-multi-step-workflows.md) for the engine-vs-aggregate-native trade-off.

## Patterns that survive contact with production

- **Three anchor aggregates: Demand, Supply, Match.** Never collapse them into two.
- **Match is a CAS on the supply unit.** Optimistic locking, single-threaded matcher, or workflow engine — but always a single serialisation point.
- **Hot-path matcher off the event store.** Only milestones go on the durable log.
- **Snapshot pricing at request time.** `surgeMultiplier@request`, `nightlyRate@booking`, `clearingPrice@trade` — recorded as immutable event payload, never recomputed.
- **Surge / pricing is a projection, not an aggregate.** Streaming aggregation; smoothing happens in the projection layer.
- **Two-sided reputation = two aggregates.** Different rules, different timing, different visibility.
- **Multi-party settlement = N-leg balanced journal entry.** Camp B (journal-as-truth) from day one; see [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md).
- **Cancellation by any party = single event with `by` discriminator.** Idempotent terminal state. Refund/penalty graduated by stage.
- **Offer is a first-class short-lived aggregate.** Audit who-got-asked / who-responded / who-timed-out is operationally critical.
- **Cold-start dynamics are different from steady-state — model the difference.** Launch incentives, guaranteed earnings, subsidies as ES events lets finance and product reason about them.
- **Trust score is a separate aggregate fed by anti-abuse.** Never trust supply or demand self-reported state in scoring.

## Where to look in the cloned repos

- **`oskardudycz_EventSourcing.NetCore/Sample/ECommerce/`** — multi-aggregate transactional flow that maps reasonably to a single-merchant case; the lift to marketplace is in adding a `Seller` aggregate and a per-line `Shipment` referencing it.
- **`eventuous_eventuous/samples/postgres/Bookings/`** — multi-service booking + payment, structurally similar to an Airbnb-style instant-book.

The richest marketplace examples are in the linked blog posts rather than in cloned-repo samples, because production marketplace code (Uber Fulfillment Platform, DoorDash Cadence workflows, Lyft's ILP dispatcher, LMAX Disruptor) is either proprietary or available only as engineering writeups.

## Related docs

- [`../specific/ride-sharing-and-mobility.md`](../specific/ride-sharing-and-mobility.md) — the canonical worked example: Trip + Driver + Dispatch + Offer + Rating + Shift/Earnings as anchor aggregates.
- [`../specific/food-ordering-and-delivery.md`](../specific/food-ordering-and-delivery.md) — three-sided marketplace (customer, merchant, courier) with multi-courier batching and four-source cancellation.
- [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) — when does e-commerce become a marketplace? OrderLine-per-seller, multi-tenant prefix patterns.
- [`../specific/social-feeds.md`](../specific/social-feeds.md) — attention is the marketplace; advertisers bid for it, creators supply content, the algorithm matches.
- [`sagas-and-multi-step-workflows.md`](sagas-and-multi-step-workflows.md) — dispatch as the canonical "hot-path saga"; multi-party cancellation cascades.
- [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md) — marketplace multi-party settlement as N-leg journal entries.
- [`reservations-and-finite-resources.md`](reservations-and-finite-resources.md) — when supply is finite per time slot (Airbnb listing, restaurant table, conference room), match = reservation.
- [`unbounded-and-infinite-streams.md`](unbounded-and-infinite-streams.md) §C — driver GPS / courier location / ad-exchange impression streams as off-ES telemetry.
- [Uber — Fulfillment Platform Re-architecture](https://www.uber.com/blog/fulfillment-platform-rearchitecture/).
- [Lyft — Solving Dispatch in a Ridesharing Problem Space](https://eng.lyft.com/solving-dispatch-in-a-ridesharing-problem-space-821d9606c3ff).
- [DoorDash — Building a More Reliable Checkout Service](https://careersatdoordash.com/blog/building-a-more-reliable-checkout-service-with-kotlin/) and [DeepRed dispatch optimization](https://careersatdoordash.com/blog/next-generation-optimization-for-dasher-dispatch-at-doordash/).
- [LMAX Disruptor](https://lmax-exchange.github.io/disruptor/) — single-threaded matching engine; the *thread* is the serialiser.
