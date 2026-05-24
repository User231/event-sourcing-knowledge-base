# E-Commerce & Retail — Aggregate & Stream Decomposition

Aggregate boundaries, stream-id schemes, events, sagas, and gotchas drawn from Walmart, Shopify, Salesforce B2C Commerce, ASOS, Zalando, Mercado Libre, and the practitioner work of Oskar Dudycz / Marten.

## 1. Aggregate boundaries used in production

Boundaries in e-commerce are driven by **lifecycle**, **contention**, and **who is allowed to mutate state**.

| Aggregate | Boundary rationale | Lifetime |
|---|---|---|
| **ShoppingCart** | Per-user, anonymous-tolerant, abandoned by default. Should NOT enforce stock invariants — only "intent". Short-lived; closed on Checkout/Abandon. | Hours to days |
| **Order** | Authoritative commercial document. Owns OrderLines as **internal entities**, not separate aggregates — invariants like `sum(line.subtotal) == header.total` and "order status must reflect line states" make a single transactional boundary mandatory. | Days to months (until refunds expire) |
| **OrderLine** | Almost always an entity inside Order. Promoted to its own aggregate ONLY in B2B/marketplace scenarios where each line ships from a different seller/warehouse and has independent fulfillment status (e.g., Mercado Libre marketplace, Amazon multi-seller orders). | Same as Order |
| **Customer** | Slow-changing master data. Often event-sourced for GDPR audit + preference history. | Years |
| **Product / SKU** | Catalog; usually NOT event-sourced — read-heavy, CRUD is fine. Pricing/promotions are split out. | Years |
| **Inventory / StockItem** | **One aggregate per (SKU, location)** is the canonical pattern. Per-SKU global aggregates collapse under flash-sale contention. Walmart and Salesforce both partition by `product × node` / `SKU × location`. | Indefinite |
| **Reservation** | Short-lived aggregate with TTL. Holds stock between cart-checkout and payment-capture. Salesforce models it as "Reservation Sets". | Minutes |
| **Pricing / PriceList** | Separate aggregate so that price changes don't invalidate historical orders. Orders capture the price as a fact at placement time. | Years |
| **Promotion / Coupon** | Own aggregate; tracks redemption count as invariant. Hot promo codes get the same contention problem as hot SKUs. | Campaign lifetime |
| **Payment** | Separate aggregate. PCI scope isolation + external gateway reconciliation = hard service boundary. Lifecycle: authorize → capture → settle / refund. | Days to months |
| **Shipment** | Own aggregate. An order can have N shipments (split shipment). Lifecycle is operational, not commercial. | Days to weeks |
| **Pick / Pack** | Warehouse-internal aggregates; usually a `PickTask` per picker that may span lines from multiple shipments. Operationally separate from Shipment. | Hours |
| **Return / RMA** | Own aggregate. Triggered months after Order is "closed", so it must be reopen-safe — separate stream prevents Order from being eternally open. | Days to weeks |
| **Warehouse / Location** | Reference data, not event-sourced. | |

**Why OrderLine stays an entity:** the [DDD line-items discussion](https://code.likeagirl.io/understanding-line-items-in-domain-driven-design-e118ee22665f) makes the point: "treating deeply connected entities as separate aggregates causes transactional consistency issues — what if InvoiceLine total doesn't match Invoice total?" Once you need per-line independent fulfilment, you don't split the line — you create a `Shipment` aggregate that references `(orderId, lineId, qty)`.

## 2. Stream-id naming patterns

```
cart-{userId}                          # anonymous: cart-{sessionId} or cart-{anonId}
order-{orderId}                        # UUID v7 or ULID — sortable
order-{orderId}-line-{lineId}          # only when line is promoted (rare)
inventory-{sku}-{warehouseId}          # Walmart-style partitioning by product-node
inventory-{sku}-{locationId}           # Salesforce OCI style
reservation-{reservationId}            # short-lived, TTL'd
payment-{paymentId}                    # 1:1 with order, but separate
shipment-{shipmentId}                  # 1:N from order
return-{rmaId}
pick-task-{taskId}
promotion-{promoCode}                  # natural key OK for campaigns
customer-{customerId}
pricing-{sku}-{currency}               # or pricing-{priceListId}-{sku}
```

**Multi-tenant prefix** (Shopify, Salesforce B2C Commerce): `tenant-{shopId}.order-{orderId}` so a single physical event store can partition per merchant.

**Temporal modeling** ([Oskar Dudycz — Keep your streams short](https://www.kurrent.io/blog/keep-your-streams-short-temporal-modelling-for-fast-reads-and-optimal-data-retention)): inventory streams that run forever should be cycled with the "closing the books" pattern, e.g., `inventory-{sku}-{warehouseId}-2026Q2`, ending each period with a `StockBalanceClosed` event and opening the next with `StockBalanceOpened` carrying forward only on-hand and committed totals.

## 3. Key events per aggregate

### ShoppingCart
- `CartOpened { cartId, customerId|anonId, currency }`
- `ItemAdded { sku, qty, unitPriceAtAdd }`
- `ItemRemoved { sku }`
- `ItemQuantityChanged { sku, qty }`
- `PromoCodeApplied { code }`
- `ShippingAddressProvided { address }`
- `CartConfirmed { orderId }` — terminal, closes the stream
- `CartAbandoned { reason: timeout | explicit }` — terminal

Oskar Dudycz's [Slim your aggregates](https://event-driven.io/en/slim_your_entities_with_event_sourcing/) example enforces a hard invariant: after `CartConfirmed` or `CartAbandoned` no further items can be added — achieved by making those events terminal in the decider.

### Order
- `OrderPlaced { orderId, customerId, lines[], totals, shippingAddress }`
- `PaymentAuthorized { paymentId, amount }`
- `OrderConfirmed { confirmedAt }` — after reservation + auth succeed
- `OrderLineAllocated { lineId, warehouseId, qty }` — multi-warehouse
- `OrderShipped { shipmentId, lineIds[] }` (can fire multiple times → split shipment)
- `OrderDelivered { deliveredAt }`
- `OrderCancelled { reason, byActor }`
- `OrderFraudHeld { reason }` / `OrderFraudCleared`
- `OrderRefunded { refundId, amount, partial }`

### Inventory (per SKU × Location)
Drawn from [Walmart's design](https://medium.com/walmartglobaltech/design-inventory-availability-system-using-event-sourcing-1d0f022e399f) and [Salesforce Engineering](https://engineering.salesforce.com/event-sourcing-for-an-inventory-availability-solution-3cc0daf5a742/):
- `StockReceived { qty, source: PO|return|transfer }`
- `StockReserved { reservationId, qty, expiresAt }`
- `StockAllocated { reservationId, orderId, qty }` — reservation → hard commit
- `StockReleased { reservationId, qty, reason: expiry|cancel }`
- `StockPicked { qty, taskId }`
- `StockAdjusted { delta, reason: cycle-count|damage|theft }`
- `StockTransferredOut { qty, toLocation }` / `StockTransferredIn`
- `StockBalanceClosed { onHand, committed, atp, asOf }` — period close

Salesforce uses a monotonically increasing **Event Sequence Number** per SKU-Location for optimistic concurrency — no row locks.

### Payment
- `PaymentInitiated`, `PaymentAuthorized`, `PaymentCaptured`, `PaymentDeclined`, `PaymentVoided`, `RefundIssued`, `ChargebackOpened`, `ChargebackResolved`.

### Shipment
- `ShipmentCreated { shipmentId, orderId, lineIds[], carrier }`
- `Picked { lineId, qty, pickerId, at }`
- `Packed { boxId, weights }`
- `LabelGenerated { trackingNumber, carrier }`
- `HandedToCarrier { at }`
- `OutForDelivery`
- `Delivered { signature? }`
- `DeliveryFailed { reason }`, `ReturnedToSender`

### Return / RMA
- `ReturnRequested { rmaId, orderId, lineIds[], reason }`
- `ReturnApproved` / `ReturnRejected`
- `ReturnLabelIssued`
- `ItemsReceived { condition: resellable|damaged }`
- `RestockApproved { qty }` — triggers inventory `StockReceived`
- `RefundIssued`, `LoyaltyPointsAdjusted`

## 4. Canonical sagas / process managers

### 4.1 Order placement saga (choreography or orchestration)

```
CartConfirmed
  -> Order.PlaceOrder        -> OrderPlaced
  -> Inventory.Reserve(*)    -> StockReserved  | ReservationFailed
  -> Payment.Authorize       -> PaymentAuthorized | PaymentDeclined
  -> Order.Confirm           -> OrderConfirmed
  -> Inventory.Allocate(*)   -> StockAllocated
  -> Fulfillment.CreateShipment(*) -> ShipmentCreated
```

**Compensations (modelled as first-class events, not silent rollbacks):**

| Failure | Compensation events |
|---|---|
| `ReservationFailed` | `OrderCancelled(reason=OUT_OF_STOCK)`; refund not needed (auth not done yet) |
| `PaymentDeclined` | `StockReleased` (for each reservation) → `OrderCancelled(reason=PAYMENT_FAILED)` |
| Fraud flag during auth | `OrderFraudHeld` — pauses saga, doesn't release stock yet (gives ops time) |
| Shipment cannot allocate | `OrderLineBackordered` → optional `OrderSplit` (see 4.3) |

Dudycz's [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/) emphasises: the process manager IS itself event-sourced — `OrderProcessStarted`, `OrderProcessStepCompleted`, `OrderProcessCompensating`, `OrderProcessCompleted`.

### 4.2 Returns saga

```
ReturnRequested -> ReturnApproved -> ItemsReceived
  -> split:
     Inventory.Restock     -> StockReceived (only if condition=resellable)
     Payment.Refund        -> RefundIssued
     Loyalty.Adjust        -> LoyaltyPointsDeducted
```

The interesting bit: `ItemsReceived` may happen 60+ days after `OrderDelivered`. Order must not be in a "terminal-locked" state — many teams introduce an `OrderClosed` event only after the returns window has expired.

### 4.3 Backorder / split shipment

When `OrderLineAllocated` cannot find one warehouse with full qty:

```
OrderLineAllocated { lineId=L1, warehouseId=W1, qty=2 }
OrderLineAllocated { lineId=L1, warehouseId=W2, qty=3 }   # split
OrderLineBackordered { lineId=L2, qty=1, eta }            # backorder
-> ShipmentCreated x2  (one per allocation)
-> OrderShipped fires twice — consumers must be idempotent and order-agnostic
```

Process manager subscribes to `OrderShipped` and only emits `OrderFullyShipped` when `sum(shipped.qty) == sum(line.qty)`.

## 5. Inventory modeling — the hardest part

Two distinct numbers per (SKU, location):

- **On-hand** — physical units in the building (changed by `StockReceived`, `StockPicked`, `StockAdjusted`, `StockTransferred*`).
- **ATP (Available To Promise)** — what we may sell. Per [Microsoft Dynamics ATP](https://learn.microsoft.com/en-us/dynamics365/supply-chain/inventory/inventory-visibility-available-to-promise) and [Shopify's ATP guide](https://www.shopify.com/blog/available-to-promise): `ATP = on_hand + scheduled_supply − reserved − allocated − safety_stock`.

ATP is a **projection** built from the inventory event stream, not state on the aggregate. Keeping it as a projection means:
- Multiple ATP views can exist (per-store, per-location-group, per-channel).
- Salesforce rolls Location-level ATP into a Location-Group ATP via stream subscription for BOPIS scenarios.
- ATP cache (Redis) is fed by the event log so reads are O(1).

**Reservation vs Allocation:**
- `Reserved` = soft hold for an active cart/checkout (TTL, typically 10–30 min).
- `Allocated` = hard commitment to a specific order, decremented at pick.
- Both decrement ATP; only `Allocated` decrements on-hand at pick time.

**Optimistic concurrency** — the canonical hot-SKU strategy ([Salesforce](https://medium.com/salesforce-engineering/event-sourcing-for-an-inventory-availability-solution-3cc0daf5a742)): append-with-expected-version. If two `StockReserved` events race, one fails the version check and retries against fresh state, where the second attempt may see ATP=0 and emit `ReservationFailed`.

**Oversold compensation:** when overselling does happen (cycle-count discovery, race past safety stock, sync lag with marketplaces):
- `StockAdjusted { delta=-N, reason=oversold-correction }` records the truth.
- A process manager picks losers (typically by FIFO of order placement or VIP scoring) and emits `OrderLineCancelled` + customer-comms event.

## 6. Cart: write-through vs event-sourced

The recurring debate ([Dudycz](https://event-driven.io/en/slim_your_entities_with_event_sourcing/), [Marten tutorial](https://martendb.io/tutorials/event-sourced-aggregate)):

| Approach | When | Why |
|---|---|---|
| **State-stored cart** (Redis/DynamoDB row) | High-traffic anonymous carts, simple UX-driven mutations | Event sourcing the cart for "user added then removed a toothbrush" generates noise; nobody audits cart events 6 months later |
| **Event-sourced cart** | Subscription commerce, B2B carts with multi-user editing, fraud-analysis use cases, A/B-tested checkout experiments | Cart events feed marketing/abandonment analytics; provides full history of why the order looks the way it does |

Dudycz's stance: model the cart event-sourced if you need to know *why* an order has its final composition (e.g., "the customer added it because of promo X which expired before checkout"). Otherwise, keep it as a write-through state document — the **Order** is where event sourcing earns its keep.

A common hybrid: cart is state-stored during shopping; at `CartConfirmed` time the full cart history (or just final state) is replayed as the seed event for the Order stream.

## 7. Real-world gotchas

1. **Hot SKU contention during flash sales** — partition by `sku × location`, use optimistic concurrency with sequence numbers (Salesforce), pre-reserve via Redis DECR with periodic reconciliation against the event log. Diagnosis tip: oversell timestamps clustering in the first 1–5 min of launch = race condition.
2. **Partial fulfilment** — `OrderShipped` is NOT terminal; `OrderFullyShipped` is. Downstream subscribers (warehousing dashboards, customer emails) must be partial-aware.
3. **Fraud holds** — `OrderFraudHeld` is not a saga compensation; it's a pause. Inventory remains reserved. Many teams forget this and release stock too early.
4. **Returns months later** — never put Order into a "closed" state until the legal return window + chargeback window have expired (60–180 days). Return is a separate aggregate referencing Order by id.
5. **GDPR vs immutability** — strategies ([Dudycz on GDPR](https://event-driven.io/en/gdpr_in_event_driven_architecture/), [Conduktor](https://www.conduktor.io/blog/gdpr-kafka-right-to-erasure)):
   - **Crypto-shredding**: PII fields encrypted with per-customer key; key deletion makes events unreadable. Caveat: regulators may still consider encrypted PII to be PII.
   - **PII tokenization / external vault**: events store tokens; a separate Vault (e.g., HashiCorp Vault) resolves them; revoking returns null.
   - **Stream rewrite**: copy the stream minus the PII; only acceptable when you control all subscribers.
6. **B2B order modification post-placement** — B2B sales reps routinely edit prices/quantities after `OrderPlaced` ([Shopify B2B draft orders](https://help.shopify.com/en/manual/b2b/checkout-and-orders/draft-orders)). Model via `OrderLineRepriced`, `OrderLineAdded`, `OrderLineRemoved` events that fire pre-fulfilment. The Order aggregate must enforce that these are only valid while status ∈ {Draft, AwaitingApproval}.
7. **Idempotency keys on commands** — every command from the checkout (`PlaceOrder`, `Reserve`, `Authorize`) carries a deduplication key; Mercado Libre [had to invest heavily in event deduplication](https://cloud.google.com/blog/topics/retail/inside-mercado-libres-multi-faceted-spanner-foundation-for-scale-and-ai) to prevent duplicate orders.

## 8. Case studies & sources

- **Walmart Global Tech — Inventory Availability via Event Sourcing**: per `product × node` partitioning, Kafka + Cassandra read side. [Medium](https://medium.com/walmartglobaltech/design-inventory-availability-system-using-event-sourcing-1d0f022e399f) and [Confluent — Walmart real-time inventory](https://www.confluent.io/blog/walmart-real-time-inventory-management-using-kafka/).
- **Salesforce B2C Commerce — Omnichannel Inventory (OCI)**: event-sourced log per SKU-Location, Reservation Sets, Location-Group ATP rollup projection. [Salesforce Engineering](https://engineering.salesforce.com/event-sourcing-for-an-inventory-availability-solution-3cc0daf5a742/).
- **Shopify — Kafka at 66M msg/s**: Monorail event abstraction, CDC + business events. [Factor House](https://factorhouse.io/articles/shopify-kafka-architecture); [Shopify Engineering — real-time buyer signals](https://shopify.engineering/real-time-buyer-signal-data-pipeline-shopify-inbox).
- **Zalando — Nakadi**: REST event bus over Kafka, ordered delivery via partition keys. [Nakadi manual](https://zalando-nakadi.github.io/nakadi-manual/).
- **ASOS — Azure Service Bus + Cosmos DB change feed**: [ASOS Tech Blog](https://medium.com/asos-techblog/solution-architecture-asos-ed21a79a0182), [Microsoft customer story](https://www.microsoft.com/en/customers/story/718983-asos-retail-and-consumer-goods-azure).
- **Mercado Libre — Spanner change streams**: 214K QPS, heavy event deduplication. [Google Cloud Blog](https://cloud.google.com/blog/topics/retail/inside-mercado-libres-multi-faceted-spanner-foundation-for-scale-and-ai).
- **Amazon DynamoDB Streams**: CDC log for checkout/order tables; Zepto's storefront refactor builds aggregations from `Draft_Orders` change stream. [AWS Blog — Zepto](https://aws.amazon.com/blogs/database/how-zepto-scales-to-millions-of-orders-per-day-using-amazon-dynamodb/).
- **Oskar Dudycz / Marten samples**: [EventSourcing.NetCore](https://github.com/oskardudycz/EventSourcing.NetCore), [Slim your aggregates](https://event-driven.io/en/slim_your_entities_with_event_sourcing/), [Closing the Books in practice](https://event-driven.io/en/closing_the_books_in_practice/), [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/), [GDPR in EDA](https://event-driven.io/en/gdpr_in_event_driven_architecture/).
- **Marten e-commerce sample**: [ECommerceEventSourcing](https://github.com/mohamedelareeg/ECommerceEventSourcing).

## Local code references

- `repos_cloned/oskardudycz_EventSourcing.NetCore/Sample/ECommerce/` — multi-service (Carts, Orders, Shipments, Payments) — see `Carts/Carts/ShoppingCarts/ShoppingCart.cs`, `Orders/Orders/Orders/OrderEvent.cs`, `Shipments/Shipments/Products/ProductAvailabilityService.cs`.
- `repos_cloned/oskardudycz_EventSourcing.JVM/samples/event-sourcing-esdb-aggregates/src/main/java/io/eventdriven/ecommerce/shoppingcarts/` — Java aggregate + event hierarchy reference.
- `repos_cloned/oskardudycz_EventSourcing.NodeJS/` — TypeScript shopping-cart focus.
