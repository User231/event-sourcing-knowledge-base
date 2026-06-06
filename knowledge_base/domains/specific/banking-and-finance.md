# Banking & Finance — Aggregate & Stream Decomposition

Practical aggregate / stream / event design lifted from real fintech writeups (Monzo, Square, Wise, Modern Treasury, Revolut, TigerBeetle) and the canonical ES authors (Verraes, Dudycz, Vernon). The textbook `BankAccount{Deposited/Withdrawn}` example breaks down the moment you hit 50k events/day on a hot account, multi-currency, or a regulator asking for replay.

## 1. Aggregate boundaries used in practice

Boundaries are chosen for **lifecycle**, **contention**, and **regulatory replay** — not just for data cohesion.

| Aggregate | Why it's a boundary | Lifecycle |
|---|---|---|
| **Customer / Party** | KYC state, regulatory identity, slow-changing. Separate so account churn doesn't bloat compliance replay. PII handling under multi-year retention is the classic GDPR-vs-immutability tension — see [`../cross-cutting/compliance-pii-and-immutability.md`](../cross-cutting/compliance-pii-and-immutability.md). | Onboard → Verified → Suspended → Closed |
| **Account** (current / savings / wallet) | Per-account optimistic concurrency, balance invariant. One stream per `accountId`. | Opened → Active → Frozen → Closed |
| **Card** | Distinct lifecycle from the funding account (issued, activated, lost, replaced). PIN/PAN scope. | Issued → Activated → Blocked → Reissued |
| **Authorization / Hold** | Short-lived, expires. Separate from the long-lived Account stream so auth retries don't pollute account history. Structurally the same reservation pattern as hotel rooms, e-commerce stock, and event tickets — see [`../cross-cutting/reservations-and-finite-resources.md`](../cross-cutting/reservations-and-finite-resources.md). | Requested → Approved → Captured → Expired/Reversed |
| **Transfer / Payment** | The canonical saga aggregate. Each transfer has its own stream with start/end markers. | Initiated → Debited → Credited → Settled / Reversed |
| **LedgerEntry / JournalEntry** | The double-entry primitive. Often a *separate* append-only journal stream, not nested inside accounts. | Posted (immutable) |
| **Loan** | Origination + servicing + repayment schedule. Long-lived but bounded by repayment periods. | Originated → Disbursed → Servicing → Paid Off / Defaulted |
| **Statement / Period** | The "closing the books" aggregate — finalises a billing period and emits opening balance for the next. | Opened → Closed (`PeriodClosed`) |
| **Mandate / Standing Order** | Separate from each scheduled payment instance. | Created → Active → Cancelled |
| **Dispute / Chargeback** | Distinct workflow from the original payment; references but does not mutate it. | Filed → Investigated → Upheld / Rejected |

**Rule of thumb** (Vaughn Vernon, [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf)): one transactional consistency boundary per aggregate. A transfer touching two accounts is therefore *never* one aggregate — it's a process across three (Transfer + 2 × Account).

## 2. Stream-id naming patterns

```
customer-{customerId}
account-{accountId}                          # one stream per account
account-{accountId}-{yyyyMM}                 # period-sharded for high-throughput
card-{cardId}
auth-{authorizationId}                       # short-lived
transfer-{transferId}                        # saga / process manager stream
loan-{loanId}
ledger-{accountId}-{period}                  # period-bucketed journal per account
journal-{ledgerId}-{yyyyMMdd}                # global journal sharded by day
statement-{accountId}-{period}
mandate-{mandateId}
dispute-{disputeId}
```

**One stream per account** is the default. Each account stream gives free optimistic concurrency (`expectedVersion`) and clean aggregate-boundary alignment ([Albert Llousas — Exploring event sourcing: A scalable bank account](https://medium.com/@allousas/exploring-event-sourcing-a-scalable-bank-account-19b9d55302e0)).

**Period-sharded streams** (`account-{id}-2026-05`) appear once accounts get long-lived or hot. Oskar Dudycz's [Closing the Books](https://event-driven.io/en/closing_the_books_in_practice/) is the canonical pattern: each period is its own short stream that opens with `PeriodOpened{openingBalance}` and ends with `PeriodClosed{closingBalance}`. The next period starts fresh — you never replay 10 years of transactions to compute today's balance. See also Verraes's [Summary Event pattern](https://verraes.net/2019/05/patterns-for-decoupling-distsys-summary-event/).

**High-contention accounts** (fee accumulators, suspense, exchange settlement, treasury) need explicit sharding:
- shard by time bucket: `fees-{merchantId}-{yyyyMMddHH}`
- shard by counterparty: `suspense-{currency}-{shard}`
- model the "logical" account as a sum across many physical streams (a projection problem, not a write-path problem)

This is exactly why TigerBeetle treats accounts as flat numeric primitives rather than ES aggregates ([TigerBeetle docs](https://docs.tigerbeetle.com/single-page/)) — for hot accounts the per-stream lock becomes the bottleneck. Dudycz makes the same critique in [Why a bank account is not the best example of Event Sourcing](https://event-driven.io/en/bank_account_event_sourcing/): "active trading accounts generate up to 50,000 events per day".

## 3. Key events per aggregate

### Account (current / wallet)
```
AccountOpened          { accountId, customerId, currency, productType, openedAt }
DepositRecorded        { amount, currency, valueDate, source, txId, idempotencyKey }
WithdrawalAuthorized   { amount, currency, holdId, expiresAt, txId }
WithdrawalPosted       { amount, currency, valueDate, holdId, txId }
WithdrawalReleased     { holdId, reason }              # hold expired / cancelled
OverdraftLimitChanged  { previousLimit, newLimit, effectiveFrom, approvedBy }
InterestAccrued        { amount, currency, periodFrom, periodTo, rate }
FeeCharged             { amount, currency, feeType, ref }
AccountFrozen          { reason, frozenBy, scope }     # partial vs full
AccountClosed          { closingBalance, finalDisposition, closedAt }
```
Note the **`valueDate`** distinct from event timestamp — events are recorded when they happened in the system, but settlement and interest accrual run on `valueDate`. See [Verraes — Practical Event Sourcing](https://verraes.net/2014/03/practical-event-sourcing/).

### Card
```
CardIssued        { cardId, accountId, pan, expiry, scheme, issuedAt }
CardActivated     { activatedAt, channel }
PinSet            { pinHashRef, setAt }
CardBlocked       { reason }                            # lost / stolen / fraud / customer
CardUnblocked     { unblockedBy }
CardReplaced      { replacementCardId, reason }
CardExpired       { expiredAt }
ContactlessLimitChanged { previousLimit, newLimit }
```

### Authorization (short-lived aggregate, per card-network message)
```
AuthorizationRequested  { authId, cardId, merchantId, mcc, amount, currency, fxRate }
AuthorizationApproved   { authId, holdAmount, availableBalanceAfter }
AuthorizationDeclined   { authId, declineCode, reason }    # 51 = insufficient funds etc.
AuthorizationReversed   { authId, reversedAmount, reason } # partial reversals exist
AuthorizationCleared    { authId, clearingAmount, settlementDate, networkRef }
AuthorizationExpired    { authId, expiredAt }              # never cleared within 7-30d
```

### Transfer (the saga aggregate)
```
TransferInitiated     { transferId, fromAccountId, toAccountId, amount, currency, rail }
TransferValidated     { transferId, complianceChecksRef }
SourceDebitPosted     { transferId, ledgerEntryId }
DestinationCreditPosted { transferId, ledgerEntryId }
TransferCompleted     { transferId, completedAt }
TransferFailed        { transferId, failedStep, reason }
TransferReversed      { transferId, reversingEntryRef, reason }
ChargebackFiled       { transferId, disputeId, filedAt }
```

### LedgerEntry / Journal (immutable double-entry primitive)
```
JournalEntryPosted    {
  entryId, postedAt, valueDate,
  debits:  [{ accountId, amount, currency }],
  credits: [{ accountId, amount, currency }],
  reference, txId, originatingEvent
}
ReversingEntryPosted  { reversesEntryId, reason, postedAt }
```
Every `JournalEntryPosted` must satisfy `sum(debits) == sum(credits)` per currency. Modern Treasury enforces this at the API layer ([Designing the Ledgers API with Concurrency Control](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking)).

### Loan
```
LoanApplicationApproved   { loanId, principal, currency, rate, term, schedule }
LoanDisbursed             { loanId, disbursedAmount, toAccountId, disbursedAt }
RepaymentScheduled        { installmentId, dueDate, principal, interest }
RepaymentReceived         { installmentId, receivedAmount, allocatedPrincipal, allocatedInterest, allocatedFees }
RepaymentMissed           { installmentId, missedAt }
LoanRescheduled           { newSchedule, reason }
LoanWrittenOff            { residualBalance, writtenOffAt }
LoanPaidOff               { paidOffAt }
```
See Temenos [Lending Events Lifecycle Guide](https://developer.temenos.com/article/lending-events-lifecycle-guide).

## 4. Cross-aggregate processes / sagas

The Transfer saga below is *the* textbook event-sourcing saga — referenced by every other domain doc in this directory. For the cross-domain landscape (which industries run which saga families, the universal compensation playbook, idempotency keying strategies, workflow-engine vs aggregate-native trade-offs), see [`../cross-cutting/sagas-and-multi-step-workflows.md`](../cross-cutting/sagas-and-multi-step-workflows.md).

### 4.1 Money transfer between two accounts (the canonical saga)

```
Command: InitiateTransfer(fromAcct, toAcct, amount, currency)
                                      |
Transfer aggregate                    v
  emits TransferInitiated
                                      |
Process manager listens               v
  -> Command: AuthorizeDebit(fromAcct, amount, transferId)
Account(fromAcct)
  emits WithdrawalAuthorized          # optimistic lock on stream
                                      |
                                      v
  -> Command: PostCredit(toAcct, amount, transferId)
Account(toAcct)
  emits DepositRecorded
                                      |
                                      v
  -> Command: PostDebit(fromAcct, transferId)
Account(fromAcct)
  emits WithdrawalPosted
                                      |
                                      v
Transfer aggregate
  emits TransferCompleted
  + JournalEntryPosted { debit: fromAcct, credit: toAcct }
```

**Compensation:** if `PostCredit` fails, the process manager emits `ReleaseHold` on `fromAcct` (`WithdrawalReleased`) and `TransferFailed` on the Transfer aggregate. We never delete `WithdrawalAuthorized` — that's the whole point of immutability. See [Proto.Actor — Money Transfer Saga](https://proto.actor/docs/money-transfer-saga/) and Dudycz, [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/).

### 4.2 Card authorization → clearing → settlement

These are *three* different real-world events arriving days apart over different rails — model as three separate aggregates linked by `networkRef`:

```
T+0   AuthorizationRequested -> AuthorizationApproved       # online, ~200ms
      => Account: WithdrawalAuthorized (hold on available balance)

T+1d  AuthorizationCleared                                  # batch file from scheme
      => Account: WithdrawalPosted (real debit), hold released
      => JournalEntryPosted

T+2d  Settlement file reconciles network -> issuer cash     # Monzo: settlement account
      => JournalEntryPosted: debit settlement, credit network suspense
```
See [Monzo — Processing payments safely at scale](https://monzo.com/blog/2022/02/08/processing-payments-safely-at-scale) on reconciling internal ledger against the settlement account.

### 4.3 SEPA / ACH batch flow

Batch rails arrive as *files*, not single transactions:

```
BatchFileReceived            { fileId, scheme, count, hash }
  -> for each item: PaymentExtracted { paymentId, ... }
       -> Transfer aggregate per payment item
PaymentReturned              { paymentId, returnCode, reason }   # R01 insufficient, R03 no account, etc.
  -> emits ReversingEntryPosted against the original credit
BatchSettled                 { fileId, settledAt, settlementRef }
```
Return windows are long (ACH R10/R11 unauthorized can come back 60 days later), so the original `PaymentPosted` event must never be mutated — only `PaymentReversed` appended.

### 4.4 Fraud hold

```
FraudSignalRaised (Risk service)
  -> Command: FreezeAccount(accountId, scope=outgoing)
Account emits AccountFrozen { scope: 'outgoing', reason: 'fraud_review' }
  # subsequent WithdrawalAuthorized commands rejected by aggregate invariant
FraudCleared
  -> Command: UnfreezeAccount(accountId)
Account emits AccountUnfrozen
```

## 5. Double-entry ledger treatment

The Camp A / Camp B choice below applies to any domain with multi-party value-conserving transactions — see [`../cross-cutting/ledgers-and-double-entry.md`](../cross-cutting/ledgers-and-double-entry.md) for the cross-domain treatment (marketplace settlement, subscription rev-rec, loyalty points, hot-account escapes, the universal multi-currency / value-date / idempotency triple).

Two camps in event-sourced banking:

**Camp A — Ledger entries embedded in account streams.** Each account stream contains its half of the transaction (`DepositRecorded` on one, `WithdrawalPosted` on the other). Balance = projection over the stream. Simple, but cross-account reconciliation requires joining N streams, and double-entry invariants are *enforced by convention* rather than structurally.

**Camp B — Separate journal stream as source of truth.** A single `journal-*` append-only stream holds `JournalEntryPosted{debits[], credits[]}`. Account streams become *projections* of the journal. This is how **Square's Books** ([blog](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/)), **Modern Treasury Ledgers** ([How to Scale a Ledger Pt V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v)), and **TigerBeetle** all work.

Why Camp B wins for serious finance:
- The journal *is* the regulatory record. `debits == credits` is structural.
- Reversal is a new `ReversingEntryPosted` referencing the original — never mutation.
- You can reproject account balances any way you want (pending vs available vs settled, per currency).
- Audit replay is literally re-reading one stream.

Square's [Books post](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/): "both journal and book entries data sets are effectively append-only and immutable once stored. Besides the books table, there are no update statements — only inserts. If you make a mistake, you write a new entry that corrects the previous one rather than updating in place."

## 6. Real-world gotchas

**High-contention accounts.** Fee accumulators, FX suspense, exchange settlement, treasury accounts can receive thousands of writes/sec — way more than a single-stream optimistic-lock model can sustain. Solutions: shard the logical account into many physical streams, or push the ledger primitive down to a purpose-built engine (TigerBeetle) and keep ES at the *business event* layer above.

**Long streams.** A 5-year-old account replayed event-by-event is slow. Two fixes:
- **Snapshots** — periodic state cache; replay from there. Cheap but doesn't shorten history.
- **Closing the Books / Summary Events** — start a new stream per period, opened by a `PeriodOpened{openingBalance}` carrying forward the summary. Old streams can be cold-archived without losing audit replay.

**Retroactive corrections.** *Never mutate past events.* If a fee was wrongly charged in March and you discover it in May, you emit `ReversingEntryPosted{reverses: originalEntryId, reason}` in May with a `valueDate` of March. Reports must distinguish between **event time** and **value date**.

**Regulatory replay / audit.** The ledger stream is the auditable record. Keep schema evolution disciplined: events are versioned, never deleted, never reshaped. Most fintech regulators want 5-7-10 year retention — plan your archive tier accordingly. See Kurrent's [Finance use cases](https://www.kurrent.io/use-cases/finance).

**Multi-currency.** Every event with `amount` must carry `currency`. Balances are *per currency* — never sum across currencies without an explicit FX event. Each posting in `JournalEntryPosted` carries its own currency; an FX trade is a balanced journal entry with debits in one currency and credits in another *plus* an explicit `FXRateApplied` event capturing the rate used. See [SDK.finance — Multi-currency ledger](https://sdk.finance/blog/what-is-a-multi-currency-ledger-how-fintechs-track-balances-transfers-and-settlement-across-currencies/).

**Idempotency.** Every command into an account aggregate must carry an `idempotencyKey`. The aggregate (or a dedup table fed by a projection) rejects duplicates. Monzo's payment-processing post stresses this — the same payment instruction may arrive twice from upstream rails and the ledger must remain balanced.

**Pending vs available vs settled.** A single account has at least three balance projections: pending (auth holds applied), available (what the customer can spend), settled (what's actually cleared with the network). All three are projections off the same event stream — but you need them all, separately.

## 7. Sources & case studies

- **Monzo** — [Processing payments safely at scale](https://monzo.com/blog/2022/02/08/processing-payments-safely-at-scale); [Modern Banking in 1500 Microservices, InfoQ](https://www.infoq.com/presentations/monzo-microservices/).
- **Square / Block** — [Books: an immutable double-entry accounting database service](https://developer.squareup.com/blog/books-an-immutable-double-entry-accounting-database-service/).
- **Modern Treasury** — [How to Scale a Ledger Pt V](https://www.moderntreasury.com/journal/how-to-scale-a-ledger-part-v); [Designing the Ledgers API with Optimistic Locking](https://www.moderntreasury.com/journal/designing-ledgers-with-optimistic-locking); [Ledger Event Handlers](https://www.moderntreasury.com/journal/announcing-ledger-event-handlers).
- **Revolut** — [Architecture of a Neobank](https://news.abnasia.org/blog/posts/en-architecture-of-a-neobank-revolut-3689) (in-house event store on Postgres, per-aggregate version, no Kafka).
- **Wise** — [System Design overview](https://www.systemdesignhandbook.com/guides/wise-system-design-interview/).
- **TigerBeetle** — [docs](https://docs.tigerbeetle.com/single-page/) — purpose-built debits/credits primitive when ES streams aren't fast enough.
- **Kurrent / EventStoreDB** — [Finance use cases](https://www.kurrent.io/use-cases/finance).
- **Oskar Dudycz** — [Why a bank account is not the best example of Event Sourcing](https://event-driven.io/en/bank_account_event_sourcing/), [Closing the Books in Practice](https://event-driven.io/en/closing_the_books_in_practice/), [Saga and Process Manager](https://event-driven.io/en/saga_process_manager_distributed_transactions/), [Building your own Ledger Database](https://www.architecture-weekly.com/p/building-your-own-ledger-database).
- **Mathias Verraes** — [Practical Event Sourcing](https://verraes.net/2014/03/practical-event-sourcing/), [Summary Event pattern](https://verraes.net/2019/05/patterns-for-decoupling-distsys-summary-event/).
- **Vaughn Vernon** — [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf).
- **Temenos** — [Lending Events Lifecycle Guide](https://developer.temenos.com/article/lending-events-lifecycle-guide); **Mambu** — [Loan Account Life Cycle and States](https://docs.mambu.com/docs/loan-account-life-cycle-and-states/).

## Local code references

- `repos_cloned/oskardudycz_EventSourcing.JVM/workshops/build-your-own-event-store/solved/src/test/java/bankaccounts/` — minimal `BankAccount` aggregate with sealed event interface; useful as a starting template. The intentional simplicity highlights what a *real* banking system would need to add (multi-currency, holds, idempotency, ledger entries).
