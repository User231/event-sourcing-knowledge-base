# Ledgers, Double-Entry & Money Semantics

The textbook `BankAccount{Deposited, Withdrawn}` aggregate is where every event-sourcing course starts and where every real fintech leaves it behind. The moment you have **two parties to a transaction, multiple currencies, late-arriving reconciliations, hot accounts, regulatory replay, or any meaningful sum-of-money invariant**, you've left ordinary ES territory and entered ledger territory — a place with its own century-old conventions (debits = credits, immutable journal, closing the books) that the event-sourcing community has been steadily rediscovering.

This doc is the cross-domain view. The deep dive on retail banking lives in `[../specific/banking-and-finance.md](../specific/banking-and-finance.md)`; on subscription billing in `[../specific/long-running-subscriptions.md](../specific/long-running-subscriptions.md)`; but **ledger-shaped problems appear in every transactional domain in this directory**, and the same five or six patterns recur each time.

## Where ledger semantics actually appear


| Domain                                      | What's the ledger                                                                  | Notes                                                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Retail banking / fintech**                | Account balances + journal entries                                                 | The literal accounting case. Square Books, Modern Treasury, TigerBeetle.                             |
| **Card networks / PSPs**                    | Auth → clear → settle pipeline; merchant ledger                                    | Three balances per account (pending, available, settled).                                            |
| **Subscription billing**                    | Invoice line items + revenue subledger                                             | Cash ledger ≠ revenue ledger (ASC 606). Stripe, Chargebee, Recurly, Zuora.                           |
| **E-commerce**                              | Order totals, refunds, store credit, gift cards, loyalty points                    | Often *under*-modelled as ledger; refunds bite the team that didn't.                                 |
| **Hotel**                                   | In-house folio (open ledger during stay) → invoice (closed)                        | Two distinct ledger shapes: live mutation vs immutable artefact.                                     |
| **Marketplaces (ride / food / freelance)**  | Driver/merchant/seller earnings; platform-take split; payouts                      | Multi-party settlement — every transaction touches platform + supply + sometimes a third (tax, tip). |
| **Ad-tech**                                 | Impression/click accumulator → advertiser invoice → publisher payout               | A ledger run at billions/day where the unit is fractional cents.                                     |
| **Crypto / UTXO**                           | Each transaction is *literally* a journal entry (inputs = outputs by construction) | Blockchain is the planetary-scale double-entry ledger; mining = consensus on the next journal entry. |
| **Loyalty / points**                        | Same shape as money; different unit                                                | Frequent-flyer miles, hotel points, store credit. Multi-year expiry, status-tier rollover.           |
| **Carbon credits / RECs / inventory units** | Allocated, transferred, retired                                                    | Non-fungible ledger entries with chain-of-custody.                                                   |


The unifying property: **the truth of the system is a sequence of value-conserving transactions, and any state (balance, position, allocation) is a projection of that sequence.** The accountant's "trial balance must balance" is the original event-sourced projection.

## The two architectural camps

When you draw the aggregate, you face one decisive choice — it shapes everything else.

### Camp A — Ledger entries embedded in account aggregates

Each account is an aggregate. A transfer appends `DepositRecorded` on one account stream and `WithdrawalPosted` on another. Balance is a projection over the stream. This is what every "event sourcing 101" tutorial does.

**Works for:** small systems, ≤thousands of writes/sec, single currency, no separate audit obligation.

**Breaks when:** you need to *prove* `sum(debits) == sum(credits)` system-wide (reconciliation requires joining N streams); hot accounts hit the optimistic-lock wall; the regulator wants the journal as the audit artefact and there isn't one.

### Camp B — Separate journal stream as source of truth

A single global (or per-tenant) `journal-`* stream holds `JournalEntryPosted{debits[], credits[]}` where each entry is *structurally balanced* (`sum(debits) == sum(credits)` per currency, enforced at the API). Account streams become **projections** of the journal — not aggregates.

This is how **Square Books** ([blog](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/)), **Modern Treasury Ledgers** ([How to Scale a Ledger Pt V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v)), and **TigerBeetle** all work. Square's Books post puts it baldly: *"both journal and book entries data sets are effectively append-only and immutable once stored. Besides the books table, there are no update statements — only inserts. If you make a mistake, you write a new entry that corrects the previous one rather than updating in place."*

**Works for:** anything with reconciliation, audit, or high contention.

**Breaks when:** you've outgrown a single Postgres for the journal and need to shard. The next move is purpose-built (TigerBeetle), or sharding the journal by tenant / day / accounting unit.

The pattern: **most teams start in Camp A and migrate to Camp B the first time the regulator audits the system or the fee accumulator melts.** The migration is painful. If you can predict you'll need it, start there.

## The double-entry invariant — and what it buys you

> Every transaction is recorded as one or more debits **and** one or more credits, where `sum(debits) == sum(credits)` per currency.

This is not a money-specific thing. It's a *structural invariant that makes reconciliation cheap*:

- **Trial balance is O(1).** Sum all debits, sum all credits, they match. If they don't, you have a corruption — locate it by binary-search on time.
- **Cross-account reconciliation is local.** Every transfer touches exactly two (or N balanced) accounts. You never need a transaction across N aggregates if N > 2 — the journal entry IS the transaction.
- **Compensation is structurally honest.** You can't accidentally "lose" money by reverting one side and forgetting the other; the reversing entry has to balance too.

You get the same benefit in non-money ledgers: a loyalty-points transfer between user accounts, a carbon-credit allocation, an inventory unit moving between warehouses — all benefit from forcing every transaction to be a balanced N-leg entry.

Modern Treasury enforces the invariant at the API layer ([Designing the Ledgers API with Concurrency Control](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking)); TigerBeetle enforces it in the storage primitive itself.

## Compensation = reversing entries, never edits

The single most-violated ledger rule in non-finance domains:


| Wrong                                              | Right                                                                       |
| -------------------------------------------------- | --------------------------------------------------------------------------- |
| Update `Charge.amount` after a dispute             | Append `ChargeAdjusted{delta, reason: "dispute"}` or `ReversingEntryPosted` |
| Delete `OrderPlaced` when fraud detected           | Append `OrderCancelled` + `RefundIssued`                                    |
| Mutate `TripCompleted.fare` when toll arrives late | Append `FareAdjusted{delta, reason: "toll"}`                                |
| Edit `InvoiceFinalised` to change a line item      | Append `CreditNoteIssued` (Stripe / Chargebee enforce this)                 |
| Backdate a `JournalEntry` to fix an error          | Append a *new* journal entry today that reverses or corrects the old one    |


Square's discipline: *"there are no update statements — only inserts."* This is also the deep reason **the journal is the audit artefact** — auditors care that no one *can* secretly amend history, not just that no one *did*.

## Multi-currency, value-date, idempotency — the three things every ledger must handle

Three concerns that all four of {banking, subscriptions, marketplaces, e-commerce ledgers} discover the hard way.

### Multi-currency

- Every monetary event carries `currency`. Always. No exceptions, even if you're "only" USD today.
- Balances are *per currency*. Never sum across currencies without an explicit FX event.

- FX trade = balanced journal entry with debits in one currency, credits in another, **plus** an explicit `FXRateApplied{baseCcy, quoteCcy, rate, source, asOf}` event so the rate is auditable.
- See [SDK.finance — Multi-currency ledger](https://sdk.finance/blog/what-is-a-multi-currency-ledger-how-fintechs-track-balances-transfers-and-settlement-across-currencies/).

### Value-date ≠ event-time

- `occurredAt` = wall-clock when the system recorded the event.
- `valueDate` = the date the transaction *takes effect* for accrual, interest, settlement, period attribution.
- They are routinely different (ACH posts T+2; year-end adjustment booked in January with December value-date; backdated correction). Every monetary event must carry both. See Verraes, [Practical Event Sourcing](https://verraes.net/2014/03/practical-event-sourcing/).

### Idempotency

- Every command into a ledger aggregate carries an `idempotencyKey`. The aggregate (or a dedup table fed by a projection) rejects duplicates.
- Monzo's payment-processing post: the same instruction may arrive twice from upstream rails and the ledger must remain balanced.
- Mercado Libre invested heavily in Spanner-based event deduplication specifically for ledger writes ([Inside Mercado Libre's Spanner foundation](https://cloud.google.com/blog/topics/retail/inside-mercado-libres-multi-faceted-spanner-foundation-for-scale-and-ai)).
- Idempotency key sources: client-generated (`requestId`), upstream PSP id (`paymentIntent.id`), saga step id. **Content hash is risky** for ledgers — two genuine `Charge($10)` of the same customer for the same product can be deliberate.

## The three (or four) balances every account actually has

A single "account" exposes several balances, all projections of the same event stream:


| Balance                            | Definition                                     | When customer sees it               |
| ---------------------------------- | ---------------------------------------------- | ----------------------------------- |
| **Pending**                        | Auth holds applied, not yet cleared            | Card "pending" transactions         |
| **Available**                      | What the customer can spend right now          | The number on the app's home screen |
| **Settled**                        | What's actually cleared with the network       | What ends up in the statement       |
| **Committed** *(retail/inventory)* | Reserved for in-flight orders, not yet shipped | Distinguishes from on-hand          |


All three (or four) are projections off the same event stream — but you need them all, separately, and getting which-one-is-the-correct-answer wrong is a customer-trust bug. Banking is the most public example; e-commerce inventory has the structurally identical `onHand / committed / available-to-promise` triple (see `[../specific/ecommerce-and-retail.md](../specific/ecommerce-and-retail.md)`).

## The hot-account problem — when to leave ES

Fee accumulators, FX suspense accounts, exchange settlement accounts, treasury accounts, top-1% creators on a tipping platform — these single logical accounts can receive **thousands of writes per second**, which is way more than a single-stream optimistic-lock model can sustain.

Three escapes, in order of escalation:

1. **Shard the logical account.** `fee-accumulator-{shard 0..63}-{period}` with periodic roll-up into a summary account. Same pattern that solves hot SKUs in retail. Works while you have <100k writes/sec.
2. **Push the ledger primitive down.** Use TigerBeetle (or Square Books, or a sharded Postgres ledger) for the raw debits/credits, and keep ES at the *business event* layer above. The business event is "Trip Completed at fare $14.50"; the ledger entries that posting produces are a *projection* (or downstream consumer) of that event. Dudycz makes this argument: [Why a bank account is not the best example of Event Sourcing](https://event-driven.io/en/bank_account_event_sourcing/).
3. **Build / borrow a purpose-built primitive.** TigerBeetle was built for exactly this — millions of debits/credits per second, structurally enforced double-entry, no random-access random writes. The "is this ES?" question stops mattering; what matters is that the regulator-facing journal is intact.

## Closing the books — bounded streams over unbounded ledgers

A ledger account for an active corporate treasury runs forever and accumulates millions of entries. Replay-from-zero becomes impractical; storage grows linearly; the regulator wants snapshots.

**Closing the books** ([Dudycz](https://event-driven.io/en/closing_the_books_in_practice/)) is the universal answer: at a defined period boundary (monthly, quarterly, annually), emit `PeriodClosed{closingBalance, ...summary}`. Start a fresh stream `account-{id}-{nextPeriod}` opening with `PeriodOpened{openingBalance: previousClosingBalance}`. Old streams can be cold-archived without losing audit replay; the current period stream stays short and fast.

This is structurally the same as `inventory-{sku}-{warehouseId}-{quarter}` in retail or `subscription-{id}-{billingPeriod}` in SaaS billing. The trick is: **the closing-balance event seeds the next period as a fact, not a calculation**. You never have to replay 10 years of postings.

## Cash ledger ≠ revenue ledger (ASC 606 / IFRS 15)

This one is invisible until you have a finance team. **Money received** and **revenue recognised** are different ledgers running on different clocks.

A SaaS customer pays $1,200 upfront for a 12-month subscription. The *cash ledger* shows $1,200 received on day 1. The *revenue ledger* (under ASC 606 / IFRS 15) recognises $100/month over 12 months as the performance obligation is satisfied. A refund halfway through has different effects on each.

The cleanest design: **a separate `rev-rec-{subscriptionId}` stream** alongside the cash/invoice stream, with `RevenueScheduled{amount, asOf, performanceObligation}` and `RevenueRecognised{amount, period}` events. Stripe Sigma, Chargebee RevRec, Zuora RevPro, Recurly all expose this; they're structurally append-only because GAAP auditors require it ([Recurly ASC 606 guide](https://recurly.com/blog/asc-606-subscriptions/), [Zuora — Operationalizing ASC 606](https://www.zuora.com/guides/saas-accounting-standard/)).

The principle generalises: **any time "when we got the money" differs from "when we earned it", you have two ledgers, not one.** Same applies to ride-sharing (fare collected vs driver earnings recognised vs platform commission earned), insurance (premium received vs earned premium over policy period), advertising (impression delivered vs invoice raised vs payment received).

## Reconciliation — the internal/external truth boundary

Every real ledger has an *external* truth it must agree with: the card network's settlement file, the ACH return file, the PSP's daily reconciliation report, the bank-account statement, the carrier's delivery confirmation log.

The pattern is universal:

1. **Internal ledger** emits events optimistically as they happen.
2. **External truth** arrives later (T+1, T+2, end-of-day file).
3. A **reconciliation job** compares: missing on either side, mismatched amounts, late settlements, unexpected fees.
4. Discrepancies are themselves events: `ReconciliationDiscrepancyFound{...}`, `ReconciliationResolved{adjustment}`.
5. Resolution may produce an adjusting journal entry, an escalation to ops, or a `LossWrittenOff`.

Monzo's [Processing payments safely at scale](https://monzo.com/blog/2022/02/08/processing-payments-safely-at-scale) details this against their settlement account. The same pattern in ad-tech (publisher-reported impressions vs advertiser-reported clicks), in marketplaces (platform's view of GMV vs payment processor's view of capture), in insurance (claim paid vs reinsurer recovery).

**Anti-pattern:** treating reconciliation as "a script that runs at night and fixes things." Make every discrepancy an event; the auditor needs to see what was wrong and how it was fixed.

## Marketplace / multi-party settlement — the under-recognised ledger

Ride-sharing, food-delivery, freelance platforms, app stores — every transaction has **three or more parties**: customer, provider, platform, and often tip recipient, tax authority, payment processor.

The naïve model: one `Charge`, one `Payout`. The honest model: a balanced journal entry per transaction:

```
TripCompleted fare $14.50, tip $2.00
  -> JournalEntryPosted:
       debit  rider-payment-method     $16.50
       credit platform-commission       $3.50
       credit driver-earnings          $11.00
       credit driver-tip                $2.00
```

Each of those credits is itself an account that later participates in its own payout cycle. Driver earnings accumulate until weekly payout; platform commission rolls into a per-day P&L; tip is held separately for tax reasons.

`[../specific/ride-sharing-and-mobility.md](../specific/ride-sharing-and-mobility.md)` covers the canonical version. The pattern repeats across every two-sided platform — and is the single biggest reason marketplace teams should adopt Camp B (journal-as-truth) from day one.

## Non-money ledgers

The double-entry primitive works for any conserved quantity:

- **Loyalty / frequent-flyer miles** — Qantas's status-credit rollover at year-end is a structural `StatusYearClosed{rolledOverCredits, expiringCredits, newOpeningBalance}` event, identical to a banking period close.
- **Carbon credits / RECs** — each credit must be uniquely identified, transferred via balanced entries, and *retired* (a one-way debit to a "retired" account) — never destroyed.
- **Inventory units (serialised / lot-tracked)** — pharma, alcohol, firearms, jewellery — every unit's lifecycle is a chain of `Received → Allocated → Issued → ... → Retired/Sold/Disposed` postings.
- **API quota / rate-limit credits** — granted, consumed, refilled — same shape, different unit.
- **Game / virtual currency** — Hearthstone dust, Fortnite V-Bucks, in-app credits — the same multi-currency, idempotency, refund problems as real money, with even less tolerance for "lost" units.

If your system has a *conserved quantity* and *multiple parties holding balances of it*, you have a ledger. Adopt the conventions.

## Patterns that survive contact with production

- **Camp B from day one if you might ever need an audit.** Migrating from account-as-aggregate to journal-as-truth after the fact is brutal.
- **Every monetary event carries currency, amount, valueDate, occurredAt, idempotencyKey.** Five fields. If any are missing, you'll regret it within 18 months.
- **Three balance projections, not one.** Pending / available / settled. Make their definitions explicit and tested.
- **Compensation is a reversing entry, never an edit.** Convention: `*Reversed`, `*Adjusted`, `*CreditNote`, `*Refunded`. Never `*Undone` or `*Corrected` (implies the original is gone).
- **Period-close as the bound on unbounded streams.** `PeriodClosed{closingBalance}` seeds `PeriodOpened{openingBalance}` on the next stream.
- **Cash ledger and revenue ledger are different streams.** Don't conflate them under "billing".
- **Reconciliation discrepancies are events.** `ReconciliationDiscrepancyFound` + `ReconciliationResolved`. Not a script that silently fixes things.
- **For hot accounts, push to TigerBeetle or shard.** Don't argue with the optimistic-lock model — it loses at scale.

## Where to look in the cloned repos

- `**oskardudycz_EventSourcing.JVM/workshops/build-your-own-event-store/solved/src/test/java/bankaccounts/`** — the deliberately-minimal `BankAccount` aggregate. The intentional simplicity is the lesson: it shows what a *real* ledger has to add (multi-currency, holds, idempotency, journal entries).
- `**oskardudycz_EventSourcing.NetCore/Sample/HotelManagement/*`* — the `GuestStayAccount` is a live folio (open ledger); `Folio/Invoice` is the closed artefact. Two ledger shapes side-by-side.
- `**oskardudycz_EventSourcing.NetCore/Sample/ECommerce/**` — Payment as separate aggregate; refund as compensating event; reservation→capture lifecycle.

## Related docs

- `[../specific/banking-and-finance.md](../specific/banking-and-finance.md)` — the deep dive: account vs transfer vs journal vs statement, hot-account sharding, multi-currency, the Camp A / Camp B debate in full.
- `[../specific/long-running-subscriptions.md](../specific/long-running-subscriptions.md)` — billing-as-ledger, proration as a captured fact, ASC 606 rev-rec subledger, dunning state machine.
- `[../specific/ecommerce-and-retail.md](../specific/ecommerce-and-retail.md)` — payment lifecycle, refunds, store credit, loyalty points, inventory-as-non-money-ledger.
- `[../specific/ride-sharing-and-mobility.md](../specific/ride-sharing-and-mobility.md)` — marketplace multi-party settlement; fare adjustment as compensating ledger entry.
- `[sagas-and-multi-step-workflows.md](sagas-and-multi-step-workflows.md)` — the transfer saga, the dunning saga, the refund cascade all live there.
- `[unbounded-and-infinite-streams.md](unbounded-and-infinite-streams.md)` §D — lifetime ledger records (banking, insurance) and the period-sharding pattern.
- [Square — Books: an immutable double-entry accounting database service](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/) — canonical journal-as-truth case study.
- [Modern Treasury — How to Scale a Ledger Pt V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v) and [Designing Ledgers with Optimistic Locking](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking) — production engineering for SaaS-grade ledger APIs.
- [TigerBeetle docs](https://docs.tigerbeetle.com/single-page/) — when you've outgrown ES for the ledger primitive.
- [Oskar Dudycz — Why a bank account is not the best example of Event Sourcing](https://event-driven.io/en/bank_account_event_sourcing/) — the critique of the textbook example.

