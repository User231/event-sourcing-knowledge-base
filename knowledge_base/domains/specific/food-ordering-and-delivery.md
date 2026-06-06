# Food Ordering & Delivery — Aggregate & Stream Decomposition

How real platforms (DoorDash, Uber Eats, Wolt, Instacart, Deliveroo, plus POS like Toast/Olo) carve the domain into aggregates, streams, and sagas. The two defining splits in this domain: **Cart ≠ Order** (different consistency rules) and **Order ≠ Delivery** (different lifecycle, different operational owner).

Food delivery is a *three-sided* marketplace (customer + restaurant + courier + platform). The cross-domain marketplace mechanics — Demand/Supply/Match anchor aggregates, dispatch as compare-and-swap, multi-party settlement, four-source cancellation, hot in-memory matcher vs durable ES — are in [`../cross-cutting/marketplaces-and-matching-engines.md`](../cross-cutting/marketplaces-and-matching-engines.md).

## 1. Aggregate boundaries used in practice

Boundaries are driven by **lifecycle, consistency rules, and who owns the truth** — not by entity nouns.

| Aggregate | Why it's its own boundary | Notes from real systems |
|---|---|---|
| **Cart** | Highly mutable, transient, owned by the consumer client. No regulatory audit need. Most "writes" are user mistakes (added/removed an item). | DoorDash has an explicit "Order Cart Service" separate from the order service. Often **not** event-sourced — CRUD with a Redis/Cassandra row. Events that matter only start at checkout. |
| **Order** | Hard audit requirement (tax, payment, dispute). Multi-party contract: customer ↔ merchant ↔ platform. Different invariants than a cart (immutable items once accepted, refunds appended). | DoorDash's Order Service writes to Cassandra, drops `OrderSubmitted` to Kafka, kicks off a Cadence workflow. State machine: `CREATED → PAID → SENT_TO_RESTAURANT → CONFIRMED → PREPARING → DRIVER_ASSIGNED → DRIVER_AT_RESTAURANT → PICKED_UP → DELIVERED → COMPLETED`. |
| **Delivery / Drop / Job** | Independent lifecycle: a delivery can be re-assigned, batched, or fail while the order is fine. Owned by logistics, not commerce. | Uber's fulfillment platform splits **Trip** (the work, with waypoints) from **Supply** (the courier). Modelled as **statecharts** with cross-entity writes coordinated by "Business Transaction Coordinators" over Spanner. |
| **Courier / Driver / Dasher** | Long-lived. Online/offline, location, current shift. Cross-cuts many deliveries. | DoorDash's Dasher entity is updated via a separate stream (online/offline). Dispatch ("DeepRed") consumes courier state + order state to assign. |
| **Dispatch / Assignment** | The decision to bind a delivery to a courier is a distinct event with its own retry & reversal semantics (re-assignment is common). | Wolt: "A courier partner is always assigned after the order has been created… the delivery may be reassigned if delays occur." Optimisation runs every 30–60s. |
| **Restaurant / Merchant** | Reference data + operational state (open/closed, prep-time, store hours). | Wolt webhooks operate **at the merchant level**: all venues for the merchant share one webhook endpoint. |
| **Menu** | Versioned catalog. Changes infrequently relative to availability. | Olo+Toast: menu sync is a separate flow from order injection. |
| **MenuItemAvailability ("86" state)** | Changes per item, many times per shift. Different write frequency from the menu itself, different consumers (search/ranking projection). | DoorDash exposes **per-item 86'ing webhooks** that update availability in real time — separate from menu CRUD. |
| **Payment** | Regulated; PCI scope; separate audit trail. Authorize / capture / refund have their own lifecycle. | Always its own service. Payment failure compensates the order saga. |
| **Refund** | Often opened **after** delivery; can be partial; references both order and payment. | Distinct stream so partial refunds, disputes, and chargebacks can be replayed independently of the order. |
| **Promo / Coupon** | Independent issuance & redemption lifecycle, fraud-relevant. | |
| **Rating / Review** | Created after delivery; separate stream so order replay isn't polluted with social data. | Confirmed across Wolt, Uber, DoorDash. |
| **Tip** | Often *adjusted after delivery* (24h tip window on DoorDash, Instacart). Modelled as its own append rather than mutating the order. | DoorDash and Instacart both allow post-delivery tip adjustment — naturally an appended event on a tip/payment stream. |

The cart→order split exists because of **different consistency rules**: a cart tolerates "last writer wins" on a single user's clicks; an order needs strict serialisability around payment + merchant acceptance.

## 2. Stream-id naming patterns

```
cart-{userId}-{sessionId}              # often NOT event-sourced (see §5)
order-{orderId}                        # canonical, immutable id minted at checkout
delivery-{deliveryId}                  # 1:1 with order in most cases, 1:N for batched
courier-{courierId}                    # long-lived
restaurant-{merchantId}                # long-lived; menu/availability often sub-streams
menu-{merchantId}-v{n}                 # menu version
item-availability-{merchantId}-{sku}   # high-write rate; per-item stream
payment-{paymentId}                    # one auth/capture per payment id
refund-{refundId}                      # separate; refers to order+payment
dispatch-{orderId}                     # ephemeral; assignment decisions
rating-{orderId}                       # post-delivery, separate stream
```

## 3. Key events per aggregate

### Order
- `OrderPlaced` (the cart snapshot is *frozen* into this event — items, prices, addresses, promotions applied)
- `OrderAcceptedByRestaurant` / `OrderRejectedByRestaurant`
- `OrderPaymentAuthorized` / `OrderPaymentCaptured` / `OrderPaymentFailed`
- `OrderItemsSubstituted` (grocery)
- `OrderPrepared` / `OrderReadyForPickup`
- `OrderPickedUp`
- `OrderDelivered`
- `OrderCancelled` (with `cancelledBy: customer|merchant|courier|platform`)
- `OrderRefunded` (full or partial; references refund stream)
- `OrderTipAdjusted` (post-delivery)
- `OrderRated`

DoorDash uses essentially these as state-machine transitions in its Cadence workflow.

### Delivery
- `DeliveryCreated`
- `CourierAssigned` / `CourierReassigned` / `CourierUnassigned`
- `CourierEnRouteToRestaurant`
- `CourierArrivedAtRestaurant`
- `OrderPickedUp`
- `EnRouteToCustomer`
- `DeliveredToCustomer`
- `DeliveryFailed` (with reason: `customer_unreachable`, `wrong_address`, `damaged`)
- `DeliveryBatched` (for route consolidation — links to other delivery ids)

Wolt's webhook stream emits roughly this set ([Wolt Drive webhooks](https://developer.wolt.com/docs/wolt-drive/webhooks)).

### Menu / Availability
- `MenuPublished` (version bump)
- `ItemMadeAvailable`
- `Item86d` (sold out — DoorDash's exact terminology)
- `ItemPriceChanged`
- `ItemRestocked`

### Courier
- `CourierWentOnline` / `CourierWentOffline`
- `CourierLocationUpdated` (very high volume; sometimes streamed to a *separate* topic from the courier aggregate stream)
- `CourierShiftStarted` / `CourierShiftEnded`

### Cart (if event-sourced — see §5)
- `CartOpened`
- `ItemAddedToCart`
- `ItemRemovedFromCart`
- `ItemQuantityChanged`
- `PromoCodeApplied`
- `CartConfirmed` → triggers `OrderPlaced` on a fresh stream

(Naming matches Oskar Dudycz's canonical sample.)

## 4. Cross-aggregate processes / sagas

This domain is the clearest case for **workflow engines over aggregate-native sagas** — Cadence at DoorDash, Temporal at Uber Eats. The compensation rules also have a sharp time-axis (pre-accept / post-accept / post-prep cancellation policies). For the cross-domain landscape of saga families and the orchestrator-vs-aggregate-native trade-off, see [`../cross-cutting/sagas-and-multi-step-workflows.md`](../cross-cutting/sagas-and-multi-step-workflows.md).

### Canonical "happy path" — orchestrated saga

DoorDash's blog spells it out ([Building a More Reliable Checkout Service](https://careersatdoordash.com/blog/building-a-more-reliable-checkout-service-with-kotlin/)): Order Service → Kafka `OrderSubmitted` → Cadence workflow → state-machine steps (fraud check, payment authorise, delivery creation, send-to-merchant) each calling a sibling microservice over gRPC. Each step has a compensation.

```
Customer -- CheckoutCart --> Order Service
                                  |  writes order to Cassandra
                                  |  publishes OrderSubmitted (Kafka)
                                  v
                          Cadence Workflow
                                  |
        +-------------------------+-------------------------+
        v                         v                         v
  FraudCheck            AuthorizePayment           CreateDelivery
  (compensate:          (compensate:               (compensate:
   none)                 VoidAuth)                  CancelDelivery)
                                  |
                                  v
                       SendOrderToMerchant
                       (compensate: NotifyMerchantCancel)
                                  |
                                  v
                       wait MerchantAccept event
                                  |
                       +----------+----------+
                       v                     v
                  Accepted               Rejected
                  -> continue       -> compensate(VoidAuth, NotifyCustomer)
```

### Substitution / mid-flight modification (Instacart's signature flow)

1. Shopper scans empty shelf → `ItemUnavailableAtPick` (item-level event).
2. Engine reads customer pref: refund / replace / approve-via-chat.
3. If replace: `ItemReplacementProposed` → customer notification.
4. Customer accepts → `OrderItemsSubstituted` on the order stream.
5. Price delta recomputes: `OrderTotalAdjusted`.
6. On checkout: `CheckoutComplete`, then `OrderItemRefund` for any not-found items.

Instacart's webhook taxonomy exposes exactly these ([Instacart Event Callbacks](https://docs.instacart.com/connect/api/fulfillment/communications/event_callbacks/)): `Acknowledged`, `Picking`, `Order item replacement`, `Item replaced`, `Item refunded`, `Checkout`, `Delivering`, `Late delivery`.

### Cancellation policy by stage

The graded-by-stage refund policy below generalises across reservation-shaped domains (hotel cancellation windows, airline fare buckets, restaurant deposits, doctor no-show fees) — see [`../cross-cutting/reservations-and-finite-resources.md`](../cross-cutting/reservations-and-finite-resources.md) §6 for the cross-domain pattern.

- **Pre-accept** (before `OrderAcceptedByRestaurant`): customer cancellation is **free**. Compensation: `VoidAuth`.
- **Post-accept, pre-prep**: usually free, sometimes partial. Compensation: `VoidAuth` + `NotifyMerchantCancel`.
- **Post-prep, pre-pickup**: partial refund (food cost forfeit, delivery refunded). Compensation: `PartialRefund` + `ReassignOrCancelDelivery`.
- **Post-pickup**: **no automatic refund** — goes to support. Emits `OrderCancellationRequested` but waits on human decision.

This is encoded as guard rules on the order state machine — the same state diagram has different allowed transitions per state.

### Two/three-sided cancellation

Any of {customer, merchant, courier, platform} can cancel. The aggregate enforces:
- Only one terminal `OrderCancelled`; subsequent attempts return idempotent no-op.
- `cancelledBy` is captured for analytics, ratings adjustment, and merchant-SLA penalties.

### Multi-courier batching

A single courier picks up two orders going to nearby drop-offs. Modelled as:
- Each `delivery-{id}` stream stays independent.
- A `batch-{batchId}` stream emits `DeliveriesBatched(deliveryIds=[...])`, `BatchRouteOptimized`, `BatchPickupCompleted`, `BatchDeliveryCompleted`.
- The dispatch aggregate decides batching; deliveries are notified but stay first-class.

## 5. Cart vs Order — the recurring debate

Two viable approaches, both used in production:

**Approach A: Cart is CRUD, Order is event-sourced.**
- Cart sits in Redis/DynamoDB/Cassandra as a mutable row. No history kept.
- On checkout, the cart snapshot is *baked* into the first `OrderPlaced` event on a brand-new `order-{id}` stream.
- This is what DoorDash effectively does: Order Cart Service is a separate microservice on its own storage; events start at order creation.
- **Pros**: cheap, fast, no need to replay carts (they're abandoned 70%+ of the time). Easy "merge guest cart on login."
- **Cons**: lose the "why did this user keep removing items" signal. Marketing teams sometimes want it back.

**Approach B: Cart is event-sourced.**
- `cart-{userId}-{sessionId}` stream with `CartOpened`, `ItemAddedToCart`, …, `CartConfirmed`.
- `CartConfirmed` is the trigger; an `OrderPlaced` is then written on a fresh `order-{id}` stream — the cart is **not** the order, it's the input.
- This is Oskar Dudycz's recommended pedagogical model ([Slim your aggregates with Event Sourcing](https://event-driven.io/en/slim_your_entities_with_event_sourcing/)) and matches his samples.
- **Pros**: full behavioural analytics, replayable cart abandonment funnel.
- **Cons**: high write volume for events that mostly don't matter; need TTL/archival; cross-device cart merging is messy.

Most large platforms pick A for production and B only if cart analytics are a first-class requirement.

## 6. Real-world gotchas

- **Restaurant offline mid-order.** Order placed but merchant terminal hasn't acked in N seconds. DoorDash retries via Cadence; after timeout, auto-cancel + refund. Encoded as a workflow timer, not an order-aggregate concern.
- **Item out-of-stock after acceptance.** Merchant POS 86's an item *after* accepting. Emits `OrderItemUnavailable`; consumer flow asks customer "refund or substitute." This is why grocery (Instacart) had to build a full substitution domain; restaurant platforms typically just refund the line item.
- **Late acceptance.** Merchant takes 8 minutes to accept; courier was already speculatively dispatched. Dispatch must handle both "merchant declined after courier en-route" and "merchant accepted but ETA stale."
- **Courier no-show.** `CourierAssigned` but no `CourierEnRouteToRestaurant` within SLA → automatic `CourierUnassigned` + re-dispatch.
- **Two/three-sided cancellation.** Idempotent terminal state with `cancelledBy` captured.
- **Tips arriving after delivery.** Don't mutate the order — append `OrderTipAdjusted` (and a `PaymentCaptureIncreased` on the payment stream). DoorDash and Instacart both have 24h tip-edit windows that work this way.
- **Ratings.** Separate stream. The order is "closed" — rating arrives async and shouldn't reopen the order aggregate.
- **Multi-store / split orders.** Some platforms (Wolt's "group order," Instacart multi-retailer cart) split into multiple `order-{id}` streams that share a `cart-{id}` parent. Each order is independently fulfillable.
- **Real-time courier location updates** are extremely high-volume. Don't put them on the courier aggregate stream; use a separate location topic with short retention. The aggregate stream gets `CourierShiftStarted` / `CourierWentOffline`, not every GPS tick.
- **Idempotency for state-machine transitions.** Two services may both observe "merchant ack" and try to write `OrderAcceptedByRestaurant`. DoorDash notes: "must ensure transitions are idempotent and atomic" — usually by guarding on expected-version of the order stream.

## 7. Sources & case studies

- **DoorDash — Building a More Reliable Checkout Service** (Cassandra + Kafka + Cadence): https://careersatdoordash.com/blog/building-a-more-reliable-checkout-service-with-kotlin/
- **DoorDash — Cadence as a Fallback for Event-Driven Processing**: https://careersatdoordash.com/blog/building-reliable-workflows-cadence-as-a-fallback-for-event-driven-processing/
- **DoorDash — Iguazu / Kafka + Flink event platform** (100B events/day): https://careersatdoordash.com/blog/building-scalable-real-time-event-processing-with-kafka-and-flink/
- **DoorDash — DeepRed dispatch ML/optimization**: https://careersatdoordash.com/blog/next-generation-optimization-for-dasher-dispatch-at-doordash/
- **DoorDash — Item 86'ing webhook contract**: https://developer.doordash.com/en-US/docs/marketplace/how_to/item_status/
- **Uber — Fulfillment Platform Rearchitecture**: https://www.uber.com/us/en/blog/fulfillment-platform-rearchitecture/
- **Uber — Building Uber's Fulfillment Platform for Planet-Scale**: https://www.uber.com/blog/building-ubers-fulfillment-platform/
- **Instacart — Real-Time Item Availability**: https://www.infoq.com/news/2024/02/instacart-item-availability/
- **Instacart — Event Callbacks**: https://docs.instacart.com/connect/api/fulfillment/communications/event_callbacks/
- **Instacart — Order Status flow**: https://docs.instacart.com/connect/post-checkout_guide/tutorials/implement_order_status/
- **Wolt — Drive webhooks**: https://developer.wolt.com/docs/wolt-drive/webhooks
- **Wolt — From polling to WebSockets for order tracking**: https://careers.wolt.com/en/blog/engineering/from-polling-to-websockets-improving-order-tracking-user-experience
- **Toast ↔ Olo integration**: https://pos.toasttab.com/integrations/olo
- **Oskar Dudycz — Slim your aggregates** (canonical shopping-cart sample): https://event-driven.io/en/slim_your_entities_with_event_sourcing/
- **Oskar Dudycz — Handling events coming in an unknown order**: https://event-driven.io/en/strict_ordering_in_event_handling/
- **Reference implementation — `digital-restaurant`** (Axon, Kafka, RabbitMQ): https://github.com/idugalic/digital-restaurant

## Key takeaways

1. **Cart and Order are not the same aggregate**, even though they share items. Different lifecycle, different audit needs, different write frequency.
2. **Delivery is its own aggregate**, never an attribute of Order. It can be reassigned, batched, and fail independently.
3. **State machines + sagas + orchestrator** (Cadence / Temporal at DoorDash and Uber) is the dominant production pattern — not pure choreography. Long-running workflows with compensating actions need a workflow engine in front of the aggregates.
4. **Availability ("86'ing") needs its own stream/topic**, separate from menu — write rates differ by 2–3 orders of magnitude.
5. **Tips, ratings, and refunds are appended to separate streams**, not as mutations of a closed order.
6. **Courier GPS pings do not belong on the courier aggregate stream** — that's a high-volume sidecar topic with short retention.
