# POST-EV2-6 — Whole-project retrieval + hydration admission

POST-EV2-6 supplies broad **older/project-wide** story retrieval without making
retrieval a new truth owner, visibility engine, save path, or RHC front door.

The core flow is deliberately small:

> **SEARCH → CANDIDATE RECEIPT → HYDRATION ADMISSION → BOUNDED EXCERPT**

## Why the architecture is split this way

The first POST-EV2-6 candidate tried to combine broad search with a generic
Markdown/JSON META/NON_META interpreter. That created an open-ended parser:
section headings, bullets, nested JSON, inheritance and byte ordering all became
retrieval responsibilities.

That was the wrong ownership boundary.

knowledge/META_NON_META_PROTOCOL.md owns visibility semantics. Existing source
domains own their structure. POST-EV2-6 consumes only visibility evidence that is
safe to state without inventing new semantics.

## Search wide, hydrate narrow

The searchable V1 corpus is repository-derived and includes declared story roots
such as Canon/Played History, characters, NPCs, villains, locations, inventory,
knowledge, BTH, plans and brainstorm material.

Search discovery never promotes anything. Every hit keeps:

- source path;
- source class;
- authority (canon, canon_backstage, non_canon);
- exact content SHA-256;
- conservative whole-source visibility evidence;
- admission reason.

The generated manifest is derived, rebuildable and non-authoritative.

## Hydration profiles

### dm

DM retrieval may search and hydrate every declared source class. META,
non-canon and brainstorm material remain labelled as such and never become canon
or character knowledge.

### authoritative

Ordinary player-safe/authoritative hydration is intentionally conservative.

A source is admitted only when:

1. its authority is not non_canon; and
2. the source provides **unambiguous whole-source NON_META evidence**.

If visibility is mixed, nested, inherited in a way that would require generic
interpretation, or simply absent, the source is **not admitted** to this profile.

That source may still be discoverable/hydratable for the DM.

This is safe incompleteness by design. POST-EV2-6 does not invent a second
repository-wide visibility resolver merely to retrieve more text.

## Conservative evidence rules

### Markdown

A Markdown file is player-safe as a whole only when a top-level
Visibility: NON_META declaration appears in its header area and **no META
visibility marker appears anywhere in the file**.

Any mixed section/bullet classification makes the file DM-only for V1
authoritative hydration. Retrieval does not attempt to calculate section scope.

### JSON

A JSON file is player-safe as a whole only when the root explicitly declares
visibility: non_meta or default_visibility: non_meta and **no META
visibility appears anywhere in the JSON tree**.

Mixed/nested JSON is DM-only for V1 authoritative hydration. Retrieval does not
invent record inheritance or subtree redaction semantics.

## Freshness

The manifest contains the exact indexed path set, classification, authority,
whole-source admission evidence and per-source SHA-256.

Freshness is recomputed from the current declared source set. Therefore:

- indexed source edit/add/remove makes the manifest stale;
- an unrelated engineering file does not;
- a tampered manifest cannot become fresh merely by recomputing its own
  fingerprint, because current source truth is independently rebuilt and
  compared;
- each file is digest-checked again at hydration time, so a source change after
  the freshness pass fails the query closed;
- stale/tampered/unavailable retrieval never treats a zero result as proof of
  semantic absence.

## Relationship to POST-EV2-5

POST-EV2-5 remains the only current published-world exact-focus search:
public.dm_current_search(...).

POST-EV2-6 does not recreate or wrap that runtime search. It exists for broader
repository/history discovery.

## Explicit non-goals

POST-EV2-6 does not:

- become the RHC Dropgate or orchestration center;
- implement a generic atomic visibility parser;
- rewrite mixed repository content for retrieval;
- mutate campaign truth;
- add Supabase/runtime SQL;
- implement external web/lore lookup;
- implement Day Start;
- implement POST-EV2-7 COLD archive;
- perform Gate 36 bulk intake;
- add UI;
- commit generated manifests.

**Search wide. Admit explicitly. Hydrate narrowly.**
