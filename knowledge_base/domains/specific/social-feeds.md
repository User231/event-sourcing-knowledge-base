# Social Feeds & Timelines — Aggregate & Stream Decomposition

Social platforms (Twitter/X, Facebook, Instagram, TikTok, LinkedIn, Pinterest, Reddit, BlueSky, Mastodon) are the canonical case for [archetype B in the unbounded-streams taxonomy](../unbounded-and-infinite-streams.md#b-long-running-conversations--activity-timelines--no-end-of-life): relationship-as-stream with no closing event, write amplification is brutally asymmetric (one celebrity post → 100M timelines), and the "feed" everyone calls *the* model is actually a per-user projection, never an aggregate.

## 1. Aggregate boundaries used in practice

The load-bearing distinction: **Timeline / Feed is not an aggregate** — it's a per-user projection materialised either at write time (push) or at read time (pull).

| Aggregate | Why it's a boundary | Lifecycle |
|---|---|---|
| **User / Profile** | Identity, handle, bio, settings. Slow-changing; separate so post churn doesn't bloat profile reads. | Created → Active → Suspended/Deleted |
| **Post** (tweet, toot, pin, skeet, status) | Per-post optimistic concurrency for its own metadata (edits, pins, visibility). One stream per `postId`. | Drafted → Published → Edited* → Deleted/Tombstoned |
| **Comment / Reply** | Often a Post with `inReplyTo`. Reddit treats it as first-class with its own tree position. | Posted → Edited* → Deleted |
| **Reaction** (like, heart, clap, upvote) | Per-user × per-post idempotent toggle. Tiny separate aggregate or relationship row. | Added → Removed |
| **Repost / Quote / Share / Retoot** | Distinct aggregate that *references* the original but never mutates it. Quote-posts add their own body. | Created → Deleted |
| **Follow / Subscribe** | Directed edge in the social graph. Its own aggregate so block/mute lifecycle is independent. | Followed → Unfollowed |
| **Block / Mute / Restrict** | Per-user-pair safety state; shapes fan-out and read filtering. | Added → Removed |
| **Direct Message thread** | Channel-style aggregate; see sibling `chat-and-messaging.md`. | Opened → Active (no natural close) |
| **Timeline / Home Feed** | **NOT an aggregate.** Per-user projection over many post streams. | n/a |
| **Engagement counters** | Like/view/repost counts. Sharded counters, never replayed cell-by-cell from raw events. | n/a (projection) |
| **Moderation action** | Takedown, flag, label, shadow-ban. References content; does not mutate the original Post. | Filed → Reviewed → Upheld/Reversed |
| **Notification** | Per-user inbox of "X liked your post". Projection from cross-aggregate events. | n/a (projection) |

The rule (Vernon, [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf)): one transactional consistency boundary per aggregate. A "like" therefore touches two aggregates (the Reaction record and a counter projection), never the Post — otherwise the Post stream becomes the bottleneck for every viral tweet.

### Why Timeline ≠ Post stream

A user's home timeline is *derived* from the union of `post-{postId}` streams across everyone they follow, ranked and filtered by their own signals. Twitter's Redis home timeline cache, Facebook's News Feed leaf indexes, Instagram's pre-computed inbox, and Mastodon's home feed are **all projections** — different in implementation (push vs pull vs hybrid) but identical in role. Conflating "Post" and "Timeline" is the canonical social-feeds modelling mistake.

## 2. Stream-id naming patterns

```
user-{userId}                              # profile aggregate
user-{userId}-posts                        # per-author post emission stream (append-only)
post-{postId}                              # per-post stream: edits, pins, visibility, deletion
post-{postId}-engagement-{shardKey}        # sharded engagement stream for hot posts
comment-{commentId}                        # Reddit/threaded-comment style
reaction-{userId}-{postId}                 # idempotent per-pair (often a row, not a stream)
repost-{repostId}                          # quote/retweet/share/retoot
follow-{followerId}-{followeeId}           # graph edge
block-{userId}-{targetId}
moderation-{caseId}                        # takedowns, flags
notification-{userId}                      # projection inbox

# Projections (built FROM streams above, NEVER appended to as aggregates):
feed-{userId}                              # home timeline inbox (push model)
feed-{userId}-{yyyyMMdd}                   # time-bucketed inbox for cold archival
profile-feed-{userId}                      # "your posts" view on the profile page
trending-{topic}-{yyyyMMddHH}              # bucketed trending projection
```

**Time-bucketing the inbox** (`feed-{userId}-{yyyyMMdd}`) bounds an otherwise unbounded per-user feed; old buckets cold-archive (see [unbounded streams §B](../unbounded-and-infinite-streams.md#b-long-running-conversations--activity-timelines--no-end-of-life)). Twitter keeps ~800 entries per Redis-cached home timeline ([How Twitter Uses Redis to Scale](https://highscalability.com/how-twitter-uses-redis-to-scale-105tb-ram-39mm-qps-10000-ins/)) — the bound is a product decision; older entries are recoverable by replaying author streams.

**BlueSky / AT Protocol** is the odd one out: a literal per-user signed commit log. Stream ID is the user's DID; records addressed as `at://{did}/{collection}/{rkey}` — see §6.

## 3. Key events per aggregate

### Post
```
PostDrafted              { postId, authorId, body, mediaRefs[], visibility, draftedAt }
PostPublished            { postId, authorId, body, mediaRefs[], visibility, inReplyTo?, publishedAt }
PostEdited               { postId, newBody, editedAt, editReason? }   # X "edit", Mastodon Update
PostVisibilityChanged    { postId, fromVisibility, toVisibility }
PostPinned               { postId, pinnedAt }
PostDeleted              { postId, deletedAt, deletedBy }
PostTombstoned           { postId, reason }                            # GDPR / takedown — body scrubbed
PostLabelApplied         { postId, label, byActor }                    # community notes / content label
```
The original `PostPublished` is never mutated — `PostEdited` is appended. Mastodon emits ActivityPub `Update` activities for federation.

### Reaction, Repost, Follow, Moderation
```
ReactionAdded            { userId, postId, kind, addedAt }       # kind = like/heart/laugh/upvote
ReactionRemoved          { userId, postId, kind, removedAt }

PostReposted             { repostId, originalPostId, byUserId, repostedAt }
PostQuoted               { repostId, originalPostId, byUserId, quoteBody, snapshotOfOriginal }
RepostUndone             { repostId, undoneAt }

UserFollowed             { followerId, followeeId, followedAt }
UserUnfollowed           { followerId, followeeId, unfollowedAt }
UserBlocked              { userId, blockedUserId, blockedAt }
UserMuted                { userId, mutedUserId, scope }                # full / posts-only / reposts-only

ContentReported          { reportId, reporterId, postId, reason, reportedAt }
ContentLabelApplied      { postId, label, byActor, basis }
ContentTakedownOrdered   { postId, basis, byActor, takedownAt }        # legal / TOS
ContentShadowBanned      { postId, scope, reason }                     # visibility-limited, not deleted
UserSuspended            { userId, duration, reason }
```
Moderation is a **separate aggregate** that references but never mutates Post events. A takedown emits `ContentTakedownOrdered` plus flips visibility in the projection — the original `PostPublished` stays in the post stream for audit replay.

### Engagement counters (projection-emitted)
```
LikeCountSnapshotted     { postId, count, asOf, shardId }
ViewCountSnapshotted     { postId, count, asOf }
RepostCountSnapshotted   { postId, count, asOf }
```
Emitted by the counter rollup job, not commands on the post. See §5.

## 4. Fan-out / fan-in — the asymmetric write amplification problem

The single most-quoted social-platform tradeoff.

### 4.1 Fan-out-on-write (push) vs fan-out-on-read (pull)

**Push**: each `PostPublished` triggers a fan-out worker that pushes postId into every follower's `feed-{userId}` inbox. Twitter: each tweet by a typical user produces "as many as 20K inserts… across the Redis cluster" ([How Twitter Uses Redis to Scale](https://highscalability.com/how-twitter-uses-redis-to-scale-105tb-ram-39mm-qps-10000-ins/)). Reads become trivially fast; writes get *very* expensive for high-follower accounts.

```
Command: PublishPost(authorId, body, mediaRefs, visibility)
  -> Post aggregate emits PostPublished
  -> FanOutOnWriteService: lookup followers, for each push to feed-{followerId}
  -> emit FeedFanOutCompleted(postId, followerCount, durationMs)
```

**Pull (celebrities)**: above a threshold (Instagram tuned ~10K-100K; varies), push is abandoned. On read the timeline service queries the user's "celebrity follows" and **merges** with the pre-computed inbox.

```
Read: GetHomeTimeline(userId)
  -> A = feed-{userId}.last(N)                          # push-side inbox (normal authors)
  -> celebrityFollows = followers(userId) ∩ celebritySet
  -> B = for each celebrityId: post-{celebrityId}-recent.last(M)
  -> merge(A, B) by score/time, dedupe, filter blocked/muted
```

This is the **"celebrity problem"** — every major platform's hybrid (push below threshold, pull above) is how they avoid pushing one post to hundreds of millions of inboxes ([Designing Instagram](https://highscalability.com/designing-instagram/); [Instagram: From Redis to Cassandra and Rocksandra](https://sujeet.pro/articles/instagram-cassandra-migration)).

### 4.2 What each major platform actually does

| Platform | Approach |
|---|---|
| **Twitter/X** | Push to Redis home timeline (Haplo cache) for normal follows; high-follower accounts merged at read; ranker layered on top ([High Scalability — Twitter](https://highscalability.com/the-architecture-twitter-uses-to-deal-with-150m-active-users/)) |
| **Instagram** | Pre-computed inbox in Cassandra (Rocksandra) for normal authors; celebrity posts fetched on read ([Designing Instagram](https://highscalability.com/designing-instagram/)) |
| **Facebook** | Multifeed *leaf* indexes recent friend actions in memory; *Aggregator* fetches & ranks per-user on read ([Serving Facebook Multifeed](https://engineering.fb.com/2015/03/10/production-engineering/serving-facebook-multifeed-efficiency-performance-gains-through-redesign/); [ML News Feed ranking](https://engineering.fb.com/2021/01/26/core-infra/news-feed-ranking/)) |
| **Mastodon** | `FanOutOnWriteService` pushes to followers' Redis home feeds; remote deliveries batched via `ActivityPub::DeliveryWorker` ([Mastodon Timeline & Feed Management](https://deepwiki.com/mastodon/mastodon/4-timeline-and-feed-management)) |
| **TikTok** | Almost entirely pull-side; candidate retrieval + Monolith ranker over an interest graph ([Monolith — ByteDance](https://medium.com/@chidubemndukwe/monolith-by-tiktok-bytedance-d53ee4e0dfd0)) |
| **Pinterest** | Pull, real-time random-walk candidate generation (Pixie) on the object graph ([Pixie paper](https://arxiv.org/abs/1711.07601); [Pinterest Engineering](https://medium.com/pinterest-engineering/introducing-pixie-an-advanced-graph-based-recommendation-system-e7b4229b664b)) |
| **LinkedIn** | Activity stream (Kafka) into offline + online pipelines; feed built via batch + online merges; ranking-dominated ([The Log — Jay Kreps](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying)) |
| **Reddit** | Pull: candidate pool from subscribed subreddits, ranked per-request; hot/comment trees cached in Redis ([Designing Reddit From Scratch](https://designgurus.substack.com/p/how-to-design-reddit-in-45-mins)) |

Recommendation-driven feeds (TikTok, Pinterest, modern X "For You", FB News Feed) have effectively abandoned the follow graph as the *primary* signal. The post stream is still per-author and immutable; what changed is which projection wins eyeballs.

### 4.3 Reaction storm, quote chain, notification fan-in

A viral post receives 10M+ likes in an hour. Naive `Post` aggregate writes serialise through one optimistic-lock stream — collapse. Universal pattern: the Post aggregate is **never written to** by a like. The like is its own aggregate; the count is a sharded projection (§5).

```
LikeButton clicked
  -> ReactionAdded { userId, postId, kind }   # tiny per-user-per-post aggregate, idempotent
  -> async: increment sharded counter shard{hash(userId) % N}
  -> periodic rollup: sum shards → publish LikeCountSnapshotted(postId, count, asOf)
```

Repost / quote chains:
```
A: PostPublished(p1)
B: PostReposted(r1 -> p1)
C: PostQuoted(q1 -> p1, quoteBody, snapshotOfP1AtQuoteTime)
A: PostEdited(p1, newBody)
A: PostDeleted(p1)
```
C's quote remains coherent because it captured a snapshot at quote-time; without it, deleted-quote-tweets render as "this post is unavailable" stubs.

Notifications are the *inverse* fan-out: many event streams (`ReactionAdded`, `PostReposted`, `UserFollowed`, comments) collapse into one per-recipient projection, with coalescing rules ("X and 12 others liked your post"). See [`../../implementation-patterns/multi-aggregate-commands-and-sagas.md`](../../implementation-patterns/multi-aggregate-commands-and-sagas.md) and [`../../implementation-patterns/subscription-checkpoints-and-ordering.md`](../../implementation-patterns/subscription-checkpoints-and-ordering.md) for the underlying patterns.

## 5. Algorithmic vs chronological feeds — same input, different projections

The *same* `post-{authorId}` streams feed multiple projections:

| Projection | Inputs | Sort/filter |
|---|---|---|
| **Chronological "Following"** | union of `post-{a}` for a ∈ follows(user) | reverse-chronological, filter blocks/mutes |
| **Algorithmic "For You" / "Home"** | candidate pool from follows + recommended + topic | ranked by ML model on per-user signal vector (Twitter's "Heavy Ranker", FB's News Feed ranker) |
| **Lists** | union of `post-{a}` for a ∈ list(listId) | chronological within the list |
| **Per-topic / hashtag** | `post-{*}` filtered by `hashtags` projection | chronological or ranked |
| **Trending** | aggregated engagement velocity over `ReactionAdded`/`PostReposted` bucketed by topic & time | top-K by velocity |
| **Profile timeline** | `user-{userId}-posts` only | reverse-chronological |

The algorithmic feed is the canonical "projection that depends on per-user state" — the score function `f(post, user, context)` means *no two users see the same feed*, so caching is per-user. **Never derive the feed by replaying the union of post streams at read time without a candidate-generation step** — for a user following 1000 active accounts that's 30K+ events/month per render.

### Counters at scale

Likes, views, reposts, impressions, comment counts: **always projected, eventually consistent, never computed by scanning the raw event stream on read.** Most-violated rule in greenfield designs. Patterns:

- **Sharded counters**: one logical counter is N physical counters keyed by `shardId = hash(userId) % N`. Reads sum the shards; writes increment one shard ([Distributed Counter System Design](https://systemdesign.one/distributed-counter-system-design/)).
- **Approximate counters**: view counts often from sampled impression logs, not exact per-impression rows. "1.2M views" is approximate; "12 likes" is exact.
- **Counter snapshots**: periodic `LikeCountSnapshotted` events feed the read-side cache; raw `ReactionAdded` stream is the source of truth.
- **Idempotency**: `ReactionAdded` keyed by `(userId, postId, kind)` so double-clicks/retries don't inflate counts.

Twitter accepts eventual consistency on counters explicitly. The cost of strong consistency on a viral-tweet counter would be a write-lock storm that takes the timeline service down.

## 6. Edits, deletes, "right to be forgotten", and quote coherence

The hardest design surface because immutability collides with platform policy *and* legal obligations.

**Edits.** X, Mastodon, Facebook, LinkedIn all support edit. `PostPublished` is never mutated; subsequent `PostEdited` events form the revision chain. Reads project the *latest* body; revision history shown to the user is a projection over the chain.

**Deletes.** A `PostDeleted` event marks the post invisible; projections filter it. The event itself is *not* removed — historical replay would otherwise be broken. ActivityPub propagates deletes via `Delete` activities to all known remote inboxes; this is best-effort.

**Right to be forgotten (GDPR Art. 17)** conflicts directly with immutability. Two production strategies (rarely combined):

1. **Tombstoning** — event stays, payload scrubbed (body, media refs, mentions). A `PostTombstoned { postId, reason }` is appended; projection replaces body with `[content removed]`. See [Events are forever… until they're not](https://carnage.github.io/2018/10/events-are-forever) and [Event Sourcing for GDPR](https://dev.to/alex_aslam/event-sourcing-for-gdpr-how-to-forget-data-without-breaking-history-4013).
2. **Crypto-shredding** — PII fields encrypted per-user with a per-user key; "forget" means deleting the key, making historical events unreadable but structurally intact ([HashiCorp Vault — GDPR-Compliant ES](https://www.hashicorp.com/en/resources/gdpr-compliant-event-sourcing-with-hashicorp-vault)).

**Quote-of-deleted-content.** Quote aggregate captures a snapshot at quote-time (§4.5). After the original is tombstoned, the snapshot may itself need scrubbing — chained delete-propagation across reposts/quotes is its own saga. X shows "This post is from a suspended account" when the original is gone; the quote's `quoteBody` (the quoter's added text) remains.

## 7. BlueSky / AT Protocol — event sourcing in production at the user level

BlueSky's AT Protocol is the closest mainstream production deployment of pure per-user event sourcing visible from the outside. Each user has a **repository** ("repo") stored on a Personal Data Server (PDS) — literally a signed append-only log of records:

- The repo is a content-addressed Merkle Search Tree of records; each mutation produces a new **commit** signed by the user's keypair ([AT Protocol — Repository spec](https://atproto.com/specs/repository)).
- Records addressed as `at://{did}/{collection}/{rkey}`, e.g. `at://did:plc:abc/app.bsky.feed.post/3jzfcijpj2z2a`.
- A repo can be exported as a single CAR file — the entire user history in a portable, verifiable artefact.
- Commits chain via `prev`; the repo is causally a DAG.
- The PDS broadcasts a **firehose** of commits to Relays which downstream consumers (AppView servers, third-party feed generators) subscribe to. The home timeline on bsky.app is computed by an AppView consuming this firehose.

This maps 1:1 to ES vocabulary: per-user repo is a stream; commits are events; the AppView is a projection; Relays are the message bus. BlueSky has [debated whether to allow repo history truncation](https://github.com/bluesky-social/atproto/discussions/1410) — the same unbounded-stream tension every archetype-B domain hits.

Consequence: **portability is a first-class property**. A user can move PDS providers and bring their full signed history; consumers can re-verify any record against the user's DID. Compare to Twitter, where an export is a tarball with no cryptographic chain of custody.

## 8. Mastodon / ActivityPub — events across instance boundaries

ActivityPub-based platforms (Mastodon, Pleroma, Pixelfed, Akkoma) treat publishing as emission of an `Activity` object (`Create`, `Update`, `Delete`, `Like`, `Announce` = boost, `Follow`) POSTed to every interested remote inbox.

- **FanOutOnWriteService** pushes locally and queues remote deliveries via `ActivityPub::DeliveryWorker` batched per remote inbox ([Mastodon DeepWiki — Timelines](https://deepwiki.com/mastodon/mastodon/4-timeline-and-feed-management)).
- **`Update` activities** federate edits; older instances may show stale versions.
- **`Delete` activities** federate deletes; non-cooperating instances may retain the post — *the* unsolved-by-design federation hazard.
- **StatusReachFinder** computes which remote inboxes should receive an activity (followers + mentions + reblog audiences).

Each instance is an autonomous event store; cross-instance federation is multi-master, best-effort replication with no global ordering — archetype E ("branching / non-linear histories") in [unbounded streams](../unbounded-and-infinite-streams.md#e-branching--non-linear-histories). Each instance has its own causal history; merge happens by activity replay, not by stream concatenation.

**Cross-posting between platforms** (a user posting to X, Mastodon, BlueSky, LinkedIn simultaneously via Buffer/Hootsuite/Typefully) is the consumer-side of the same multi-master problem: each platform is its own event stream and aggregate root; there is no shared identity across them. Edits and deletes on the source must be fanned out to each target, and each platform supports a different subset (X edit is paid + short window, Mastodon allows edit, BlueSky allows delete-and-repost, LinkedIn allows edit).

## 9. Real-world gotchas

1. **The 99% read-cache hit rate is the actual product.** Twitter's home timeline cache hits 99%+ because users refresh constantly. Plan capacity for cache-warming on cold start, not for cold reads ([How Twitter Uses Redis to Scale](https://highscalability.com/how-twitter-uses-redis-to-scale-105tb-ram-39mm-qps-10000-ins/)).
2. **Celebrity threshold is dynamic.** Instagram tuned around 10K-100K; shifts with infra capacity and follower-distribution skew. Treat as runtime config, not constant.
3. **Block filters the inbox at read, not deletes.** If A blocks then unblocks B, A expects to see B's posts again. Deleting from the inbox on block means lossy rebuild on unblock.
4. **Mute is per-user, per-scope.** "Mute reposts of X" ≠ "mute X entirely". Modelling mute as a boolean misses this — see Mastodon's `mute_notifications` vs full mute.
5. **Reaction toggle race.** Fast double-tap on flaky network: aggregate is `(userId, postId, kind)`; last command's `addedAt`/`removedAt` ordering decides state. Per-click idempotency keys prevent count inflation.
6. **Counter divergence at viral velocity.** During burn the displayed like count lags reality by seconds-to-minutes. Show approximate counts ("1.2M") — deliberate UX accommodation of eventual consistency.
7. **Edit-after-quote.** A quote with snide commentary references a post that's then edited to remove the embarrassing claim. The quote now references benign content but the snark remains. Platforms diverge: X shows "(edited)" badges; Mastodon shows revision; no platform "rewrites" the quote.
8. **Federation delete is best-effort.** A `Delete` activity may fail to reach an offline/non-cooperating instance. Plan for "deleted on origin, still present on remote" as a permanent state. Same for AT Protocol — a record removed from the user's repo may persist in third-party AppView caches.
9. **Reply graph is a tree but engagement graph is not.** Comments form a tree (parent pointer per comment); reposts/likes/quote-tweets on replies form a DAG. Reddit's [comment tree storage](https://designgurus.substack.com/p/how-to-design-reddit-in-45-mins) uses Cassandra column families with a designed sort-key.
10. **Search and trending need their own append-only stream.** Don't query the post stream for search/trending. Emit `PostIndexed` to a search projection (Elasticsearch / OpenSearch) and let trending aggregate over a short-window engagement stream.
11. **Notification storms.** A user following a popular live-tweeter during a major event gets thousands of notifications. Coalesce by author / topic / time window at the *projection*, not by suppressing source events.
12. **Recommendation candidate generation is its own subsystem.** TikTok's Monolith, Pinterest's Pixie, Twitter's Heavy Ranker, FB's Multifeed are *upstream* of the timeline projection. The event store feeds them via Kafka; they don't write back. Don't try to do candidate generation inside the timeline-projection job.
13. **DM threads belong in chat, not feeds.** Direct messages have message-delivery semantics (read receipts, delivery acks, E2E encryption) closer to chat — see sibling [`chat-and-messaging.md`](chat-and-messaging.md).

## 10. Sources & case studies

- **Twitter / X** — [Architecture for 150M Active Users](https://highscalability.com/the-architecture-twitter-uses-to-deal-with-150m-active-users/); [How Twitter Uses Redis to Scale](https://highscalability.com/how-twitter-uses-redis-to-scale-105tb-ram-39mm-qps-10000-ins/); [Manhattan distributed KV store](https://blog.twitter.com/engineering/en_us/a/2014/manhattan-our-real-time-multi-tenant-distributed-database-for-twitter-scale).
- **Facebook / Meta** — [Serving Facebook Multifeed](https://engineering.fb.com/2015/03/10/production-engineering/serving-facebook-multifeed-efficiency-performance-gains-through-redesign/); [How ML powers News Feed ranking](https://engineering.fb.com/2021/01/26/core-infra/news-feed-ranking/); [TAO paper summary](https://www.micahlerner.com/2021/10/13/tao-facebooks-distributed-data-store-for-the-social-graph.html).
- **Instagram** — [Designing Instagram](https://highscalability.com/designing-instagram/); [From Redis to Cassandra and Rocksandra](https://sujeet.pro/articles/instagram-cassandra-migration).
- **LinkedIn / Kafka** — Jay Kreps, [The Log](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying); [Kafka's origin story at LinkedIn](https://www.linkedin.com/pulse/kafkas-origin-story-linkedin-tanvir-ahmed).
- **TikTok / ByteDance** — [Monolith real-time recommendation](https://medium.com/@chidubemndukwe/monolith-by-tiktok-bytedance-d53ee4e0dfd0).
- **Pinterest** — [Pixie paper (arXiv)](https://arxiv.org/abs/1711.07601); [Introducing Pixie — Pinterest Engineering](https://medium.com/pinterest-engineering/introducing-pixie-an-advanced-graph-based-recommendation-system-e7b4229b664b).
- **Reddit** — [Designing Reddit From Scratch](https://designgurus.substack.com/p/how-to-design-reddit-in-45-mins).
- **BlueSky / AT Protocol** — [Repository spec](https://atproto.com/specs/repository); [Personal Data Repositories guide](https://atproto.com/guides/data-repos); [Bluesky PDS GitHub](https://github.com/bluesky-social/pds); [Intention to remove repository history](https://github.com/bluesky-social/atproto/discussions/1410).
- **Mastodon / ActivityPub** — [Mastodon ActivityPub docs](https://docs.joinmastodon.org/spec/activitypub/); [Mastodon Timeline & Feed Management (DeepWiki)](https://deepwiki.com/mastodon/mastodon/4-timeline-and-feed-management).
- **Counters & GDPR** — [Distributed Counter System Design](https://systemdesign.one/distributed-counter-system-design/); [Events are forever… until they're not](https://carnage.github.io/2018/10/events-are-forever); [Event Sourcing for GDPR](https://dev.to/alex_aslam/event-sourcing-for-gdpr-how-to-forget-data-without-breaking-history-4013).
- **DDD** — Vernon, [Effective Aggregate Design Pt II](https://www.dddcommunity.org/wp-content/uploads/files/pdf_articles/Vernon_2011_2.pdf).

## 11. Open questions

- Fan-out thresholds at Instagram and Twitter are community-inferred; published values are illustrative, not current production config. "~10K-follower threshold" is the right shape, not a literal.
- Twitter/X engineering posts thinned post-2022; recent changes ("For You" ranking, Grok integration) are visible only through product behaviour and reverse-engineering writeups.
- Reddit's vote-counting internals come from third-party writeups; canonical engineering posts are old and large parts of the stack have been rewritten.
- Cross-posting tools (Buffer/Hootsuite/Typefully) don't publish internal data models — §8 is reasoned from the API shape they consume.
