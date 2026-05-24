# Chat & Messaging — Aggregate & Stream Decomposition

Chat is the canonical [archetype-B domain](../unbounded-and-infinite-streams.md#b-long-running-conversations--activity-timelines--no-end-of-life): a Slack channel can hold 1M+ messages, the relationship never ends, there is no `ChannelClosed` event. Edits, deletes, reactions, threads, read receipts, typing, federation, E2E encryption each force a distinct call on *what is an aggregate, what is a projection, and what doesn't belong in the event store at all*. Drawing on Slack, Discord, WhatsApp, Signal, Matrix, Telegram, XMPP and IRC ([Discord's ScyllaDB migration](https://discord.com/blog/how-discord-stores-trillions-of-messages), [Slack's Vitess sharding](https://slack.engineering/scaling-datastores-at-slack-with-vitess/), [Matrix's room DAG](https://matrix-org.github.io/synapse/latest/development/room-dag-concepts.html)).

## 1. Aggregate boundaries used in practice

Decompose by **lifecycle**, **write rate**, and **whether the server can read the payload** (E2E changes everything). The textbook `Channel{MessagePosted}` model breaks the moment you ask "what about reactions?" or "how do 5000 users mark this message read?".

| Aggregate / object | Aggregate? | Stream-per-X? | Why this boundary |
|---|---|---|---|
| **Channel / Room** | Yes (settings) | One per channel | Name, topic, retention, permissions. Slow-changing. Distinct from the message log. |
| **Message** | Sub-entity of a per-period channel stream | `channel-{id}-{yyyyMM}` | Append-only with edit / tombstone events; never one stream per message. |
| **Thread** | Sometimes its own sub-stream | `thread-{rootMessageId}` for hot threads | Promoted only when reply count justifies the indirection; otherwise just `parentMessageId` on the child event. |
| **Reaction set** | Per-message; relation events, not row-mutation | Rarely its own stream | High write rate ("4000 reactions to one announcement"). Matrix calls this [`m.annotation`](https://github.com/matrix-org/matrix-spec-proposals/blob/main/proposals/2675-aggregations-server.md). |
| **Read state** (per user × channel) | **Not** in the event store | — | A cursor `lastReadMessageId` per `(userId, channelId)`. Hot KV. One event per read flip would crush the store. |
| **Presence / Typing** | **Not** in the event store | — | Matrix calls these EDUs ("ephemeral data units" — explicitly non-persistent — [spec](https://spec.matrix.org/v1.6/server-server-api/)). |
| **User profile** | Yes | `user-{userId}` | Identity, display name, avatar, status. Separate from any conversation. |
| **Membership** | Sub-stream or state events | `channel-{id}-members` or inlined | Matrix puts each `m.room.member` as a state event in the room DAG; Slack/Discord keep it in tables and only milestone events hit the log. |
| **DM** (1:1 / group) | Same as Channel | `dm-{min(a,b)}-{max(a,b)}` / `dm-group-{id}` | A private channel of N members; same stream shape. |
| **Pinned set** | Projection | — | Fold over `MessagePinned` / `MessageUnpinned`; not its own aggregate. |
| **Attachment** | Yes (file lifecycle) | `attachment-{fileId}` | Upload → AV scan → available → deleted. Distinct lifecycle from the message that references it. |
| **Workspace / Server / Guild** | Yes | `workspace-{id}` | Plan, billing, SSO, default retention. Holds channels but isn't *in* the channel streams. |

**Rule of thumb** (Vernon, [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf)): one transactional consistency boundary per aggregate. Reaction-add does **not** mutate the message; thread reply does **not** mutate the parent. The "Message" your client renders is a *projection* over multiple aggregates (message + edits + reactions + replies-count), never one aggregate's snapshot.

### Why Channel ≠ Message log

`Channel` settings (name, topic, retention, members) change in kilobytes per lifetime. The message log is tens of thousands of appends per day in busy channels. One combined stream means every settings change interleaves with a torrent of messages, and replay to compute "what's the current topic?" walks past millions of unrelated posts. Slack, Discord, Matrix all separate these. Discord partitions the message log by `(channel_id, message_id)` with `message_id` a Snowflake; Slack shards by channel ID with Vitess. Settings live elsewhere.

## 2. Stream-id naming patterns

```
workspace-{workspaceId}                      # plan/billing/SSO config
channel-{channelId}                          # settings: name/topic/members/retention
channel-{channelId}-{yyyyMM}                 # period-bucketed message log (the usual)
channel-{channelId}-bucket-{bucketIdx}       # size-bucketed (Discord's original scheme)
dm-{min(userA,userB)}-{max(userA,userB)}     # 1:1 DM, deterministic key
dm-group-{conversationId}
thread-{rootMessageId}                       # promoted sub-stream for deep threads
user-{userId}                                # profile / settings
attachment-{fileId}                          # upload lifecycle (separate from message)
```

**Notably absent — do NOT do this:**
```
message-{messageId}                          # too fine-grained
readstate-{userId}-{channelId}-{...}         # cursor, not an event log
presence-{userId}                            # ephemeral; Redis with TTL
typing-{channelId}-{userId}                  # ephemeral; pub/sub
```

### Period-bucketed message streams

The canonical pattern for unbounded conversation logs. The logical channel log is a sequence of physical streams keyed by time bucket (`channel-C0123-2026-04`, `channel-C0123-2026-05`...). A `BucketOpened{previousBucket, messageCount, lastMessageId}` event starts each new bucket; the previous is now closed and cold-archivable. The live optimistic-concurrency window only covers the current bucket. This is the [closing-the-books](https://event-driven.io/en/closing_the_books_in_practice/) pattern applied to a chat log: the period close is calendar-driven rather than business-driven, but it bounds replay and enables tiered retention.

**Bucket sizing**: by time (monthly, weekly) for low-traffic channels; by count or size for hot ones. Discord originally bucketed Cassandra partitions by `(channel_id, bucket)` with the bucket sized so each partition stayed under ~100 MB — ~10 days for typical channels ([Discord blog](https://discord.com/blog/how-discord-stores-trillions-of-messages)) — and later switched to ordering directly by Snowflake `message_id`.

**Retention tiers**: hot (Redis / SSD, last N messages — Slack does client-side lazy load via edge caches per [InfoQ](https://www.infoq.com/news/2023/04/real-time-messaging-slack/)), warm (OLTP shard, current + recent buckets), cold (S3 / Glacier, closed buckets + compliance archive). Closed bucket streams can be snapshotted and pushed to cold storage with only an index entry retained hot.

## 3. Key events per aggregate

### Channel settings (`channel-{channelId}`)
```
ChannelCreated         { channelId, workspaceId, name, kind, createdBy, createdAt }
ChannelRenamed         { previousName, newName, renamedBy }
ChannelTopicChanged    { previousTopic, newTopic, changedBy }
ChannelRetentionPolicySet { policy, daysToRetain, appliesFrom }
ChannelArchived        { archivedBy, reason }
MemberAdded            { userId, addedBy, role }
MemberRemoved          { userId, removedBy, reason }
MemberRoleChanged      { userId, previousRole, newRole }
```

### Message log (period stream, `channel-{channelId}-{yyyyMM}`)
```
BucketOpened           { bucketKey, previousBucket?, openedAt }
MessagePosted          { messageId, authorId, body, postedAt, clientMsgId, parentMessageId? }
MessageEdited          { messageId, editedBody, editedAt, editedBy, revision }
MessageDeleted         { messageId, deletedBy, reason, hard:false }  # soft-delete / tombstone
MessageRedacted        { messageId, redactedBy, redactedAt }         # Matrix-style content stripped
MessagePinned          { messageId, pinnedBy }
MessageUnpinned        { messageId, unpinnedBy }
ReactionAdded          { messageId, userId, emoji, addedAt }
ReactionRemoved        { messageId, userId, emoji, removedAt }
MessageForwarded       { newMessageId, originalMessageId, fromChannelId, by }
MessageQuoted          { newMessageId, quotedMessageId, quotedExcerpt }
AttachmentAdded        { messageId, attachmentId, kind, byteCount }
BucketClosed           { bucketKey, messageCount, lastMessageId, closedAt }
```

`clientMsgId` is the client-generated **idempotency key** — chat clients retry on network failure (the user has already typed it) and the server must dedupe without emitting two `MessagePosted` for one intent.

### Thread (promoted sub-stream, `thread-{rootMessageId}`)
```
ThreadStarted          { threadId, rootMessageId, channelId, startedBy }
ThreadReplyPosted      { messageId, threadId, authorId, body, postedAt }
ThreadFollowed         { userId, followedAt }
ThreadResolved         { resolvedBy }
ThreadLocked           { lockedBy, reason }
```

In Slack the parent's `thread_ts` is the foreign key ([Slack — modifying messages](https://docs.slack.dev/messaging/modifying-messages/)). A thread is **not** automatically its own stream; promote it only when reply count justifies the indirection — usually somewhere in the hundreds, where inline replies start skewing the parent bucket's size distribution.

### Reactions (relation events, never row-mutation)

Matrix calls these `m.annotation` ([MSC1849 / MSC2675](https://github.com/matrix-org/matrix-spec-proposals/blob/main/proposals/2675-aggregations-server.md)). The reaction event references the message by ID; the server aggregates them into a bundle on the message's read-model. In ES terms:

```
ReactionAdded   { reactionEventId, targetMessageId, userId, emoji, ts }
ReactionRemoved { reactionEventId, targetMessageId, userId, emoji, ts }
```

The per-`(messageId, emoji)` count is materialised into the message read model so clients don't reduce on each view. Modelling reactions as relation events scales linearly with traffic; `UPDATE message SET reaction_counts = ...` does not.

### User profile (`user-{userId}`)
```
UserRegistered         { userId, email, displayName, registeredAt }
DisplayNameChanged     { previous, current }
AvatarChanged          { previousRef, currentRef }
StatusSet              { text, emoji, expiresAt? }   # NOT the "online" presence flag
TimeZoneChanged        { ianaZone }
NotificationPreferenceSet { channelId?, level }
UserDeactivated        { reason, by }
UserDeleted            { mode: tombstone | crypto-shred, by }
```

## 4. Cross-aggregate processes / sagas

Per the project rule, one command touches one aggregate. Everything cross-aggregate is a saga or a projection. See [../../implementation-patterns/multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md).

### 4.1 Send-a-message fan-out

```
Command: PostMessage(channelId, authorId, body, clientMsgId)
       v
Message-bucket aggregate emits MessagePosted{...}
                            |
       +--------------------+----------------------+--------------------+--------------+
       v                    v                      v                    v              v
   WS push to        Push-notif saga         Search index         Mentions proj.    Unread proj.
   online            (APNs/FCM)              projection           (-> user inbox)   (-> cursors)
   recipients
```

All downstream consumers are subscribers of the single `MessagePosted` event ([subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md) for failure/ordering). None write back to the message stream. WhatsApp does this through one Erlang lightweight process per connected user, subscribing to the recipient's mailbox and pushing on arrival ([overview](https://scalewithchintan.com/blog/whatsapp-erlang-architecture-2-billion-users)).

### 4.2 Edit / delete propagation

**No mutation of `MessagePosted`.** The edit is its own event; the read model folds `MessagePosted -> MessageEdited* -> MessageDeleted?` into the rendered payload. Slack exposes both original and edited text when retention is set to "track edits" ([Slack retention](https://slack.com/help/articles/203457187-Customize-data-retention-in-Slack)). Matrix uses the `m.replace` relation — a new event with `m.relates_to: { rel_type: m.replace, event_id: <original> }` carrying `m.new_content` ([MSC2676](https://github.com/matrix-org/matrix-spec-proposals/blob/main/proposals/2676-message-editing.md)). The server bundles the latest edit into the original on retrieval; the DAG keeps every version. Push notifications are universally not re-fired on edit.

### 4.3 Tombstones and thread parents

A parent with replies cannot just disappear without breaking the thread render. Slack shows a "This message was deleted" placeholder so replies remain coherent ([Slack help](https://slack.com/help/articles/202395258-Edit-or-delete-messages)). Two distinct commands, two distinct events:

```
MessageDeleted  { messageId, deletedBy, reason, hard: false }   # tombstone (default)
MessageRedacted { messageId, redactedBy, retainShape: true }    # hard / GDPR erasure
```

Matrix's `m.room.redaction` strips the content from the original event but leaves event-ID, sender, and DAG position so the room's hash-chain stays valid. This is the practical resolution to "GDPR right-to-be-forgotten vs immutable event store" — *content* is removed, *event identity and position* survive. See [ecommerce-and-retail.md](./ecommerce-and-retail.md) for the same crypto-shredding pattern at the row level.

### 4.4 Membership change and backfill

`AddMemberToChannel` emits `MemberAdded` on the settings aggregate; subscribers initialise the `(userId, channelId)` read-state cursor, route a WS subscription, and decide backfill policy. Slack public channels expose full history; Discord exposes only post-join messages by default. The decision lives in the projection, not the message stream.

### 4.5 Cross-workspace shared channels (Slack Connect)

[Slack Connect](https://slack.engineering/how-slack-built-shared-channels/) is the canonical "two workspaces, one channel" problem. Slack gave the shared channel a single canonical home shard and projects metadata into participating workspaces, rather than duplicating messages on both sides. In ES terms: one canonical `channel-{id}-{period}` stream; per-workspace projections of identity / permissions / display state.

## 5. Federation — events as a DAG, not a log

Federated chat (Matrix, XMPP, IRC s2s, ActivityPub) breaks a core assumption: that events have a **total order** within an aggregate. With multiple servers contributing to the same room and partition-tolerant delivery, what you have is a partially ordered **graph**.

Matrix makes this explicit. A room is a DAG of "Persistent Data Units" (PDUs); each event cryptographically references its `prev_events` and `auth_events` ([room DAG concepts](https://matrix-org.github.io/synapse/latest/development/room-dag-concepts.html)). Servers receive events out of order, branch, re-converge, and run state-resolution v2 to deterministically compute the current state from competing forks ([State Resolution v2](https://matrix.org/docs/older/stateres-v2/)). No central sequencer; no consecutive sequence numbers.

Implications for ES-style federated chat:

- **Stream IDs are still per-room** (`room-{roomId}`) but appends are not optimistically locked against a `lastVersion` — multiple homeservers append concurrently. Conflict resolution is via the DAG's `prev_events` chain plus state resolution, not `expectedVersion`. See [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md) for the parallel with CRDT/OT merge.
- **Ephemeral data is shipped but not persisted to the DAG.** Matrix calls these EDUs — typing, presence, receipts — entirely separate from durable room history ([federation API](https://spec.matrix.org/v1.6/server-server-api/)). Holds even in non-federated systems: keep typing and presence off the event store regardless.
- **State events vs message events.** Matrix splits "state events" (membership, name, topic — produce current state via state-resolution) from "message events" (the linear-ish history). The ES analogue is splitting the Channel settings stream from the Channel message log, even within a single server (§1).

XMPP federation is similar but flatter: stanza-by-stanza with [XEP-0313 Message Archive Management](https://xmpp.org/extensions/xep-0313.html) providing optional server-side archive and sync. IRC server-to-server is the original — second-resolution timestamps and netsplit reconciliation — and famously doesn't archive at all, which is why bouncers like [ZNC](https://github.com/znc/znc) exist to give individual users persistent scrollback for an intentionally stateless protocol.

Unifying point: when multiple writers contribute without a coordinator, **the event store becomes a DAG and "current state" requires a merge function**, not a fold over a totally-ordered log.

## 6. End-to-end encryption — what's left in the event store?

In E2E systems (Signal, WhatsApp, iMessage, Matrix encrypted rooms), the server cannot read the body. This breaks every projection that needs plaintext: search, mentions, push previews, content moderation. What survives is metadata plus a ciphertext blob:

```
EncryptedMessagePosted {
  messageId, channelId, senderId,
  ciphertext,                 # opaque to server
  algorithm,                  # e.g. "olm.v1.curve25519-aes-sha2"
  sessionRef,                 # which Megolm/Double-Ratchet session
  ts
}
```

Consequences: search/unfurling run on-device or not at all; push notifications carry only metadata and the text is rendered post-decryption; moderation moves to the client (sender-side filtering or report-then-decrypt-locally). Signal drops ciphertext from the server queue as soon as a device fetches it ([Privacy is Priceless, but Signal is Expensive](https://signal.org/blog/signal-is-expensive/)); WhatsApp does the same — closer to a *transient queue* than an event store, with the durable audit trail living on the device. Signal's [sealed-sender](https://signal.org/blog/sealed-sender/) goes further, so even the sender field is opaque server-side. Group rekeying on member departure (forward secrecy) generates a key-rotation event even though no human "sent" anything.

Matrix's hybrid is instructive: in an encrypted room the *DAG itself* is still plaintext on every participating server — event IDs, sender, prev-events, timestamps, `type: m.room.encrypted` — only `content.ciphertext` is opaque. State resolution, membership, redactions, replies still work. **Encrypt the payload, not the envelope.** The envelope is what keeps the event-sourced system functioning.

## 7. Read state, presence, typing — what does NOT belong in the event store

The high-frequency interaction signals are the canonical "[don't put it in the event store](../README.md#patterns-that-recur-across-every-domain)" trap. They look like events but are better modelled as transient state.

| Signal | Why not in the event store | Where it lives |
|---|---|---|
| **Read state** per `(userId, channelId)` | Every scroll updates the cursor. Past values have no business meaning. | Per-user cursor in Redis / DynamoDB storing `lastReadMessageId`, `lastDeliveredMessageId`. Slack and Discord both keep this entirely off the message store. |
| **Unread counts** | Derived from read state + message stream. | Per-user counter; can be lazy ("unread since X"). |
| **Typing indicators** | Multi-second lifetime; the user already saw it. | Pub/sub topic with ~10s retention. Matrix EDU. |
| **Presence** | Continuous heartbeat. Past values meaningless. | KV with TTL; pub/sub fanout. Matrix EDU. |
| **Delivery receipts** (WhatsApp double-tick) | N messages × M recipients. | Same hot store as read cursors; deletable once delivered. |

The "[phantom update problem](https://systemdr.substack.com/p/designing-a-chat-system-storing-history)": one post in a 1000-member channel would need 1000 read-state updates if every member opens within a minute. The fix is to model read state as a **cursor moved by the user**, not a row touched by the message — the system writes "I am now caught up to message M" once per visit, never "user N read message M".

## 8. Ordering — sequence IDs, Snowflakes, Lamport

A single-server chat can use a monotonic per-channel sequence and call it done. Two situations break that: multiple servers writing to the same channel (federation, multi-region active-active), and offline clients delivering hours-old messages.

Two industry approaches:

1. **Snowflake IDs (Discord, Slack `ts`, Twitter)** — 64-bit `(timestamp_ms | shard_id | per-ms_seq)` ([format](https://en.wikipedia.org/wiki/Snowflake_ID)). K-sortable: roughly chronological, deterministic tiebreaker via shard bits. Discord uses them as the message log's clustering key: `((channel_id), message_id)` partitioned by `channel_id` ([Discord blog](https://discord.com/blog/how-discord-stores-trillions-of-messages)). Slack's `ts` is the same idea — "looks like a Unix timestamp with microseconds but is actually an ID" ([Slack docs](https://docs.slack.dev/messaging/retrieving-messages/)).
2. **Lamport / vector clocks for true distributed order** — independent writers without coordinator. Matrix's room DAG carries `depth` (Lamport-style) plus the `prev_events` graph, enough to deterministically resolve forks. See [collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md).

For non-federated chat, Snowflakes are sufficient — chronological tiebreaking lets clients merge late-arriving messages into roughly the right scroll position without re-sort cascades. Reactions and threaded replies whose causal parent is older than the reaction's clock should always be modelled as relation events with explicit `targetMessageId`, never reordered.

## 9. Real-world gotchas

1. **One client message ≠ one event.** Network retries mean the same `clientMsgId` arrives 3-5 times. Dedup at the aggregate via `clientMsgId` index, not via `messageId` (server hasn't issued one on retry). The event carries both: `clientMsgId` for dedup, `messageId` for canonical identity.
2. **Edit windows.** "Within N minutes" or "until anyone reacts" is an aggregate invariant evaluated against the bucket's tail, never mutation of the original. Past the window, an edit is a *new message that quotes the old one* — different command, different event.
3. **Tombstones don't shrink storage.** `MessageDeleted` is *another* event appended; you've grown, not shrunk. Reclaim happens via retention-driven bucket truncation. The legal distinction between "user can no longer see it" (tombstone) and "the bits are gone" (compaction / redaction / crypto-shredding) is significant — model both.
4. **Reactions are the noisiest write.** A viral message picks up thousands in seconds. Each reaction as an append, aggregated in the projection, scales linearly; `UPDATE message SET reaction_counts = ...` does not.
5. **Threads can blow partition sizing.** Bucketing by `(channel_id, message_id)` with a thread on one root that generates 10k replies all carrying the same `parentMessageId` makes the parent's "child count" projection hot. Either promote the thread to its own stream above some threshold, or shard reply storage by `(parentMessageId, hash(replyId))`.
6. **DM stream IDs need a canonical order.** `dm-{userA}-{userB}` and `dm-{userB}-{userA}` must hash to the same stream. Always normalise (lexicographic min then max). Forgetting this is a recurring outage.
7. **Pins reference messages in cold buckets.** Denormalise enough payload into the pin event (`title`, `excerpt`, `authorAtPinTime`) so cold reads aren't required for normal display.
8. **Membership changes invalidate read state.** When a user is removed and re-added, their old `(userId, channelId)` cursor is misleading. Reset on `MemberRemoved`; offer "mark all read" on re-add.
9. **Mentions resolve at send time.** Capture the resolved `userId` in the `MessagePosted` payload, not the display name; a later rename then doesn't break old mentions. Slack renders the *current* display name but links by stable ID.
10. **Backfill on join via projection, not stream replay.** Naive replay floods the WS connection; paginate against the read model instead.
11. **Federated rooms rewrite history.** A homeserver netsplit for a day delivers hours of backdated events on rejoin that interleave with the live stream. Clients must subscribe by *event ID* (stable), not *position* (not stable).
12. **Cross-period queries hit a search index, not a fan-read.** "Everything from this user in this channel last year" crosses many bucket streams; the answer is a per-channel-per-author projection (usually a search index).

## 10. Sources & case studies

- **Discord** — [How Discord Stores Trillions of Messages](https://discord.com/blog/how-discord-stores-trillions-of-messages); [InfoQ — Cassandra → ScyllaDB migration](https://www.infoq.com/news/2023/06/discord-cassandra-scylladb/); [ScyllaDB tech talk](https://www.scylladb.com/tech-talk/how-discord-migrated-trillions-of-messages-from-cassandra-to-scylladb/).
- **Slack** — [Scaling Datastores at Slack with Vitess](https://slack.engineering/scaling-datastores-at-slack-with-vitess/); [How Slack Built Shared Channels](https://slack.engineering/how-slack-built-shared-channels/); [Real-Time Messaging Architecture at Slack (InfoQ)](https://www.infoq.com/news/2023/04/real-time-messaging-slack/); [Slack — modifying messages](https://docs.slack.dev/messaging/modifying-messages/); [Slack — retrieving messages](https://docs.slack.dev/messaging/retrieving-messages/); [Customize data retention](https://slack.com/help/articles/203457187-Customize-data-retention-in-Slack).
- **Matrix** — [Matrix Specification](https://spec.matrix.org/latest/); [Room DAG concepts](https://matrix-org.github.io/synapse/latest/development/room-dag-concepts.html); [State Resolution v2 for the Hopelessly Unmathematical](https://matrix.org/docs/older/stateres-v2/); [MSC1849 / MSC2675 (aggregations / reactions)](https://github.com/matrix-org/matrix-spec-proposals/blob/main/proposals/2675-aggregations-server.md); [MSC2676 (message editing)](https://github.com/matrix-org/matrix-spec-proposals/blob/main/proposals/2676-message-editing.md); [Server-Server (federation) API](https://spec.matrix.org/v1.6/server-server-api/).
- **WhatsApp** — [How WhatsApp Grew to ~500M Users (High Scalability)](https://highscalability.com/how-whatsapp-grew-to-nearly-500-million-users-11000-cores-an/); [WhatsApp Erlang Architecture](https://scalewithchintan.com/blog/whatsapp-erlang-architecture-2-billion-users).
- **Signal** — [Signal Protocol (Wikipedia)](https://en.wikipedia.org/wiki/Signal_Protocol); [Sealed Sender](https://signal.org/blog/sealed-sender/); [Privacy is Priceless, but Signal is Expensive](https://signal.org/blog/signal-is-expensive/).
- **Telegram** — [System Architecture overview](https://readmedium.com/telegram-system-architecture-ddf9f7d358de); MTProto schema docs.
- **XMPP / IRC** — [XEP-0313 Message Archive Management](https://xmpp.org/extensions/xep-0313.html); [ZNC IRC bouncer](https://github.com/znc/znc) (scrollback for an intentionally stateless protocol).
- **Snowflake IDs** — [format (Wikipedia)](https://en.wikipedia.org/wiki/Snowflake_ID).
- **Cross-cutting** — [Designing a Chat System (systemdr)](https://systemdr.substack.com/p/designing-a-chat-system-storing-history); [How Discord Stores Trillions of Messages (ByteByteGo)](https://blog.bytebytego.com/p/how-discord-stores-trillions-of-messages).

## Related docs in this knowledge base

- [../unbounded-and-infinite-streams.md](../unbounded-and-infinite-streams.md) — chat is the worked example of archetype B; see the period-sharding patterns.
- [../../concepts/collaborative-editing-ot-crdt-lww.md](../../concepts/collaborative-editing-ot-crdt-lww.md) — for federated chat, ordering across writers reduces to the same merge problem as collaborative documents.
- [../../implementation-patterns/multi-aggregate-commands-and-sagas.md](../../implementation-patterns/multi-aggregate-commands-and-sagas.md) — message-send fan-out, edit propagation, and federation backfill all use the saga / process-manager shape.
- [../../implementation-patterns/subscription-checkpoints-and-ordering.md](../../implementation-patterns/subscription-checkpoints-and-ordering.md) — push, search, mentions, and unread-count subscribers all need checkpoint semantics; for federated chat, the ordering guarantee is partial, not total.
- [./ecommerce-and-retail.md](./ecommerce-and-retail.md) — GDPR vs immutability and crypto-shredding apply identically to chat right-to-be-forgotten.
