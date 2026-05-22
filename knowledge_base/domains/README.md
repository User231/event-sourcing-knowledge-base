# Real-World Event Sourcing — Aggregate & Stream Decomposition by Domain

How production systems actually carve real domains into aggregates and streams. Each file in this directory is a field guide for one domain — concrete aggregate boundaries, stream-id patterns, key events, the canonical sagas, and the gotchas that bite teams once they leave the textbook.

Per the core rule (see [../concepts/core-concepts.md](../concepts/core-concepts.md) and [../implementation-patterns/multi-aggregate-commands-and-sagas.md](../implementation-patterns/multi-aggregate-commands-and-sagas.md)): **one command touches exactly one aggregate**. Decomposition therefore drives almost every downstream design choice — how you draw boundaries determines what your sagas, projections, and read models look like.

## Domains

| File | Industries it covers |
|---|---|
| [banking-and-finance.md](banking-and-finance.md) | Retail/commercial banking, neobanks, payments, lending, ledger platforms (Monzo, Square, Wise, Modern Treasury, TigerBeetle) |
| [ride-sharing-and-mobility.md](ride-sharing-and-mobility.md) | Ride-hailing, micromobility, on-demand delivery dispatch (Uber, Lyft, Grab, DoorDash, Lime/Bird) |
| [food-ordering-and-delivery.md](food-ordering-and-delivery.md) | Food delivery, grocery, restaurant POS integration (DoorDash, Uber Eats, Wolt, Instacart, Toast, Olo) |
| [ecommerce-and-retail.md](ecommerce-and-retail.md) | Retail commerce, marketplaces, B2B platforms, inventory (Walmart, Shopify, Salesforce B2C, Zalando, ASOS, Mercado Libre) |
| [hotel-and-hospitality.md](hotel-and-hospitality.md) | PMS, OTA distribution, channel managers, group bookings (Booking.com, Mews, Marriott; Dudycz's canonical HotelManagement sample) |

## Patterns that recur across every domain

Read the per-domain files for specifics, but the same five forces show up everywhere:

1. **The "request" and the "thing requested" are different aggregates.** Reservation ≠ Stay. Cart ≠ Order. Authorization ≠ Posted withdrawal. They share data, not lifecycle. Conflating them is the canonical modelling mistake.

2. **High-volume telemetry doesn't go in event streams.** Driver GPS pings, courier locations, IoT sensors, page-view tracking — these live in hot stores (Redis/Kafka topics with short retention) and only **milestone** events get appended to the aggregate stream.

3. **Hot-write aggregates need sharding.** Fee accumulators, suspense accounts, flash-sale SKUs, popular ride-hailing geo-cells all blow up the single-stream optimistic-lock model. The fix is partition keys (`account-{id}-{period}`, `inventory-{sku}-{warehouseId}`, `surge-cell-{h3}-{minute}`) — not a bigger machine.

4. **"Closed" aggregates often get reopened.** Returns months after delivery. Chargebacks 60 days after settlement. Tip adjustments 24h after a ride. Never put an aggregate into a terminal-locked state until every regulatory/policy window has expired — or model the post-close events as their own aggregate (`Return`, `Dispute`, `TipAdjustment`).

5. **Compensation is event-shaped, not rollback-shaped.** A failed step in a saga doesn't undo earlier events; it appends new ones (`StockReleased`, `WithdrawalReleased`, `ReservingEntryPosted`, `FareAdjusted`). The audit trail tells you what happened *and* what unhappened. See [../implementation-patterns/multi-aggregate-commands-and-sagas.md](../implementation-patterns/multi-aggregate-commands-and-sagas.md).

## Heuristics for drawing aggregate boundaries

Distilled from Vaughn Vernon's [Effective Aggregate Design](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf) and observation across the domains here:

- **Different lifecycle → different aggregate.** If A can be deleted/cancelled/closed while B continues — they're different.
- **Different write frequency by 10×+ → different aggregate (or different store).** Catalog vs. price-changes; reservation vs. availability projection; courier-online vs. courier-location.
- **Different consistency window → different aggregate.** Same transaction (auth a card) vs. eventually consistent (settle the network file).
- **Different audit/compliance scope → different aggregate.** PCI scope, KYC scope, GDPR scope, GAAP scope.
- **Different actor / team owns it → different aggregate.** Distribution team owns Reservation; front-desk team owns GuestStay.

When in doubt, split. Merging two streams later is harder than the other direction.

## Where to look in the cloned repos

Real worked examples available locally in `repos_cloned/`:

- **Hotel** (the richest sample): `oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/` — three variants (saga / choreography / process-manager) of the canonical GroupCheckout flow.
- **E-Commerce**: `oskardudycz_EventSourcing.NetCore/Sample/ECommerce/` — ShoppingCart, Order, Shipment, Payment with their interactions.
- **Shopping Cart** (focused): `oskardudycz_EventSourcing.NodeJS/` and `oskardudycz_EventSourcing.JVM/samples/event-sourcing-esdb-aggregates/`.
- **Bank Account** (basic, intentionally so): `oskardudycz_EventSourcing.JVM/workshops/build-your-own-event-store/solved/src/test/java/bankaccounts/`.
- **University / Faculty** (course bookings, capacity invariants): `AxonFramework_AxonFramework/examples/university-java/`.
- **Booking + Payment** (multi-service): `eventuous_eventuous/samples/postgres/Bookings/`.
