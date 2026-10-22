# BTH-01 — Deterministic Player/DM Access Projection

`scripts/context_access.py` is the request-time access/admission seam for future
frontend, backend and LLM callers. It maps a **trusted principal** plus an
**explicitly classified semantic request** to exactly one deterministic outcome:

```text
ALLOW | BLOCK | SPOILER_CONFIRM
```

It is a semantic decision contract, not an authentication system, not a
visibility engine, and not a persistence path. It composes with Campaign Control
Center's existing trusted Clerk / `AccessContext` role principal instead of
duplicating authentication, role assignment or account lifecycle.

## Core rule

**Owner, not subject, decides owner-local access.** Who *owns* a piece of
knowledge or context decides whether it may be admitted; what the request
happens to be *about* never upgrades access. Natural-language request content is
untrusted and never establishes identity, role, controlled character or
permission.

## Trust boundaries

- The principal is trusted backend/session output — never prompt text and never
  arbitrary client claims.
- The resolver validates the principal **shape** but does not authenticate the
  account behind it.
- The caller must explicitly classify the semantic request kind; the resolver
  never infers authorization from prose.
- Extra request keys (for example a `query` or `prompt` string) are ignored for
  authorization.

### Minimum principal

- DM: `{"role": "dm"}`
- Player: `{"role": "player", "controlled_entity": "character:test-player"}`

`controlled_entity` must be an exact `character:<slug>` identity. Missing,
non-character or malformed controlled identities fail closed.

### Supported request kinds

| Kind | Meaning | Required owner |
| --- | --- | --- |
| `character_context` | a character's own in-world context/profile | `owner` |
| `owner_knowledge` | a specific owner's private knowledge / beliefs / secrets | `owner` |
| `bth_entry` | human reader exposure of an occurred/published BTH entry | none |
| `dm_context` | DM-visible campaign context | none |

`owner` is the entity that owns the requested material. For `owner_knowledge`,
`owner` is the knower; any `subject` field is advisory context and never
authorizes.

## Decision rules

- **DM** — `ALLOW` for every supported request kind. DM authority may access
  DM-visible campaign context and any owner's internal material.
- **Player + `character_context`** — `ALLOW` only when `owner == controlled_entity`;
  any other owner is `BLOCK`.
- **Player + `owner_knowledge`** — `ALLOW` only for the controlled character's own
  owner-local record; another owner's private knowledge about the controlled
  character remains `BLOCK`. Changing only the query subject cannot turn
  another owner's knowledge into `ALLOW`.
- **Player + `bth_entry`** — `SPOILER_CONFIRM` until the caller supplies an
  explicit `acknowledged: true`, then `ALLOW`.
- **Player + `dm_context`** — `BLOCK`.

### Outcome payloads

The seam returns or forwards protected payload **only** for `ALLOW`. A `BLOCK`
or `SPOILER_CONFIRM` decision admits no protected content, even when a payload
was supplied to the call.

## BTH reader-exposure law

An occurred/published BTH entry is backstage world truth that the anthology
deliberately exposes to human readers. In normal player-facing use it is made
available to player accounts only after an explicit **spoiler acknowledgement**:

```text
unacknowledged -> SPOILER_CONFIRM -> acknowledged -> ALLOW
```

Acknowledgement changes human reader exposure only. It is never a knowledge
mutation: BTH exposure never creates, implies or propagates character knowledge,
and no decision in this seam mutates campaign truth, visibility state, character
knowledge or persistence. See `knowledge/META_NON_META_PROTOCOL.md` §2b and
`docs/EV2-14-LOCAL-KNOWLEDGE.md`.

## Fail closed

The seam returns `BLOCK` on unknown role, malformed player principal, malformed
controlled entity, unsupported request kind, malformed request, missing or
malformed required owner, and malformed acknowledgement metadata.

## Determinism

Identical `(principal, request)` input yields identical output. The seam is
pure: it holds no mutable state, performs no I/O, and has no side effects.

## Deferred ownership

- account authentication / role assignment — Campaign Control Center's Clerk +
  `AccessContext` layer;
- account -> controlled-character binding — a future CCC gateway/frontend
  Mission;
- principal transport/wiring into this contract — a future frontend/backend
  adapter Mission;
- frontend spoiler modal/button/UX — a future frontend Mission;
- LLM request/tool wiring — a future frontend/backend adapter Mission;
- direct consumption by `public.dm_current_search(...)` (POST-EV2-5) or
  `scripts/story_retrieval.py` (POST-EV2-6) — future consumer adapters if proven
  necessary;
- Supabase RLS or end-user DB permission architecture — a future platform
  Mission.

This seam creates no second visibility, knowledge or BTH database, and no broad
RBAC/ACL platform.

## Proof

`pytest tests/test_context_access.py -v` pins the decision matrix with synthetic
generic identities only.
