# POST-EV2-5 — Current published-world exact-focus search

`public.dm_current_search(<focus>, <limit>)` is the POST-EV2-5 read capability: a
small, service-only, exact-focus search engine over the **current published
world**. It is wiring, not a new truth system. It reuses the existing engine
owners and adds no persistence, mutation route, validator framework, cache,
index, graph/vector store, generic query language, or second state reader.

The public contract:

```
public.dm_current_search(p_focus text, p_limit integer default 20) -> jsonb
```

- one stable entity-like focus per call: `character:` / `creature:` /
  `location:` / `faction:` / `party:` / `item:`;
- `p_limit` defaults to `20` and is clamped to `[1, 50]`;
- output carries the trusted RT01-D published generation / exact-ref metadata,
  the exact focus, and bounded current hits grouped by owning domain, with
  explicit per-domain truncation metadata;
- IDs found inside hits are never recursively hydrated.

## Core rule

**Search decides relevance. Existing engine owners decide validity.**

For one exact focus the read:

1. reads ONLY the current published namespace(s) that can contribute to that
   focus kind, each fetched individually by its exact runtime key — the whole
   published generation is never aggregated and filtered later (selective read
   path);
2. validates each namespace through its EXISTING owning whole-collection
   validator / canonical published read, including the owner's declared
   cross-collection law (below);
3. only after validation, filters by the owner's exact stable
   identity/relation fields;
4. returns bounded matching hits.

A malformed authoritative namespace fails closed through its owner contract.
POST-EV2-5 does not invent a weaker per-record validation path. Only
`campaign_runtime.published_generation` is read: a staged/future generation is
never the read authority.

## Authoritative owner contracts consumed

| Domain | Owner contract reused |
| --- | --- |
| `entity_state` | `_rhc_validate_entity_state_collection` |
| `inventory` | `_rhc_validate_inventory_collection` |
| `item_custody` | `_rhc_validate_item_custody_collection` |
| `item_admissions` | `_rhc_validate_item_admissions_collection` plus the existing EV2-12.1 cross-collection law `_rhc_validate_item_admission_custody_linkage` (every admission receipt requires exactly one matching custody record for the same `item_id`; receipt-without-custody fails closed) |
| `applied_statuses` | `_rhc_validate_applied_statuses_collection` |
| `entity_knowledge` | `_rhc_validate_knowledge_collection` |
| `runs` | existing canonical published Run truth reader (RT03/EV2-08 validation path; no Run validation or uniqueness rule is duplicated) |

An owner contract is reused whole, including its declared cross-collection
invariants: an admission receipt whose custody linkage is missing fails closed
through the existing EV2-12.1 law even when both collections are individually
valid, and the one-directional legacy asymmetry (custody-without-receipt) stays
allowed.

## V1 routing (exact relations only)

Routed namespaces per focus kind, and the exact relation field(s) that create a
hit:

| Focus kind | Namespaces read | Exact relation field(s) |
| --- | --- | --- |
| `character:` | `entity_state`, `inventory`, `item_custody`, `applied_statuses`, `entity_knowledge`, `runs` | `entity_state.entity_id`; `inventory.entity_id`; `item_custody.owner_entity_id` / `holder_entity_id`; `applied_statuses.target_entity_id` / `source_entity_id`; `entity_knowledge.entity_id`; `runs.participant_entity_ids` / `mutable_owner_entity_ids` |
| `creature:` | `entity_state`, `inventory`, `applied_statuses`, `entity_knowledge`, `runs` | `entity_state.entity_id`; `inventory.entity_id`; `applied_statuses.target_entity_id` / `source_entity_id`; `entity_knowledge.entity_id`; `runs.participant_entity_ids` / `mutable_owner_entity_ids` |
| `location:` | `inventory`, `applied_statuses`, `entity_knowledge`, `runs` | `inventory.entity_id`; `applied_statuses.source_entity_id`; `entity_knowledge.entity_id`; `runs.location_ids` |
| `faction:` | `inventory`, `applied_statuses`, `entity_knowledge` | `inventory.entity_id`; `applied_statuses.source_entity_id`; `entity_knowledge.entity_id` |
| `party:` | `inventory`, `item_custody`, `applied_statuses`, `entity_knowledge`, `runs` | `inventory.entity_id`; `item_custody.owner_entity_id` / `holder_entity_id`; `applied_statuses.source_entity_id`; `entity_knowledge.entity_id`; `runs.party_id` |
| `item:` | `inventory`, `item_custody`, `item_admissions`, `applied_statuses`, `entity_knowledge` | `inventory.entity_id`; `item_custody.item_id`; `item_admissions.item_id`; `applied_statuses.source_entity_id`; `entity_knowledge.entity_id` |

`applied_statuses.target_entity_id` is restricted by its own schema to
`character:` / `creature:`; for every other focus kind only `source_entity_id`
can match, exactly as the owner contract permits. `inventory` owners may be any
of the schema's allowed owner identities, so its owner `entity_id` is matched
exactly for every focus kind.

No fuzzy matching, semantic similarity, inferred relationship or recursive
traversal is performed. `entity_knowledge` always stays with the exact knower:
knowledge is never propagated to another entity or party member.

## Output

```
{
  "read_version": 1,
  "mode": "current_search",
  "focus": "<focus>",
  "runtime": { <RT01-D runtime metadata envelope> },
  "results": {
    "<owning domain>": { "hits": [ <validated current records> ],
                          "truncated": <bool> }
  }
}
```

Only domains with at least one hit appear (sparse output). Within a domain hits
are ordered by the owner's stable identity, so output is deterministic. When a
multi-hit domain has more matches than `p_limit`, the bounded hits are returned
with `truncated: true`.

## Fail-closed conditions

- malformed / unsupported focus;
- a routed namespace that is present but unreadable (not a JSON array);
- a routed namespace that fails its existing owner whole-collection contract,
  including the declared cross-collection law (an orphan `item_admissions`
  receipt with no matching custody record);
- a malformed / duplicated / ownership-conflicting published Run batch;
- `anon` / `authenticated` execution (service-only).

## Non-goals / deferred ownership

POST-EV2-5 is not a scene composer and not a second engine. It owns no state and
mutates nothing. The following remain with their later owners:

- **POST-EV2-6** — older played-history / Story / RAG retrieval, search/index
  freshness, vector/semantic retrieval decisions;
- **POST-EV2-7 (superseded planning note)** — this document originally deferred cold historical Run archive/retrieval to POST-EV2-7. POST-EV2-7 later closed zero-code after RT04 + POST-EV2-2 + RT03 + POST-EV2-5 were verified to already satisfy the intended historical Run selective-retrieval capability; no separate archive lifecycle/owner was added;
- **PLAY/Lore Gate** — external official-lore lookup;
- **Existing runtime domains** — retain all validation, mutation and semantic
  ownership of their state.

The existing compact Hook projection stays owned by current
`dm_quick_context` / PLAY behavior; POST-EV2-5 adds no Hook SQL validator or
read. `CHANGELOG.md` and `ENGINE_CHANGELOG.md` are untouched by this Mission.