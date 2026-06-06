# Compliance, PII & the Immutability Tension

The defining promise of event sourcing — *the log is forever, you never edit, you never delete* — collides head-on with the defining promise of modern privacy law: *the data subject can demand erasure, and you must comply within 30 days*. GDPR Article 17, CCPA §1798.105, LGPD Art. 18, APPI's deletion provisions, HIPAA's right to amend, even Schrems II's *cross-border restrictions* — every one of them assumes that data **can be removed**. Your event store assumes it can't.

This doc inventories how every transactional domain in `specific/` lives with that tension, the four real strategies, and the regulatory regimes (GDPR, HIPAA, PCI-DSS, SOX, KYC/AML, Schrems II) that drive them. It's the meta-pattern referenced in passing by [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md), [`../specific/multi-region-replication.md`](../specific/multi-region-replication.md), [`../specific/chat-and-messaging.md`](../specific/chat-and-messaging.md), [`../specific/social-feeds.md`](../specific/social-feeds.md), [`../specific/federated-systems.md`](../specific/federated-systems.md), and [`../specific/banking-and-finance.md`](../specific/banking-and-finance.md) — pulled into one place.

## The regulatory regimes that actually matter

| Regime | Jurisdiction | What it requires | Where it bites event-sourced systems |
|---|---|---|---|
| **GDPR** Art. 17 | EU | Right to erasure within 30 days | Every PII-bearing event, every replica, every CDC consumer, every projection, every cold archive |
| **CCPA / CPRA** §1798.105 | California | Right to delete | Same; slightly looser exemptions for ongoing contractual obligation |
| **LGPD** Art. 18 | Brazil | Erasure within 15 days | Same |
| **HIPAA** §164.526 | US healthcare | Right to *amend* (not delete) PHI | Adjusting (not deleting) past clinical facts; 6-year retention floor conflicts with erasure |
| **PCI-DSS** | Global payment cards | No PAN, CVV, full track data after authorisation | The auth event must not carry the PAN — store tokens, not card numbers |
| **SOX** §404, §802 | US public companies | 7-year financial-record retention | The journal *cannot* be deleted; tension with PII inside financial records |
| **SEC 17a-4** | US broker-dealers | WORM 6-year+ for trade records | Append-only storage hardware, ironically a *good* fit for ES |
| **KYC / AML** (BSA, AMLD6, etc.) | Banking | Verified-identity records for 5-7-10 years post-relationship | Identity is PII; relationship close ≠ erasure; right-to-erasure does *not* override AML retention |
| **Schrems II** | EU↔US transfers | EU PII can't flow to jurisdictions where intelligence services have lawful access | Event replication topology becomes a legal question |
| **MiCA, MiFID II** | EU markets | Record-keeping for trade, comms | Multi-year retention with PII inside |
| **Common Carrier / FCC / Ofcom** | Telecom | Recording, CALEA, lawful intercept | Some events *must* be retained even when subject objects |
| **Records-management statutes** (state/civic) | Court, land, vital records | Forever-retention with public-record exceptions | Land titles, court cases — the strongest "events are forever, period" domains |

The first rule: **erasure obligations don't trump retention obligations**. KYC records for a closed account survive an erasure request because AML law requires them. The bank doesn't choose; the statute does. This is why financial systems often segment PII from financial-fact events and erase only the former.

## Where PII appears in event-sourced systems

| Where | Example payload fields | Risk class |
|---|---|---|
| **Aggregate identifiers** | `customerId`, `accountId`, `userId` — often UUIDs (low risk) but sometimes natural keys (email, phone, SSN — high risk) | The hardest to erase; ids appear in every downstream event |
| **Event payloads** | name, email, address, DOB, IP, geolocation, device id, payment instrument, health data | The classic target of an erasure request |
| **Metadata / headers** | actor identity, IP, user-agent, trace context | Often overlooked; "system" metadata is usually still PII under GDPR |
| **Foreign refs** | `BCOM/{externalGuestId}` in hotel OTA integrations; `stripe_customer_id`; carrier tracking numbers | Identifiers issued *by other systems* — erasing your side doesn't erase theirs |
| **Projections / read models** | denormalised tables holding cached PII | Erasure must fan out; rebuilds must not re-introduce |
| **Caches, queues, message brokers** | Kafka topics, Redis, RabbitMQ DLQ | Often missed in the first audit |
| **Logs, traces, error reports** | Sentry, Datadog logs, accidentally-logged request bodies | The single most common PII leakage path |
| **Backups / cold archive** | S3 Glacier, Azure Archive, tape | Restoring an old backup must NOT resurrect erased data — design for it |

The blast radius of an erasure request is typically 3–10× larger than teams initially estimate.

## The four strategies — what each one actually buys you

### 1. Crypto-shredding (the practitioner default)

Encrypt every PII field with a **per-subject key** (one key per data subject). Store ciphertext in events; store the key in a separate keystore. When the subject requests erasure, **delete the key**. Ciphertext remains structurally intact; it's permanently unreadable.

- Event structure stays valid (no schema breakage, no DAG/chain disruption).
- Works across replicas, CDC consumers, archives, backups — they all hold ciphertext.
- Audit replay works for *non-PII* logic; PII-dependent projections see redacted fields.
- Recognised by EU data-protection authorities as effective erasure ([HashiCorp Vault — GDPR-Compliant Event Sourcing](https://www.hashicorp.com/en/resources/gdpr-compliant-event-sourcing-with-hashicorp-vault); see [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) for the canonical worked example).

**Caveats:**
- **Regulators may still consider encrypted PII to be PII.** Until the key is destroyed, you hold the data; some auditors apply pre-deletion controls to ciphertext too.
- **Key management is now a hard system.** Per-subject keys at scale (10M+ subjects) need HSM-backed rotation, audit, regional residency, recovery procedures.
- **You cannot ever "un-shred".** No customer-success recovery, no "actually they asked us to restore." Once gone, gone.
- **Algorithm migration** is a problem: AES-128 to AES-256 to post-quantum. Need to re-encrypt before the old algorithm becomes vulnerable, or accept that crypto-shredding by old algo is theoretically reversible after Q-day.

### 2. Tombstoning (the messaging default)

The PII-bearing event stays in the log with its identifier, sender, and DAG/position intact. The **payload is scrubbed** to a placeholder. A new event — `PostTombstoned`, `MessageRedacted`, `UserDeleted{mode: tombstone}` — is appended marking the redaction.

- Matrix's [`m.room.redaction`](https://spec.matrix.org/v1.6/client-server-api/#redactions) strips content but leaves event-ID, sender, DAG position so the room's hash-chain stays valid — the cleanest production example. See [`../specific/chat-and-messaging.md`](../specific/chat-and-messaging.md).
- Social-feed equivalent: `PostTombstoned{postId, reason}` with the projection rendering `[content removed]`.
- **Cheaper key-management story** (no per-subject keys), more invasive event structure (you do edit the payload).

**Caveats:**
- **Editing a payload breaks signature chains.** If events are signed (federated systems, blockchain, audit-grade ES), you can't tombstone without re-signing — which means the original signer must cooperate (rarely possible if it's the customer being erased).
- **Tombstones don't shrink storage** — every tombstone is another append. Reclamation happens via retention-driven bucket truncation.
- **The legal distinction between "user can no longer see it" (projection-level redact) and "the bits are gone" (storage-level scrub) is significant** — model and document both.

### 3. PII tokenisation (external vault)

Events store **tokens**; a separate vault (HashiCorp Vault, AWS Macie, Skyflow, an in-house "Identity Service") resolves tokens to values. Erasure means returning null for the token forever after.

- Clean separation: events become genuinely PII-free.
- Same vault can serve projections, exports, BI, analytics.
- Often combined with crypto-shredding — vault holds ciphertext + key.

**Caveats:**
- **Token vault is now a single point of failure** for every PII-bearing read.
- **Joins become RPC calls** — analytics that need PII run slower or pre-resolve into a region-pinned read model.
- **External systems get the token, not the value.** Stripe customer ids, OTA reservation ids — if the integration needs a real email, you have to resolve before sending and re-tokenise on return. Easy to leak through this seam.

### 4. Stream rewrite (the nuclear option)

Copy the entire stream minus PII events, throw away the old stream. Only acceptable when **you control every subscriber and every downstream consumer**. In practice that's:
- Internal greenfield systems with no CDC.
- Pre-launch / pre-replication systems.
- Self-hosted blockchain forks (very rare).

Almost never the right answer at scale. Included for completeness because some teams will discover the painful way that none of (1)–(3) was set up in advance, and rewrite is the only path left.

| Strategy | Schema survives | Hash/sig survives | Backups handled | Federation/replication handled | Operational cost |
|---|---|---|---|---|---|
| **Crypto-shred** | ✓ | ✓ | ✓ (ciphertext) | ✓ (ciphertext) | Key management = ongoing |
| **Tombstone** | partial (payload changes) | ✗ if signed | ✓ if propagated | Advisory only in federation | Lower steady-state, higher per-erasure |
| **Tokenise** | ✓ | ✓ | ✓ (tokens) | ✓ (tokens) | Vault = ongoing |
| **Rewrite** | ✗ | ✗ | requires re-shipping | impossible in federation | One-time but catastrophic |

The production default for most ES teams: **crypto-shred for free-text and identity fields; tokenise for structured PII that needs frequent use; tombstone for federated/distributed content; rewrite never.**

## The "advisory delete" problem in federated and distributed systems

A signed event forwarded to N servers can be *requested* to be deleted; deletion cannot be *enforced*. This is the operational shape of GDPR vs an immutable signed event store across jurisdictions you don't control:

- **Mastodon / ActivityPub** — a `Delete` activity is fanned out. Each receiving instance is supposed to honour it; a non-cooperating instance keeps the post. Several admins have documented month-long "tombstone storms" after a popular account deletes — the deletion fans out to thousands of servers, each chewing through stored posts. See [`../specific/federated-systems.md`](../specific/federated-systems.md).
- **Matrix** — `m.room.redaction` is sent to participating homeservers; those that aren't online when it arrives apply it later. A server that refuses to apply redactions is operating outside the spec.
- **Git / version control** — `git filter-repo` rewrites history on the local copy; **every clone in the wild still has the old history**. Practically equivalent to crypto-shredding via reflog expiry, except secrets pushed to GitHub also need a credential rotation.
- **Blockchain** — deletion is structurally impossible. The only answers are crypto-shredding pre-publication, zero-knowledge proofs (zkSNARKs / zkSTARKs), and shielded pools (Tornado Cash, Zcash, Aztec). See [`../specific/smart-contracts-and-blockchain.md`](../specific/smart-contracts-and-blockchain.md).

**Practical posture:** in federated/distributed systems, erasure is **advisory and best-effort**. Make the request, propagate to cooperating peers, log non-compliance, and architect to *minimise PII inclusion in federated events in the first place* — the strongest defence against "right to erasure across a system you don't fully own" is to never put PII into that system to begin with.

## Multi-region: data residency before erasure

Cross-region deployments add a layer above all of the above: **the event itself may not be allowed to leave the home jurisdiction**.

- **Schrems II** (2020) invalidated the EU-US Privacy Shield. EU personal data flowing to the US must demonstrate the destination jurisdiction provides equivalent protection — and the bar is "would the destination's intelligence services have lawful access?" Practically: most US destinations fail without additional contractual / technical safeguards.
- **SCCs + supplementary measures** are the legal vehicle. Technical safeguards include encryption-in-transit/at-rest with key-in-home-region (so encrypted bytes can transit but cannot be decrypted at destination).

Three architectural shapes ([`../specific/multi-region-replication.md`](../specific/multi-region-replication.md) §9):

1. **Strict partitioning** — EU events live in EU stores, replicated only to EU. Cross-jurisdiction reads strip PII at the API boundary. The simplest, most defensible.
2. **Pseudonymous global replica + region-local key vault** — events replicate globally with PII encrypted; the key lives only in the home region. Non-home regions see ciphertext only — can aggregate on opaque ids but cannot read PII. **Crypto-shredding extended across regions:** when the subject invokes erasure, the EU key is deleted; ciphertext everywhere becomes permanently unreadable.
3. **Event split** — `OrderPlaced{orderId, region}` replicates globally (skeletal); paired `OrderPersonalDetails{orderId, name, address, …}` stays region-local. PII projections run only at home; analytical projections work everywhere off the skeletal stream.

**The right-to-erasure event must be appendable in the home region without cross-region coordination.** A request that requires quorum across regions can fail when the network fails — and "we couldn't process your erasure because US-East was down" is not a defence under any of the regimes.

## Audit, retention, and the "retention floor"

For domains where the regulator mandates retention, the event log is the auditable record:

- **Banking** — 5/7/10-year regulatory retention. The ledger stream *is* the audit artefact ([`../specific/banking-and-finance.md`](../specific/banking-and-finance.md)). Crypto-shredding the customer's PII fields is fine; deleting the journal entries themselves is not.
- **Insurance** — multi-decade policy retention. Lifetime claim history.
- **Healthcare** — HIPAA 6-year floor; many state laws extend to 10+ years; pediatric records often retained until majority + 7-10 years.
- **Securities** — SEC 17a-4 WORM 6-year+. Some events fit append-only storage hardware *perfectly*.
- **Land titles, court cases, voting records** — civic forever-retention. The retention floor is "indefinite".

**Pattern:** separate the *event of record* from the *PII-bearing event*.

```
TransferRecorded { transferId, amount, currency, valueDate, fromAcctRef, toAcctRef }
       — non-PII, retained for regulatory floor (forever / 10 years / etc.)

TransferActorIdentity { transferId, customerId, name, address, deviceId, ip }
       — PII-bearing companion, subject to erasure
```

After an erasure request, the `TransferActorIdentity` stream gets crypto-shredded or tombstoned; the `TransferRecorded` stream stays intact. The transfer's *legal existence* survives; the customer's *identity at the moment of the transfer* doesn't. This is the only way to satisfy "retain forever" AND "erase on request" simultaneously.

## The audit-log retention vs PII tension

Same problem in a different costume. Observability tooling (Datadog, Splunk, Sentry, audit logs) commonly retains records for years, and any logged request body or stack trace is a PII reservoir. See [`../specific/observability.md`](../specific/observability.md).

**Practical defences:**
- **Store hashes, not raw values** in audit logs where the audit purpose only needs identity-equality ("user X did Y at T").
- **Redact at log emission, not at retrieval** — `log.info("user_email", redact(email))`.
- **Per-subject key for audit-log PII** — same crypto-shredding pattern as events.
- **Trace IDs are not identifiers of people**, but they can be joined to PII downstream; treat them as quasi-identifiers.

## Five failure modes teams discover the hard way

1. **The deleted user is re-introduced by backup restore.** Backups taken before erasure contain the PII. Restoring an old snapshot re-introduces the data. Fix: maintain a *post-restore "erasure-replay" hook* — the list of erasure events gets re-applied after every backup restore.
2. **Crypto-shredding misses a projection.** The events are unreadable; the read model was last rebuilt before erasure and still holds plaintext PII. Fix: every projection rebuild must consume erasure events as part of its build pipeline.
3. **PII in event IDs / aggregate IDs.** If `customerId` is the email, every event referencing that customer carries their PII in metadata. Fix: opaque IDs (UUIDs) always; emails go in tokenised/encrypted payload fields.
4. **The CDC consumer that nobody owns.** Analytics team set up a Kafka Connect → Snowflake pipeline two years ago; ownership has rotated. Erasure events fan out to the event store; nobody propagated them to Snowflake. Fix: tag every PII-bearing event topic with an "erasure-aware-consumer" registry; CI fails when a consumer subscribes without registering.
5. **The encrypted-PII-is-still-PII finding.** Auditor reads the regulation strictly: until the key is destroyed, you control the data, and so it's still personal data subject to all controls (access, breach notification, etc.). Fix: minimise pre-deletion lifetime; have a documented key-destruction SLA; treat encrypted PII as PII for access control even if you treat it as "deleted" for erasure.

## Domain-by-domain summary

| Domain | Primary regulatory pressure | Dominant strategy | See |
|---|---|---|---|
| **Banking / fintech** | KYC/AML (5-7-10y), SOX, PCI for cards | Crypto-shred PII; never delete ledger; segregate party identity from transaction record | [`../specific/banking-and-finance.md`](../specific/banking-and-finance.md) |
| **Healthcare** | HIPAA (6y+), state laws, right-to-amend (not erase) | Amendment events; audit-grade retention; per-patient encryption | (no dedicated doc yet — see §"Where to add coverage" in [`unbounded-and-infinite-streams.md`](unbounded-and-infinite-streams.md)) |
| **E-commerce** | GDPR Art. 17; PCI for payment instruments | Crypto-shredding by default; tokenise payment instruments | [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) §"GDPR vs immutability" |
| **Chat / messaging** | GDPR; some regional comms-retention; lawful intercept | Tombstoning (`MessageRedacted`); Matrix's `m.room.redaction` is the canonical model | [`../specific/chat-and-messaging.md`](../specific/chat-and-messaging.md) |
| **Social feeds** | GDPR; platform-specific takedown obligations (DMCA, NetzDG) | Tombstone + crypto-shred; quote/reply coherence on redact | [`../specific/social-feeds.md`](../specific/social-feeds.md) §6 |
| **Federated** | GDPR across non-cooperating servers | Advisory delete; design events to minimise PII | [`../specific/federated-systems.md`](../specific/federated-systems.md) |
| **Multi-region** | Schrems II, CCPA, APPI, LGPD | Partition by jurisdiction; region-pinned PII; pseudonymous global replica | [`../specific/multi-region-replication.md`](../specific/multi-region-replication.md) §9 |
| **Multi-master DBs** | Same as multi-region, with CDC complications | Crypto-shred propagates as ciphertext rewrite; advisory delete to CDC consumers | [`../specific/multi-master-distributed-dbs.md`](../specific/multi-master-distributed-dbs.md) |
| **Observability** | GDPR vs immutable audit logs | Store hashes; crypto-shred PII fields; treat trace_id as quasi-identifier | [`../specific/observability.md`](../specific/observability.md) |
| **Smart contracts / blockchain** | Structurally append-only; deletion impossible | Crypto-shred pre-publication; zkSNARKs; shielded pools | [`../specific/smart-contracts-and-blockchain.md`](../specific/smart-contracts-and-blockchain.md) |
| **Version control** | Secrets, accidentally-committed PII | `git filter-repo` + credential rotation; equivalent to crypto-shred | [`../specific/version-control.md`](../specific/version-control.md) |

## Patterns that survive contact with production

- **Minimise PII inclusion.** The strongest defence is to never put a piece of PII into the event log unless a business requirement demands it. Opaque IDs in events; PII in a tokenised vault. Audit every new event type for what PII it carries.
- **Per-subject crypto-shredding key, from day one.** Retrofitting is brutal. Adding it to a 100M-event log requires re-encrypting every event referencing every subject.
- **Segregate the PII-bearing event from the event of record.** The transfer happened (retained forever); who initiated it (subject to erasure) are different events with different streams and different retention policies.
- **Erasure is an event.** `SubjectErasureRequested{subjectId, requestedAt, byActor, scope}` → `SubjectErasureApplied{appliedAt, mechanism: crypto_shred|tombstone|tokenise, projections_affected}`. The erasure itself goes in an audit-grade stream.
- **Projection rebuilds consume erasure events.** Every read-model rebuild pipeline includes the erasure stream in its inputs. Rebuilding from cold storage must not re-introduce erased PII.
- **Backups have an erasure-replay hook.** After restore, replay the erasure log forward.
- **Distinguish "no longer visible" from "the bits are gone".** Both matter, both have separate legal weight, and both should be modelled as different events.
- **Document the retention floor per regime.** A spreadsheet mapping (event type) × (jurisdiction) × (retention floor) × (erasure mechanism) is not optional — it's an auditor's first request.
- **For federated/distributed systems, erasure is advisory.** Build the request flow, propagate to cooperating peers, log non-compliance — and architect to put minimal PII in federated payloads in the first place.

## Where to look in the cloned repos

- **`oskardudycz_EventSourcing.NetCore`** — Dudycz's [GDPR in Event-Driven Architecture](https://event-driven.io/en/gdpr_in_event_driven_architecture/) post is the practitioner reference; the sample shows crypto-shredding patterns at the row level.

## Related docs

- [`../specific/ecommerce-and-retail.md`](../specific/ecommerce-and-retail.md) §"GDPR vs immutability" — the canonical worked-example of the three strategies in retail.
- [`../specific/multi-region-replication.md`](../specific/multi-region-replication.md) §9 — Schrems II, jurisdiction partitioning, region-local key vault.
- [`../specific/chat-and-messaging.md`](../specific/chat-and-messaging.md) — tombstoning vs hard-delete vs redaction; Matrix's `m.room.redaction`.
- [`../specific/social-feeds.md`](../specific/social-feeds.md) §6 — right-to-erasure on signed federated content.
- [`../specific/federated-systems.md`](../specific/federated-systems.md) — advisory delete across uncooperating peers.
- [`../specific/smart-contracts-and-blockchain.md`](../specific/smart-contracts-and-blockchain.md) — deletion as structurally impossible; crypto-shred + ZKP + shielded pools as the only mitigations.
- [`../specific/banking-and-finance.md`](../specific/banking-and-finance.md) — KYC/AML retention; the journal as the regulatory record.
- [`../specific/observability.md`](../specific/observability.md) — audit-log PII handling.
- [`ledgers-and-double-entry.md`](ledgers-and-double-entry.md) — the immutable journal as the audit artefact.
- [`unbounded-and-infinite-streams.md`](unbounded-and-infinite-streams.md) §D — lifetime records under regulatory retention.
- [Oskar Dudycz — GDPR in Event-Driven Architecture](https://event-driven.io/en/gdpr_in_event_driven_architecture/).
- [Conduktor — GDPR Right to Erasure on Kafka](https://www.conduktor.io/blog/gdpr-kafka-right-to-erasure).
- [HashiCorp Vault — GDPR-Compliant Event Sourcing](https://www.hashicorp.com/en/resources/gdpr-compliant-event-sourcing-with-hashicorp-vault).
- [Carnage — Events are forever… until they're not](https://carnage.github.io/2018/10/events-are-forever).
- [Event Sourcing for GDPR — how to forget data without breaking history](https://dev.to/alex_aslam/event-sourcing-for-gdpr-how-to-forget-data-without-breaking-history-4013).
