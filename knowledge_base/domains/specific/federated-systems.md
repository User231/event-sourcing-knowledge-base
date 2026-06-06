# Federated Systems — Multi-Master ES Across Independent Servers

A federated system is **multi-master event sourcing where each master is an independently operated server with its own admin, retention policy, identity authority, and moderation rules**. Unlike a Cassandra ring or CockroachDB cluster (see [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md)), peers can defederate, run out of disk, censor a topic, ignore a delete, or go offline for a week and come back demanding replay.

This is archetype-E from [unbounded-and-infinite-streams.md §E](../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories) made concrete: events branch and merge across administrative domains, identity is server-scoped, and the source of truth is whoever signed the event.

The cleanest example is **Matrix**, whose room is a signed DAG of events replicated across homeservers and reconciled by a deterministic state-resolution algorithm. The oldest is **SMTP email**, federating signed-ish threaded messages across mutually distrustful servers since 1982. **ActivityPub**, **AT Protocol**, **Nostr**, **XMPP**, and historical **Usenet/NNTP** sit between those poles.

## 1. Federation models, ranked by ES-friendliness

| Protocol | Event model | Ordering | Identity |
|---|---|---|---|
| **Matrix** | Signed DAG of PDUs per room, replicated to all participating homeservers | Partial order via `prev_events` + `depth`; [State Resolution v2](https://matrix.org/docs/older/stateres-v2/) reconciles conflicts | `@user:server` — server is identity authority |
| **AT Protocol (BlueSky)** | Per-account signed [repository](https://atproto.com/specs/repository) (MST of records); commits chained, monotonic `rev` (TID); broadcast on `subscribeRepos` firehose | Total order *per repo*; no cross-repo order | DID; PDS holds rotation keys |
| **Nostr** | Flat firehose of Schnorr-signed events; relays are dumb stores serving filtered queries | None across relays; `created_at` author-asserted | Schnorr `pubkey` only, no server-scoping |
| **ActivityPub** (Mastodon, Lemmy, Pleroma, Misskey, PeerTube) | JSON-LD `Activity` objects POSTed to recipient `inbox` URLs; sender's `outbox` is an `OrderedCollection` | Informal — HTTP arrival order; `published` author-asserted | `acct:user@domain` via [WebFinger](https://en.wikipedia.org/wiki/WebFinger) |
| **XMPP** | Per-stanza s2s delivery; MUC rooms hosted on one authoritative server | No global order | `user@domain/resource`; [server dialback (XEP-0220)](https://xmpp.org/extensions/xep-0220.html) |
| **SMTP / email** | Store-and-forward; threading via [`Message-ID` / `References` / `In-Reply-To`](https://www.rfc-editor.org/rfc/rfc5322.html) | Best-effort; thread reassembled client-side | `local@domain`; DKIM signs envelope |
| **Usenet / NNTP** | Articles flood-propagated via [IHAVE / NEWNEWS](https://www.rfc-editor.org/rfc/rfc977); each has `Message-ID` and `References` | Per-server arrival order | `From:` header — historically unauthenticated |

**Rule of thumb**: the further down the table, the more federation looks like messaging between cooperating servers and the less like replicating an event log. Matrix and AT Protocol uniquely make the log structure explicit on the wire. Lemmy, Pleroma, Misskey are ActivityPub implementations with different content models (link-aggregator, microblog, microblog+) — they federate with Mastodon at the activity layer but each adds non-standard extensions that gracefully degrade.

## 2. Aggregate boundaries in a federation

Federation adds three boundaries absent from single-tenant ES: **server identity**, **moderation scope**, **defederation**.

| Aggregate | Boundary rationale | Lifecycle |
|---|---|---|
| **Actor / User identity** | One account = one key set, lives on one home server | Created → Active → Suspended → Deleted / Migrated |
| **Server / Instance** | Administrative master with its own retention, moderation, software, peer list | Provisioned → Federating → Defederated-by-peer → Decommissioned |
| **Room / Channel / Community** | Federation unit; can be replicated (Matrix) or single-host (XMPP MUC, Lemmy community) | Created → Open → Tombstoned / Upgraded |
| **Post / Activity / Note / PDU** | The replicated event; signed, content- or URI-addressed; immutable after send | Published → (Edited)* → (Deleted) |
| **Follow / Subscription** | Drives fan-out routing; an event in its own right | Requested → Accepted → Unfollowed |
| **Delete / Tombstone** | A *new* event referencing the deleted one — remote deletion cannot be enforced | Issued → Propagated (best-effort) |
| **Moderation action** | Owned by admin, not author; distinct lifecycle (issue/appeal/lift) | Issued → Active → Lifted |
| **Defederation event** | Severs a server pair; in-flight events drop | Issued → Active |
| **Signing key** | Per-server (Matrix) or per-user (AT Proto, Nostr); rotation is an event | Generated → Active → Rotated → Revoked |

**Critical**: in single-tenant ES the aggregate owns its identity; in federated ES **identity is owned by a server**. `@alice@instance-a.org` and `@alice@instance-b.org` are different aggregates even if the same human runs both — which is why account migration (Mastodon `Move`, ActivityPub `Move`) must be a first-class cross-server event.

## 3. Stream-id naming with federated identity

Local stream-ids are meaningless across servers. Federated systems address events by one of three schemes:

```
# URI-addressed (ActivityPub, XMPP)
https://mastodon.social/users/alice/statuses/123456789

# Content-addressed / signed-envelope (Matrix, AT Protocol)
$base64-hash-of-signed-content                  # Matrix event_id (room v3+)
bafyrei...                                      # AT Proto CID
TID = base32(microsecond_ts + clock_id)         # AT Proto record key in repo

# Pubkey + content-hash (Nostr)
event.id = sha256(serialised_event_including_pubkey)
```

Local stream layouts inside one server typically look like:

```
actor-{did}                                     # AT Proto per-account repo IS the stream
room-{roomId}                                   # Matrix room, same id across servers
inbox-{actorId}                                 # ActivityPub per-actor inbox
outbox-{actorId}                                # ActivityPub per-actor outbox
community-{communityId}@{server}                # Lemmy community, server-scoped
defederation-{localServer}->{remoteServer}     # admin-action stream
```

**Mastodon does not crawl peer outboxes proactively** ([blog.joinmastodon.org](https://blog.joinmastodon.org/2018/06/how-to-implement-a-basic-activitypub-server/)). The outbox is an `OrderedCollection` in spec but in practice it's a projection cache; remote peers only see posts published *after* a local user starts following. This is the canonical "spec says ES, implementation is fire-and-forget" trap.

## 4. Matrix state resolution — the canonical federated merge

Each Matrix room is a DAG of **PDUs** (Persistent Data Units):

```
PDU {
  event_id        : content-addressed (hash of canonical form in room v3+)
  room_id         : globally agreed room id
  type            : "m.room.message" | "m.room.member" | "m.room.power_levels" | ...
  state_key       : present for state events (e.g. user id for membership)
  sender          : "@user:server"
  origin_server_ts: author-asserted, untrusted
  prev_events     : [event_ids]   // DAG parents
  auth_events     : [event_ids]   // events that authorise this one
  depth           : max(prev.depth) + 1   // Lamport-like hint, NOT authoritative
  content         : { ... }
  hashes          : { "sha256": "..." }
  signatures      : { "server": { "ed25519:keyId": "base64-sig" } }
}
```

Different servers see the DAG with different leaves depending on what's reached them. **State Resolution v2** is the deterministic merge ([matrix.org/docs/older/stateres-v2/](https://matrix.org/docs/older/stateres-v2/)):

```
1. Partition state events into unconflicted (same value across all input sets)
   and conflicted (different values).
2. full_conflicted_set = conflicted + their auth chains.
3. Order "power events" (power_levels, join_rules, member kick/ban) by
   reverse topological power ordering: topo-sort over auth-event DAG,
   tie-break by (sender power desc, origin_server_ts asc, event_id lex asc).
4. Apply iterative auth checks from unconflicted: replay each power event,
   accept iff its auth_events permit the change.
5. Order remaining events by mainline ordering: walk the power_levels chain,
   assign each event a position by closest mainline ancestor, then sort by
   (mainline pos, origin_server_ts, event_id).
6. Reapply iterative auth checks. Layer unconflicted state back on top.
```

The algorithm is deterministic and Byzantine-tolerant. Two honest servers given the same DAG produce identical resolved state; a malicious server cannot rewrite history because it doesn't hold others' signing keys (at worst it declines to forward). This is the room-state analogue of CRDT merge from [`../../concepts/collaborative-editing-ot-crdt-lww.md`](../../concepts/collaborative-editing-ot-crdt-lww.md) — the auth chain provides the deterministic tiebreaker.

## 5. Event signing and integrity

| Protocol | Signed by | Algorithm | Rotation |
|---|---|---|---|
| **Matrix** | Sending homeserver (and origin for state PDUs) | Ed25519, multiple keyIds per server | Old keys remain valid for historical verify; new events use current keys |
| **AT Protocol** | User's PDS using rotation key from the DID document | secp256k1 / P-256 | DID document holds current + rotation; PLC directory tracks history |
| **Nostr** | Author directly | Schnorr / secp256k1 | No protocol rotation — rotating = new pubkey = new identity (NIP-26 delegation tries to fix this) |
| **ActivityPub** | Sending server via [HTTP Signatures](https://datatracker.ietf.org/doc/html/draft-cavage-http-signatures-12); body integrity via `Digest` | RSA-SHA256 | Actor's `publicKey` field; rotation = update actor, peers re-fetch |
| **SMTP** | Sending domain via DKIM (optional) | RSA / Ed25519 | DKIM selector in DNS |
| **Usenet** | Nothing | — | — (and that is the cautionary tale) |

A federated event store **cannot trust its own database**. Every event read must be verifiable independently — otherwise an admin on server X could inject `Message{sender: @bob@server-y}` into their local room copy and clients would see it as Bob's. The signature makes the *event itself* the authority, not the server hosting it. **Key rotation is the hardest part**: ten years of signed events means ten years of historical keys you must keep resolvable, or your archive becomes unverifiable.

## 6. Inbox/outbox model — fan-out as ES delivery

ActivityPub maps directly onto "publish event to subscribers", with federation twists.

```
Outbox = actor's published log (OrderedCollection of Activities)
Inbox  = actor's received log (OrderedCollection of Activities)
```

When Alice on `instance-a.org` posts:

```
1. Client POSTs Create{Note{...}} to https://instance-a.org/users/alice/outbox
2. instance-a.org persists in Alice's outbox stream
3. Fan-out: POST to every follower's inbox URL — or to the shared inbox
   POST https://{peer}/inbox  with cc: [followers]   (transport batching only)
4. Receiving server persists in recipient's inbox, runs local projections
   (timeline, notifications, search index).
```

Key activity types to model as event names:

```
Create   { actor, object: Note{...} }              # new post
Update   { actor, object }                         # edit (republishes object)
Delete   { actor, object }                         # tombstone request
Like     { actor, object }                         # reaction
Announce { actor, object }                         # boost / repost / share
Follow   { actor, object }                         # subscribe
Accept / Reject { actor, object: Follow }          # follow decision
Undo     { actor, object: Like|Follow|Announce }   # retract previous activity
Block    { actor, object }                         # per-user block
Move     { actor, target }                         # account migration
Flag     { actor, object, content }                # moderation report
```

`Undo` is the convention for "take back a previous event" — never delete; append the inverse. The original `Like` stays in the outbox audit log; the like-count projection subtracts on `Undo`. Same pattern as `WithdrawalReleased` in [banking-and-finance.md §3](banking-and-finance.md#3-key-events-per-aggregate).

**Shared inbox** is a federation-load optimisation: one POST to `https://mastodon.social/inbox` instead of 5000 individual inboxes. Semantically equivalent — project as if each recipient received individually.

## 7. Delete semantics — advisory, never enforced

| Protocol | Primitive | Enforcement |
|---|---|---|
| **Matrix** | `m.room.redaction` event referencing target | All servers SHOULD redact content; event_id stays in DAG with content stripped |
| **ActivityPub** | `Delete{object}` activity; MAY replace with `Tombstone{formerType, deleted}` | [W3C spec](https://www.w3.org/TR/activitypub/): "nothing in the ActivityPub protocol can enforce remote deletion" |
| **AT Protocol** | New commit removing the record from the MST | Previous commits remain in CAR history; relays propagate the deletion commit |
| **Nostr** | NIP-09 `kind:5` deletion event | Relays MAY drop the original; many don't |
| **Email** | None | Recall is vendor-local |
| **Usenet** | `cancel` control message | Largely ignored — cancels were forgeable, so most servers stopped honouring them |

Once an event is forwarded to N servers, the best you can do is request each drop it. You cannot enforce it. This is the operational shape of GDPR vs an immutable signed event store across jurisdictions you don't control. Several Mastodon admins document month-long "tombstone storms" after a popular account deletes — the `Delete` fans out to thousands of servers, each chewing through stored posts. The cross-domain treatment of the privacy-vs-immutability tension is in [`../cross-cutting/compliance-pii-and-immutability.md`](../cross-cutting/compliance-pii-and-immutability.md) — federated advisory delete is the hardest version.

**Model `Delete` as a separate aggregate referencing the original**, not as a mutation. The original `Create` stays for audit; projections decide whether to surface.

## 8. Edits as new events

Edits are new events referencing originals — never mutations:

```
# Matrix
m.room.message with content."m.new_content" and
  "m.relates_to": { "rel_type": "m.replace", "event_id": "$original" }

# ActivityPub
Update { actor, object: { id: original-uri, content: "new text", updated: <ts> } }

# Nostr — kind:1 not editable; replaceable kinds use "latest event for
# (pubkey, kind, d-tag) wins" — explicit LWW.

# AT Protocol — new commit puts a new record at the same MST path with
# a new CID; previous record's CID stays in older commits.
```

**Projection rule**: maintain `latest_edit_for(original_id)`; render overlays the most recent `m.replace` / `Update` on top of the original. Original event never modified — preserves audit ("what did Alice originally say at 14:03?") after edit.

Concurrent edits across servers fall back to LWW by author-asserted timestamp (Mastodon, Nostr) or the protocol's native conflict resolution. The CRDT/OT discussion in [`../../concepts/collaborative-editing-ot-crdt-lww.md`](../../concepts/collaborative-editing-ot-crdt-lww.md) applies directly — federation adds "the peer may be hostile" to the threat model.

## 9. Moderation as events

Moderation is its own aggregate, referencing but never mutating the offending content (distinct lifecycle: issue / appeal / lift; distinct actor: admin, not author).

```
ContentReported       { reportId, reporter, target, reasons[] }
ContentTakenDown      { takedownId, target, scope: 'local'|'federation', issuedBy, reason }
UserSuspended         { suspensionId, target, scope, expiresAt? }
InstanceDefederated   { localServer, remoteServer, scope: 'block'|'silence'|'mediaReject', issuedBy }
InstanceLimitedReach  { remoteServer, mode: 'public-unlisted' }   # Mastodon "limit"
ModerationAppealed    { appealId, againstAction, byUser, body }
ModerationLifted      { actionId, liftedBy, reason }

UserBlocked           { blocker, blocked }
UserMuted             { muter, muted, scope: 'notifications'|'all' }
DomainBlocked         { user, domain }
```

Mastodon's three escalation tiers ([docs.joinmastodon.org/admin/moderation/](https://docs.joinmastodon.org/admin/moderation/)):

| Action | Effect | Reversible |
|---|---|---|
| **Silence** | Posts no longer appear in federated/public timelines for non-followers | Yes |
| **Suspend** | Account frozen; outbound activities stopped; existing content hidden | Reversible 30 days, then purged |
| **Defederate (instance suspend)** | All accounts on remote server treated as suspended; new activities rejected | Yes, but in-flight content stays tombstoned |

## 10. Defederation — a single event with massive blast radius

```
InstanceDefederated {
  defederationId,
  localServer:     'instance-a.org',
  remoteServer:    'instance-b.org',
  scope:           'full' | 'media-only' | 'silence',
  issuedBy:        'admin@instance-a.org',
  reason,
  issuedAt
}
```

**Triggers locally**: inbound POSTs from the peer start returning 403; local follows soft-break (the `Follow` event isn't deleted, projection stops surfacing); cached posts may be purged from media storage; the event itself drives any audit/appeal flow.

**Does not trigger**: any change on the peer (they don't know unless they probe); recovery of content already federated *out* to other peers; deletion of peer users from unrelated third-party servers' social graphs.

**Defederation is not symmetric** — `instance-b.org` may still federate happily with `instance-c.org`, which may still federate with `instance-a.org`. Cross-server transitive blocks (Bluesky labelers, Mastodon shared blocklists) are an active design problem ([Decentralized Moderation on Mastodon, WebSci '24](https://dl.acm.org/doi/10.1145/3614419.3644016); ["A Blocklist is a Boundary"](https://dl.acm.org/doi/pdf/10.1145/3710919)).

**In-flight events drop**. No two-phase commit, no drain. Fine for chat/social, catastrophic for payments — which is why federation-as-payment-rail proposals have never landed.

## 11. Backfill and historic events

| Protocol | Mechanism | Limits |
|---|---|---|
| **Matrix** | `/backfill` (paginated walk backwards) and `/get_missing_events` (fill gaps when receiving a PDU whose `prev_events` aren't known) | Server may have purged history; soft-failed events excluded; large-room pain point ([Synapse #12539](https://github.com/matrix-org/synapse/issues/12539)) |
| **AT Protocol** | `com.atproto.sync.getRepo` returns full repo as CAR; `subscribeRepos` WebSocket replays from a sequence number | PDS may rotate keys / prune; relay holds firehose tail |
| **Nostr** | `REQ` filter with `since` / `until` against any relay holding the events | Relay-dependent; no guarantee any specific relay has any specific event |
| **ActivityPub** | Spec defines `outbox` as `OrderedCollection`; Mastodon does not crawl it | Hard limit — historical posts effectively invisible to newly federating peers |
| **XMPP** | XEP-0313 MAM for own-server history; cross-server backfill unstandardised | Per-server only |
| **Usenet** | `NEWNEWS <wildmat> <date>` returns IDs since a timestamp | Per-server retention (days/weeks for text; large peers run multi-PB binary spools) |

Matrix backfill is the most thoroughly engineered: a DAG walk over signed events, with auth checks and state-res as ingestion proceeds. Think of backfill as "open an ESDB subscription at offset N" from [subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md), only the upstream is a different organisation that may not have offset N anymore. Subscribers must tolerate missing history — see [subscriber-failure-strategies.md](../../implementation-patterns/subscriber-failure-strategies.md).

## 12. Ordering and causal consistency

No global clock, no global sequence number. The toolbox:

| Mechanism | Used by | Gives you |
|---|---|---|
| **Wall clock** (`origin_server_ts`, `created_at`, `published`) | All — as a hint | Author-asserted, gameable; display sort only |
| **Lamport timestamp** | Matrix `depth` (implicit) | Partial order within one DAG |
| **DAG `prev_events`** | Matrix, Git, Automerge | True causal "happened-after"; merge reconciles concurrent branches |
| **Per-actor monotonic sequence** | AT Proto `rev` (TID) | Total order within one author; trivial dedup |
| **Vector clocks** | Research CRDTs; not in mainstream federation | Precise concurrency detection; cost grows with replica count |
| **Hash-chain / Merkle DAG** | AT Proto commits, Matrix auth-chains | Tamper-evidence + ordering proof |

**Two practical conclusions**:

1. Never trust `origin_server_ts` for security or replay correctness — a misconfigured or hostile server can set it to anything. Use for display sort and tie-breaking only.
2. Authoritative ordering is per-aggregate, not global. A Matrix room has a partial order; an AT Proto repo has a total order. Across rooms / across users, no total order exists — projections must not assume one.

## 13. Discovery and capability negotiation

```
# Account → actor URL
GET https://host/.well-known/webfinger?resource=acct:user@host
  → { "links": [{ "rel": "self", "type": "application/activity+json",
                  "href": "https://host/users/user" }] }

# Server capabilities
GET https://host/.well-known/nodeinfo
GET https://host/nodeinfo/2.0
  → { "software": { "name": "mastodon", "version": "4.2.10" },
      "protocols": ["activitypub"], "usage": {...} }

# Matrix server
GET https://host/.well-known/matrix/server
GET https://matrix.host:8448/_matrix/key/v2/server   # published Ed25519 keys

# AT Protocol
did:plc:...   → plc.directory → DID document with PDS URL + keys
did:web:host  → GET https://host/.well-known/did.json
```

Discovery events worth keeping in the local audit log:

```
PeerDiscovered          { remoteServer, software, version, capabilities[] }
PeerCapabilitiesChanged { remoteServer, oldCaps, newCaps }
PeerKeyRotated          { remoteServer, oldKeyId, newKeyId, observedAt }
```

## 14. Where federation borrows directly from ES

- **Matrix room DAG** — literally an event-sourced room. State is a projection; replay reconstructs it. State resolution is a deterministic merge (lattice join, in CRDT terms).
- **AT Protocol per-user repo** — signed append-only log per account, monotonic `rev`, content-addressed records. `subscribeRepos` firehose is the global subscription. App views (search, "discover", custom feeds) are projections.
- **Nostr signed events** — every event self-contained, signed, identified by content hash. Relays are dumb log stores. Clients are projection engines.
- **ActivityPub Outbox / Inbox** — spec defines them as `OrderedCollection`s (append-only logs, paginated). Fan-out-by-POST is exactly the subscriber-failure problem at HTTP scale.
- **Email `Message-ID` / `References`** — the original content-addressed event graph. Threading is a client-side projection over `In-Reply-To` chains, the way an ES projector would reconstruct a conversation tree.

The mental model: **a federation protocol is an ES system whose log is sharded by administrative domain instead of by aggregate id**, with a signing scheme to keep shards independently verifiable, and a merge function to reconcile concurrent updates.

## 15. Gotchas

- **Identity collisions.** `@elon@mastodon.social` and `@elon@masto.host` are different accounts; UI drops the domain part for cosmetics. The event store must always carry fully-qualified identity.
- **Server-controlled timestamps.** `origin_server_ts` and `published` are author-asserted — clock-skewed or hostile servers can backdate/future-date. Display hint only.
- **Replay attacks.** A signed event is valid forever. Without protocol dedup (Matrix event_id, Nostr id, AT Proto CID) a malicious relay can re-deliver an old `Delete` to undo a restore, or an old ban to re-ban an unbanned user. Idempotency-check on event identity, not payload.
- **Mass-moderation flooding.** When a 500K-user instance defederates 50 peers at once, the resulting tombstone/undo-follow fan-out can DoS small peers. Mastodon admins regularly report queues of millions of pending federation jobs after big moderation events.
- **Small server federating with mastodon.social.** Inbound fan-out from one huge instance can saturate a 4-vCPU peer. Backpressure is essentially unsolved; the typical mitigation is defederation or accepting dropped events. See [subscriber-failure-strategies.md](../../implementation-patterns/subscriber-failure-strategies.md).
- **Signed-event key rotation.** Ten years of events signed by key K1 means K1's public key must remain resolvable forever or historical events become unverifiable. Matrix mandates this; most others are looser. Archive keys alongside events.
- **Content vs URI addressing.** Content-addressed events (Matrix `$hash`, Nostr `sha256`, AT Proto CID) are server-agnostic and dedup across mirrors. URI-addressed events (ActivityPub `https://host/note/123`) break when the host changes — the same content has a different ID on a different mirror. Account migration is much harder under URI addressing.
- **Account migration / Move.** Mastodon `Move`, AT Proto PDS migration: "the same logical aggregate now lives on a different server". Structurally a cross-server `AccountMerged` that breaks "one log per identity" unless modelled carefully. Many implementations silently drop followers on Move.
- **Federation as DoS vector.** Every accepted signed event costs CPU to verify, disk to store, bandwidth to forward. Rate-limit per-peer; never trust per-event counts from an untrusted source.
- **The Usenet cautionary tale.** Usenet had flood-fill federation, `Message-ID` content addressing, `References` threading — the wire format was prescient. What it lacked was signed identity. By the late 1990s spammers forged `From:` freely, `cancel` was forgeable, binary groups dwarfed text. The network still works; the social layer collapsed. Every modern federated protocol that succeeded (Matrix, AT Proto, Nostr) treats per-message cryptographic identity as foundational, not optional.

## Sources

- **Matrix** — [Server-Server API](https://spec.matrix.org/v1.11/server-server-api/); [State Resolution v2 for the Hopelessly Unmathematical](https://matrix.org/docs/older/stateres-v2/); [MSC1442 state-res proposal](https://github.com/matrix-org/matrix-doc/blob/master/proposals/1442-state-resolution.md); [Synapse Federation overview](https://deepwiki.com/element-hq/synapse/3-federation-system).
- **ActivityPub** — [W3C Recommendation](https://www.w3.org/TR/activitypub/); [Mastodon ActivityPub docs](https://docs.joinmastodon.org/spec/activitypub/); [How to implement a basic ActivityPub server](https://blog.joinmastodon.org/2018/06/how-to-implement-a-basic-activitypub-server/); [Delete activity primer](https://www.w3.org/wiki/ActivityPub/Primer/Delete_activity).
- **AT Protocol / BlueSky** — [Repository spec](https://atproto.com/specs/repository); [Sync spec](https://atproto.com/specs/sync); [Federation Architecture](https://docs.bsky.app/docs/advanced-guides/federation-architecture); [Firehose](https://docs.bsky.app/docs/advanced-guides/firehose).
- **Nostr** — [NIP-01](https://github.com/nostr-protocol/nips/blob/master/01.md); [NIP-09 deletion](https://github.com/nostr-protocol/nips/blob/master/09.md); [The Nostr Protocol](https://nostr.how/en/the-protocol).
- **XMPP** — [XEP-0220 Server Dialback](https://xmpp.org/extensions/xep-0220.html); [Prosody s2s docs](https://prosody.im/doc/s2s); [Isode — Federated MUC](https://www.isode.com/whitepaper/federated-multi-user-chat/).
- **Email / Usenet** — [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322.html); [RFC 977 NNTP](https://www.w3.org/Protocols/rfc977/rfc977); [RFC 2980 Common NNTP Extensions](https://www.rfc-editor.org/rfc/rfc2980.html).
- **Discovery** — [WebFinger RFC 7033](https://datatracker.ietf.org/doc/html/rfc7033); [NodeInfo](https://nodeinfo.diaspora.software/).
- **Moderation research** — [Decentralized Moderation on Mastodon (ACM WebSci '24)](https://dl.acm.org/doi/10.1145/3614419.3644016); ["A Blocklist is a Boundary"](https://dl.acm.org/doi/pdf/10.1145/3710919); [Community-Level Blocklists (arXiv 2506.05522)](https://arxiv.org/pdf/2506.05522); [Mastodon moderation docs](https://docs.joinmastodon.org/admin/moderation/).

## Cross-references

- [`../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories`](../cross-cutting/unbounded-and-infinite-streams.md#e-branching--non-linear-histories) — federation is archetype-E
- [`../../concepts/collaborative-editing-ot-crdt-lww.md`](../../concepts/collaborative-editing-ot-crdt-lww.md) — Matrix state-res is the room-state analogue of CRDT merge; LWW on `origin_server_ts` is the Mastodon edit story
- [chat-and-messaging.md](chat-and-messaging.md) — Matrix is the federated case of chat-channel patterns
- [social-feeds.md](social-feeds.md) — ActivityPub fan-out is social feeds + federation
- [multi-master-distributed-dbs.md](multi-master-distributed-dbs.md) — same merge problem one layer down
- [multi-region-replication.md](multi-region-replication.md) — same "no global clock" constraint
- [`../../implementation-patterns/subscriber-failure-strategies.md`](../../implementation-patterns/subscriber-failure-strategies.md) — fan-out-by-HTTP-POST is the worst-case
- [`../../implementation-patterns/subscription-checkpoints-and-ordering.md`](../../implementation-patterns/subscription-checkpoints-and-ordering.md) — backfill = "start subscription at offset N from an unreliable peer"
