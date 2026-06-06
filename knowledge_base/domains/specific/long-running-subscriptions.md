# Long-Running Subscriptions — Aggregate & Stream Decomposition

Aggregate boundaries, stream-id schemes, events, sagas, and gotchas from platforms that actually run subscription billing at scale: Stripe Billing, Chargebee, Recurly, Zuora, Paddle, plus operators that built it in-house (Netflix, Spotify, Disney+, telco postpaid, P&C insurance, frequent-flyer programs).

The textbook `Subscription{Created, Renewed, Cancelled}` survives until the second month in production. Then plan changes, pauses, dunning, gifting, trials, comp accounts, proration, tax, late processor webhooks, and revenue recognition each turn out to be their own state machine. A monthly subscription running ten years has 120+ renewal events; a Netflix account opened in 2009 with plan changes and household sharing has thousands. See [`../cross-cutting/unbounded-and-infinite-streams.md`](../cross-cutting/unbounded-and-infinite-streams.md) §D (lifetime records) for the archetype — this doc is the decomposition playbook.

## 1. Aggregate boundaries used in practice

Boundaries are driven by **lifecycle**, **contention with the payment processor**, **revenue-recognition audit scope**, and **the fact that billing periods close**.

| Aggregate | Why it's a boundary | Lifecycle |
|---|---|---|
| **Subscription** | The customer-facing contract. Long-lived but its *header* (plan, status, anchor) changes slowly. | Trial → Active → Past_Due → Cancelled → (Reactivated as new chapter) |
| **BillingPeriod / Invoice** | One stream per cycle — the canonical "closing the books" application. | Open → Finalised → Paid / Voided / Uncollectible |
| **Charge / PaymentAttempt** | One per attempt against the processor. Isolates PCI scope + the late/duplicate webhook problem. | Initiated → Succeeded / Failed / Disputed |
| **DunningCase** | Only exists during a failure window. Spawned on first failed charge; expires on recovery or write-off. | Opened → Retrying → Recovered / GivenUp |
| **PlanChange** | Saga aggregate for mid-cycle changes — captures proration as a fact, not a derived calculation. | Requested → Prorated → Applied / Rejected |
| **Entitlement** | What the subscriber CAN access right now. Usually a projection; its own aggregate when grant rules are independent of billing (comp, partner promos). | Granted → Revoked |
| **LoyaltyAccount** | Forever-running accumulator with period rollovers. Tier is a sub-aggregate so balance updates don't churn tier events. | Opened → … |
| **Mandate / PaymentMethod** | Customers rotate cards independently of the subscription. SCA / mandate state lives here. | Authorised → Active → Expired / Revoked |
| **Refund / CreditNote** | Distinct from the original invoice — issued days/months later, often partial. | Issued → Applied |
| **GiftSubscription** | Pre-redemption it has no subscriber; redemption creates the real Subscription. | Purchased → Redeemed → Consumed |

**The intuition** (Verraes / Vernon on aggregate sizing): a Subscription header changes 10–100× more slowly than billing periods, which change 10–100× more slowly than payment attempts under dunning. Different write frequencies → different aggregates. See `../README.md` heuristics.

## 2. Stream-id naming patterns

```
subscription-{subscriptionId}                           # lifetime header (slim)
subscription-{subscriptionId}-period-{yyyyMM}           # one per billing cycle
invoice-{invoiceId}
charge-{chargeId}                                       # one per processor attempt
dunning-{caseId}                                        # short-lived
plan-change-{changeId}                                  # saga stream
mandate-{mandateId}
entitlement-{customerId}-{productId}                    # rarely a stream; usually a projection
loyalty-{customerId}                                    # lifetime
loyalty-{customerId}-{year}                             # status-year close (FF programs)
gift-{giftId}
refund-{refundId}
revenue-recognition-{subscriptionId}-{yyyyMM}           # GAAP-side, separate from billing
```

Multi-tenant prefix: `tenant-{merchantId}.subscription-{id}` for billing platforms hosting many merchants on one event store.

**Period-sharded streams** are the load-bearing pattern — same as [`banking-and-finance.md`](banking-and-finance.md) §2. A subscription billing monthly since 2014 should not be one ever-growing stream — it's a thin lifetime header plus one short stream per period (`subscription-{id}-period-2026-05`), each terminated by `PeriodClosed{closingState}`. "Is the customer currently active?" reads the header; "what did we bill in May 2026?" reads one period stream. Old period streams cold-archive without losing audit replay.

## 3. Key events per aggregate

### Subscription (lifetime header — kept slim)

```
SubscriptionCreated     { subscriptionId, customerId, planId, currency, anchorDate, trialEnd?, createdAt }
TrialStarted / TrialConverted / TrialExpiredWithoutPay
PlanChanged             { fromPlanId, toPlanId, effectiveAt, planChangeId, prorationInvoiceId? }
QuantityChanged         { itemId, fromQty, toQty, effectiveAt }
AddonAdded / AddonRemoved
SubscriptionPaused      { pauseFrom, resumeAt?, behaviour: keep_as_draft|mark_uncollectible|void }
SubscriptionResumed
SubscriptionCancelled   { cancelAt, reason, cancelType: at_period_end|immediate, cancelledBy }
SubscriptionEnded                                                 # terminal — final period closed
PaymentMethodAttached / PaymentMethodDetached  { mandateId }
TaxLocationChanged      { fromJurisdiction, toJurisdiction, effectiveAt }   # affects all future periods
DiscountApplied         { couponId, percentOff|amountOff, duration: once|repeating|forever }
DiscountEnded           { couponId, reason: expired|removed|exhausted }
```

Stripe's [pause_collection](https://docs.stripe.com/billing/subscriptions/pause) and [Paddle's pause](https://developer.paddle.com/build/lifecycle/subscription-pause-resume) both keep pause as **state on the same subscription** — pause/resume invariants must enforce atomically. Cancellation distinguishes `at_period_end` (the common path — customer stays entitled through the period they paid for) from `immediate` (usually triggers a credit).

### BillingPeriod / Invoice (one stream per cycle)

```
PeriodOpened       { invoiceId, periodStart, periodEnd, billingDay,
                     planSnapshot, priceSnapshot, taxRateSnapshot,
                     carryForward: { unbilledUsage, creditBalance, prorationCredits } }
UsageRecorded      { quantity, meterId, occurredAt, idempotencyKey }
LineItemAdded      { lineId, amount, taxAmount, kind: recurring|usage|proration|addon|discount }
TaxComputed        { jurisdiction, rate, taxableBase, taxAmount, taxEngineRef }
InvoiceFinalised   { totalDue, dueDate }                         # invoice now immutable
InvoicePaid        { chargeId, paidAmount }
InvoiceMarkedUncollectible / InvoiceVoided  { reason }
CreditNoteIssued   { creditNoteId, amount, reason: refund|adjustment|service_credit }
PeriodClosed       { closingState: { paidAmount, outstandingAmount, carryForwardCredit, recognizedRevenue } }
```

**The hard rule** (Stripe, Chargebee, Recurly all enforce): once `InvoiceFinalised`, totals are frozen. Adjustments are *new* events — `CreditNoteIssued`, `RefundIssued` — never edits to prior line items. Same immutability discipline as the banking ledger.

### Charge (one per processor attempt)

```
ChargeInitiated   { chargeId, invoiceId, mandateId, amount, attemptNumber, idempotencyKey }
ChargeSucceeded   { processorChargeRef, fee }
ChargeFailed      { failureCode, failureType: soft|hard, networkAdvice }
ChargeRefunded    { refundId, amount, reason }
ChargeDisputed / ChargeDisputeWon / ChargeDisputeLost
```

Each *retry* during dunning is its own `Charge` aggregate — never a "PaymentAttempted2" event on the same charge. Same discipline as `Authorization` in banking ([`banking-and-finance.md`](banking-and-finance.md) §3).

### DunningCase (only exists during a failure window)

```
DunningCaseOpened       { caseId, invoiceId, firstFailureAt, strategy: smart_retries|fixed_schedule }
RetryScheduled / RetryAttempted   { attemptNumber, chargeId }
CustomerNotified        { channel: email|sms|push|in_app, template }
PaymentMethodUpdated    { newMandateId }
SubscriptionMovedToPastDue / SubscriptionMovedToUnpaid
DunningCaseRecovered    { recoveringChargeId }                   # terminal
DunningCaseGivenUp      { reason: max_attempts|merchant_action } # terminal → cancellation
```

[Stripe Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries) attempts up to 8 retries over ~2 months; [Chargebee Dunning](https://www.chargebee.com/docs/payments/2.0/dunning/dunning-v2) classifies decline codes into soft (retry) vs hard (require customer action) and runs separate schedules per class. Modelling each dunning case as its own aggregate keeps that policy churn contained.

### PlanChange (saga aggregate)

```
PlanChangeRequested     { changeId, fromPlanId, toPlanId, effectiveAt }
ProrationCalculated     { unusedTimeCredit, newTimeCharge, netDelta,
                          basis: { periodStart, periodEnd, changeMoment, oldPrice, newPrice, roundingMode } }
ProrationInvoiceCreated { invoiceId, totalDue } | ProrationDeferred
PlanChangeApplied | PlanChangeRejected  { reason }
```

Stripe's [proration model](https://docs.stripe.com/billing/subscriptions/prorations): credit unused time on the old price (negative line item) plus charge for remaining time on the new price (positive). Both land on the *next* invoice unless billed immediately. Capturing this as an explicit aggregate with `ProrationCalculated{...basis}` makes ASC 606 contract-modification reporting tractable — inputs as facts, not just outputs.

### LoyaltyAccount (forever-running, annual rollover)

```
PointsEarned       { qty, source: flight|stay|partner|promo, expiresOn? }
PointsRedeemed     { qty, againstAwardId }
PointsExpired      { qty, reason: lifetime_expiry|inactivity }
StatusCreditsEarned { qty, sourceRef }                            # separate counter from points
TierEvaluated      { evaluationPeriod, statusCreditsThisYear, attainedTier, previousTier }
TierGranted / TierLost
StatusYearClosed   { yearEndedAt, finalStatusCredits, rolledOverCredits, attainedTier }
```

Note the **double counter** (Qantas, AAdvantage, Hilton Honors): a *redeemable* points balance with multi-year expiry, plus a *status* counter that resets — sometimes partially rolls over — at each status-year close. Status year is a textbook close-the-books boundary. [Qantas (2026)](https://loyaltylobby.com/2026/02/26/qantas-frequent-flyer-program-changes-announced-for-2026/) lets members roll over up to 50% of unused status credits, capped per tier — that's `StatusYearClosed{rolledOverCredits: ...}` seeding the next year's stream.

## 4. Cross-aggregate sagas

Subscription billing hits three of the six saga families simultaneously: time-driven retry (renewal heartbeat, dunning), external-system integration (PSP webhooks), and compensation cascade (refunds, chargebacks). See [`../cross-cutting/sagas-and-multi-step-workflows.md`](../cross-cutting/sagas-and-multi-step-workflows.md) for the cross-domain map.

### 4.1 Renewal cycle (the heartbeat)

```
Scheduler: "subscriptions whose periodEnd == today"
  -> ClosePeriod                BillingPeriod: InvoiceFinalised, PeriodClosed{carryForward}
  -> OpenPeriod(carryForward)   BillingPeriod: PeriodOpened
  -> ChargeInvoice              Charge: ChargeInitiated -> ChargeSucceeded => InvoicePaid
                                                         OR ChargeFailed   => DunningCaseOpened
                                                                              SubscriptionMovedToPastDue
```

The Subscription header records *nothing* about a successful renewal — it's just another period closed. This keeps the header small over 10 years. The textbook anti-pattern of appending `RenewalProcessed` every month is how you end up replaying 120 events to answer "what plan are they on?".

### 4.2 Mid-cycle plan change with proration

```
ChangePlan(subId, newPlanId, prorationBehavior=create_prorations)
PlanChange:    PlanChangeRequested
  process manager reads current BillingPeriod for boundaries + price:
    unusedCredit = currentPrice * remaining_fraction
    newCharge    = newPrice     * remaining_fraction
PlanChange:    ProrationCalculated { ..., basis: {...} }
BillingPeriod: LineItemAdded x2 (negative credit + positive new charge)
PlanChange:    PlanChangeApplied
Subscription:  PlanChanged
```

**Why capture the calculation as an event, not derive it**: under ASC 606, a mid-term modification may need prospective treatment or cumulative catch-up. The auditor wants the *inputs* (period boundaries, prices, the moment of change) — not just the resulting credit.

### 4.3 Dunning saga (state machine over weeks)

```
ChargeFailed (renewal)
  -> DunningCaseOpened; SubscriptionMovedToPastDue; CustomerNotified

  loop (up to N attempts, schedule from smart-retry model):
    RetryScheduled -> wait -> RetryAttempted -> new Charge
      ChargeSucceeded -> DunningCaseRecovered; InvoicePaid
      ChargeFailed    -> CustomerNotified; continue

  exhaustion:
    DunningCaseGivenUp
    -> InvoiceMarkedUncollectible
    -> SubscriptionCancelled { reason: dunning_exhausted }
```

Retry policy, message templates, and notification cadence change frequently — keeping them inside DunningCase means the Subscription stream stays clean and auditable.

### 4.4 Cancellation with credit (immediate cancel)

```
CancelSubscription(type=immediate, refundUnused=true)
Subscription:  SubscriptionCancelled { cancelType: immediate, cancelAt: now }
  -> ClosePeriodEarly(asOf=now)
BillingPeriod: LineItemAdded { kind: proration, amount: -unusedCredit }
               PeriodClosed { carryForward: { creditBalance: unusedCredit } }
  -> IssueCreditNote   => CreditNoteIssued
  -> RefundCharge      => Charge.ChargeRefunded
Subscription:  SubscriptionEnded
```

Compare with `cancelType=at_period_end` (more common): `SubscriptionCancelled{cancelAt: periodEnd}` then nothing until the natural period boundary. No refund — customer keeps entitlement through what they paid for.

### 4.5 Reactivation / win-back — a new chapter, not a revival

A user who cancelled in 2023 and resubscribes in 2026 gets a **new** `subscription-{newId}` stream, linked to the old by `previousSubscriptionId` in `SubscriptionCreated`. **Do not** append `SubscriptionReactivated` to the dead aggregate:

- The old subscription is referenced by historical invoices, rev-rec records, dunning cases, disputes — reopening muddies all of that.
- Plan catalogue, prices, taxes, ToS have likely changed — it's a different commercial agreement.
- Cohort analytics ("2026 cohort or 2023 cohort?") want the join, not a single confusing stream.

Stripe's API enforces this: a fully cancelled subscription cannot be "resumed" — only `paused` can. `canceled` is terminal. Same pattern as `Order` → `Return` in [`ecommerce-and-retail.md`](ecommerce-and-retail.md): once a lifecycle has ended, post-end activity belongs to a sibling aggregate.

## 5. Projections

| Projection | Source | Used for |
|---|---|---|
| **Active subscribers / MAU** | `Subscription.*` headers | Login gate |
| **MRR / ARR** | `PlanChanged`, `Paused`, `Cancelled` + current price | Finance dashboard |
| **Churn cohort** | `SubscriptionCreated` joined with `SubscriptionEnded` | Retention curves |
| **Entitlement read model** | `Subscription`, `InvoicePaid`, `DiscountApplied` | Hot path — "can this user watch HD?" |
| **Dunning funnel** | `DunningCase.*` | Recovery rate by attempt #, by decline code |
| **Revenue recognition (ASC 606)** | `InvoiceFinalised`, `PlanChanged`, `CreditNoteIssued` | GAAP deferred-revenue waterfall |
| **Tax remittance** | `InvoiceFinalised{taxAmount, jurisdiction}` | Per-jurisdiction VAT / sales-tax filings |
| **Outstanding A/R** | `InvoiceFinalised` minus `InvoicePaid` / `Voided` / `Uncollectible` | Past-due aging |

The **entitlement read model** is the hot path — Netflix serves entitlement decisions millions of times per second, fed by Cassandra projections off the membership event stream ([InfoQ — Managing 238M memberships](https://www.infoq.com/articles/managing-memberships-netflix/)). Source of truth is the event log; entitlement table is denormalised and rebuildable.

## 6. Closing the books, applied to billing periods

The load-bearing pattern — direct lift from [`banking-and-finance.md`](banking-and-finance.md) §6 and Dudycz's [Closing the Books](https://event-driven.io/en/closing_the_books_in_practice/). Each `BillingPeriod` is a *short* stream:

```
PeriodOpened   { carryForward: { creditBalance, unbilledUsage, pendingProrations } }
... line items, discounts, tax, usage events ...
InvoiceFinalised
InvoicePaid     (or InvoiceMarkedUncollectible)
PeriodClosed   { closingState: { paidAmount, carryForwardCredit, recognizedRevenue } }
```

`PeriodClosed` of period N seeds `PeriodOpened` of period N+1. The closed period is immutable forever (audit-relevant) and tier-able to cold storage. Two killer benefits: (1) no 10-year replay — current-period stream is small; (2) period boundaries are real-world, not synthetic, aligned with what auditors / tax authorities / CS agents ask about. Recurly's [calendar billing](https://docs.recurly.com/recurly-subscriptions/docs/calendar-billing) and Stripe's [billing cycle anchor](https://docs.stripe.com/billing/subscriptions/billing-cycle) both lean into this.

## 7. Pause / freeze / hold — state, not a separate aggregate

Pause is **state on the Subscription** with a *policy field* declaring billing behaviour. Stripe's [pause_collection](https://docs.stripe.com/billing/subscriptions/pause) offers three:

| Policy | What happens during pause |
|---|---|
| `keep_as_draft` | Invoices generated but not finalised — billed retroactively on resume |
| `mark_uncollectible` | Invoices generated, immediately written off — pause is "free" |
| `void` | No invoices generated during pause window |

Gym freezes (Gymflow, 24 Hour Fitness), Netflix DVD pauses, and meal-kit "skip a week" all reduce to this. Resume re-enters the renewal saga at the chosen new anchor. Splitting pause into its own aggregate would force a saga where a single-aggregate decider suffices.

## 8. Late / out-of-order processor events

The single nastiest operational gotcha, and the reason `Charge` is its own aggregate. From [Stripe's docs](https://docs.stripe.com/webhooks): *"Stripe doesn't guarantee delivery of events in the order in which they're generated."* You can receive `charge.refunded` before `charge.succeeded`; a `payment_intent.succeeded` retry can arrive after `payment_intent.canceled`.

Mitigations:

1. **Per-event idempotency keys** — every handler dedupes on `event.id` before appending.
2. **Re-fetch the canonical object on critical decisions** — when ordering would change the outcome, call back to the processor API rather than trusting the (potentially stale) webhook payload.
3. **Charge aggregate is short-lived and version-locked** — optimistic concurrency rejects bogus transitions (no `ChargeRefunded` before `ChargeSucceeded`).
4. **Subscription-level decisions debounce** — a consumer updating entitlement off `ChargeSucceeded` should wait; a `ChargeRefunded` arriving 30s later is common when a customer self-refunds.

Compare with [`banking-and-finance.md`](banking-and-finance.md) §4.2 (auth → clear → settle): three real-world events arriving days apart get three separate aggregates linked by network reference. Same principle.

## 9. Revenue recognition vs cash — two different streams

The "cash-ledger ≠ revenue-ledger" split below is the canonical instance of the general pattern: any time *when we got the money* differs from *when we earned it*, you have two ledgers. See [`../cross-cutting/ledgers-and-double-entry.md`](../cross-cutting/ledgers-and-double-entry.md) for the cross-domain view (banking, marketplaces, insurance, ad-tech) and the universal ledger-design rules.

A subscription generates **two** parallel event streams:

| Stream | Fires when | Tracks |
|---|---|---|
| **Billing** (`invoice-*`, `charge-*`) | Money is billed / collected | Cash — A/R, dunning, tax remittance |
| **Revenue recognition** (`revenue-recognition-{subId}-{yyyyMM}`) | Customer *consumes* the service (typically straight-line) | GAAP — recognised revenue, deferred-revenue waterfall |

A customer billed $1,200 annually gets one `InvoicePaid{$1,200}` in January but twelve monthly `RevenueRecognised{$100}` events on the rev-rec stream. A mid-year plan change emits modification events that may trigger prospective vs cumulative-catch-up treatment.

This is the "**Cash Collected ≠ Revenue Earned**" reality every SaaS finance team learns. ASC 606 / IFRS 15 require the rev-rec stream because the obligation is satisfied over time, not at cash receipt. Recurly's [ASC 606 guide](https://recurly.com/blog/asc-606-subscriptions/), Zuora's [SaaS Accounting Standards](https://www.zuora.com/guides/saas-accounting-standard/), and Chargebee all expose a "revenue subledger" — structurally append-only because GAAP auditors require it.

Treating the two as separate aggregates means a billing correction (`CreditNoteIssued`) does not silently mutate recognised revenue — it emits a *new* `RevenueAdjusted` event with explicit treatment (cumulative catch-up vs prospective). Same discipline as the journal-stream camp in [`banking-and-finance.md`](banking-and-finance.md) §5.

## 10. Trial → paid, gifting, comp accounts

**Trial → paid.** A trial *is* a real subscription (so entitlement queries work) with `status: trialing` and no successful invoice yet. On `TrialConverted`, just `PeriodOpened` on the first billing period. If the trial card fails (`TrialExpiredWithoutPay`), the header gets a terminal event and the customer must resubscribe as a new chapter (§4.5).

**Gift subscriptions.** A separate `gift-{id}` aggregate lives independently before redemption — it has no subscriber yet:

```
GiftPurchased   { giftId, purchaserId, planId, durationMonths, code }
GiftRedeemed    { giftId, redeemedBy: customerId }
  -> SubscriptionCreated { source: gift, sourceRef: giftId, prepaidUntil: now+duration }
GiftConsumed
```

Gifts are often bought months before redemption and have their own purchase/refund rules — decoupled lifecycle is mandatory.

**Comp accounts (internal / partner / VIP)** look like normal subscriptions with a 100%-off coupon `forever` or a `price=0` plan. They go through the same event stream as paying subscriptions, with `CompGranted` carrying a justification — keeps MRR projections correct (excludes comps) without losing audit trail.

## 11. Real-world gotchas

1. **Proration rounding.** $9.99 / 30 × 17 = $5.66099… Some processors round per line, some per invoice. Capture `roundingMode` in `ProrationCalculated.basis` so cents are reproducible at audit time.
2. **Billing day TZ vs UTC.** A "1st of the month" anchor for Sydney is 23h ahead of Pacific. Store boundaries UTC, render in customer billing-day TZ. Drift causes the classic "billed twice in February" bug.
3. **Leap days / DST.** Feb 29 anchor on a non-leap year is undefined; Stripe falls back to Feb 28. Store the *fallback day actually used* on `PeriodOpened` so future cycles are deterministic.
4. **Webhook duplicates and out-of-order.** Stripe redelivers up to 3 days on 5xx; ordering isn't guaranteed. Always dedupe on `event.id` before appending. See §8.
5. **Payment-method rotation mid-cycle.** The new `mandate-{newId}` is what the next renewal uses; existing `DunningCase` picks it up. In-flight charges against the *old* mandate may still resolve — don't cancel eagerly.
6. **Card-less trials and email aliasing.** Without a captured card, `TrialExpiredWithoutPay` is a frequent terminal event — first-class outcome, not error. Trial abuse via `customer+1@` is detected by a separate fraud aggregate fed by fingerprint material on `SubscriptionCreated`.
7. **Tax jurisdiction changes.** Customer moves CA → TX in May. `TaxLocationChanged{effectiveAt}` so rev-rec and tax-remittance projections see the boundary.
8. **Coupon `duration: repeating(3 months)`.** Three discounted invoices then step-up. Without `DiscountEnded{reason: exhausted}`, the projection has no clean signal and customers churn on the surprise invoice.
9. **Refunds past the network window.** Card networks have ~120-day refund windows; after that, issue a credit note + customer-credit balance (`CreditApplied` against a future invoice), not `ChargeRefunded`.
10. **Comp / trial skew churn metrics.** Projections must filter by `source`. `TrialExpiredWithoutPay` is not "churn" in the same sense as `SubscriptionCancelled` from a paying customer.
11. **Family / bundle plans — multiple identities, one billing relationship.** Disney+/Hulu, Spotify Family, T-Mobile lines. One Subscription, N Entitlement records (household members). `MemberAdded` / `MemberRemoved` on the Subscription, not a new Subscription.
12. **Eligibility expiry independent of billing.** Spotify Premium Student requires 12-month re-verification; the clock ticks even if the customer pauses. `EligibilityReverificationRequired{by: date}` scheduled on creation; on miss, a saga emits `PlanChanged{toPlanId: standard_individual}`.
13. **Insurance endorsements.** A mid-term coverage change ("add a driver", "raise limits") is structurally a `PlanChange` — the premium delta is the proration. Emit `EndorsementIssued{documentRef, effectiveAt}` as the legal fact, recalculated premium separately on the billing side.
14. **Loyalty points liability is a balance-sheet item.** Airlines carry unredeemed miles as deferred revenue. The `LoyaltyAccount` stream IS the auditable source: `PointsEarned` increases liability, `PointsRedeemed` decreases it, `PointsExpired` recognises breakage revenue.

## 12. Sources & case studies

- **Stripe Billing** — [How subscriptions work](https://docs.stripe.com/billing/subscriptions/overview), [Prorations](https://docs.stripe.com/billing/subscriptions/prorations), [Billing cycle anchor](https://docs.stripe.com/billing/subscriptions/billing-cycle), [Pause collection](https://docs.stripe.com/billing/subscriptions/pause), [Smart Retries](https://docs.stripe.com/billing/revenue-recovery/smart-retries), [Webhooks](https://docs.stripe.com/webhooks).
- **Chargebee** — [Dunning v2](https://www.chargebee.com/docs/payments/2.0/dunning/dunning-v2); [subscription billing guide](https://www.chargebee.com/resources/guides/subscription-billing-and-management-guide/).
- **Recurly** — [Calendar billing](https://docs.recurly.com/recurly-subscriptions/docs/calendar-billing), [Usage-based billing](https://docs.recurly.com/docs/usage-based-billing), [ASC 606 subscriptions](https://recurly.com/blog/asc-606-subscriptions/).
- **Zuora** — [SaaS Accounting Standards: Operationalizing ASC 606](https://www.zuora.com/guides/saas-accounting-standard/). **Paddle** — [Pause / resume](https://developer.paddle.com/build/lifecycle/subscription-pause-resume).
- **Netflix** — [Managing 238M memberships (InfoQ)](https://www.infoq.com/articles/managing-memberships-netflix/); [ByteByteGo](https://blog.bytebytego.com/p/how-netflix-manages-238-million-memberships); [Billing & Payments Meetup](https://medium.com/netflix-techblog/billing-payments-engineering-meetup-ii-3bec782b3059). **Spotify** — [Premium Student re-verification](https://support.spotify.com/us/article/premium-student/). **Disney+/Hulu** — [account model](https://thewaltdisneycompany.com/news/hulu-disney-plus-profile-linking/).
- **Insurance** — [Policy lifecycle events (Finantrix)](https://www.finantrix.com/articles/what-is-a-policy-lifecycle-event-issuance-renewal-endorsement-cancellation); [AWS — Event-driven Insurance Policy Processing](https://aws.amazon.com/blogs/industries/insurtech-event-driven-insurance-policy-processing-approach/). **Telecom** — [Definitive guide to telecom billing (Encora)](https://www.encora.com/interface/a-definitive-guide-to-telecom-billing-systems).
- **Loyalty** — [Qantas FF 2026 rollover](https://loyaltylobby.com/2026/02/26/qantas-frequent-flyer-program-changes-announced-for-2026/); [Frequent-flyer program (Wikipedia)](https://en.wikipedia.org/wiki/Frequent-flyer_program); [American AAdvantage Loyalty Points](https://www.nerdwallet.com/travel/learn/american-airlines-revolutionizes-how-you-earn-aadvantage-elite-status).
- **Practitioner foundations** — Oskar Dudycz, [Closing the Books in Practice](https://event-driven.io/en/closing_the_books_in_practice/), [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/), [Slim your aggregates](https://event-driven.io/en/slim_your_entities_with_event_sourcing/); Mathias Verraes, [Summary Event pattern](https://verraes.net/2019/05/patterns-for-decoupling-distsys-summary-event/); Vaughn Vernon, [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf); Thoughtworks, [EDA in a billing system](https://www.thoughtworks.com/en-us/insights/blog/architecture/tackling-the-challenges-of-using-event-driven-architecture-in-a-billing-system).

## Cross-references

- [`../cross-cutting/unbounded-and-infinite-streams.md`](../cross-cutting/unbounded-and-infinite-streams.md) — archetype D (lifetime records); this file is the playbook.
- [`banking-and-finance.md`](banking-and-finance.md) — closing-the-books, journal-as-source-of-truth, dispute lifecycle separate from payment, period-sharded streams. The rev-rec stream in §9 is the ledger pattern again.
- [`ecommerce-and-retail.md`](ecommerce-and-retail.md) — Cart ≠ Order parallels Subscription ≠ BillingPeriod ≠ Invoice. Returns-as-separate-aggregate parallels Reactivation-as-new-chapter (§4.5).
- [`../../implementation-patterns/multi-aggregate-commands-and-sagas.md`](../../implementation-patterns/multi-aggregate-commands-and-sagas.md) — renewal, plan-change, dunning sagas all instantiate the patterns there.
- [`../../implementation-patterns/subscriber-failure-strategies.md`](../../implementation-patterns/subscriber-failure-strategies.md) — for processor-webhook subscribers requiring retry-with-idempotency.
- [`../../implementation-patterns/optimistic-concurrency.md`](../../implementation-patterns/optimistic-concurrency.md) — per-stream version locking on `Charge` and `DunningCase` makes out-of-order webhook ingestion safe.
