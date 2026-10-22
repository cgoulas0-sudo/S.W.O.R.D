# POST-EV2-4B — Reality inheritance + explicit divergence foundation

POST-EV2-4B adds the smallest repository foundation for **explicit canonical
reality identity**, **parent lineage**, and **inheritance-by-default** semantics.
It is identity + inheritance-contract foundation only: it adds no runtime/Supabase
mutation surface, no generic reality-state copy engine, and no per-reality
subject-availability list.

> Architecture sentence: **One engine; many histories. A reality is an identity
> with an explicit parent, and a child reality is its parent unchanged unless an
> explicit divergence later says otherwise through the real owning domain.**

## The model

RHC has one canonical tabletop continuity with one explicit root reality:

- `reality:rhc-primary` — the root primary reality; declares no parent. It is
  RHC's current canonical example of the structural root role.

The root reality is a **structural role, not a fixed identity**: it is the unique
admitted record that declares no `parent_reality_id`. Any valid
`reality:<lower-slug>` id may serve as the root of a campaign, so a clean/new
campaign may initialize a different valid root reality id without editing or
forking the engine. Exactly one parentless root must exist.

An alternate history is explicitly authored, names one admitted parent reality,
and begins as **parent + zero divergences**:

- `reality_id` — stable identity using the strict grammar `reality:<lower-slug>`
  (`[a-z0-9]+(-[a-z0-9]+)*`). The `reality:` prefix is outside the eight Entity V2
  identity types.
- `display_name` — human-readable name.
- `parent_reality_id` — required on an alternate reality, forbidden on the root.

Parent lineage is explicit, resolves to an admitted reality, and is acyclic.
Anything not explicitly diverged remains inherited unchanged.

### What reality identity does NOT do

- It does **not** create a per-reality availability/scoping list. Unchanged
  inherited subjects do not need to be re-declared per reality.
- It does **not** clone, remove, rewrite or scope any
  Entity/Hook/Scenario/Encounter/Run/system definition.
- It does **not** mint reality-specific duplicate entity IDs or copy rules/catalog
  definitions (including ability/status-effect definitions). Entity V2 identity
  and catalog definitions remain global.
- It does **not** mutate the parent/source reality merely because a child exists.
- It does **not** infer lineage from similar names, dates, planes or Runs.

## Inheritance first

**A different reality means a different history because an explicit divergence
exists or may exist — not because inherited content was exhaustively re-scoped.**

The concrete laws are:

1. A child reality begins as parent + zero divergences.
2. Anything not explicitly diverged remains inherited unchanged.
3. Reality identity alone creates no new copy of any Entity/Hook/Scenario/
   Encounter/Run/state/system definition.
4. A future divergence is represented through the real owning domain/lane, not
   through a generic 4B truth blob.
5. A child-reality divergence never mutates its parent/source reality merely by
   existing.

## Rejected design scar: availability-scope

Retired PR #143 / JOHNNY #142 modeled a reality as a **subject availability /
scoping** list. That abstraction asked the wrong question — it implied that
unchanged inherited subjects must be re-declared per reality, which inverted the
inheritance model and caused repeated validator holes about whether unchanged
characters, locations, spells, abilities, Hooks, etc. "exist" in each reality.
Its review findings were useful evidence of that abstraction leak, but **review
severity is not scope and cannot create product semantics**.

POST-EV2-4B deliberately rejects that abstraction:

- no `reality_scope.schema.json` or equivalent renamed subject-availability
  machinery;
- no exhaustive "what exists in this reality?" list;
- no generic `reality_override` truth blob.

## Trust boundaries

- Reality records are repository-authored control/canon metadata.
- Reality IDs are not self-certified by callers; the registry admits them.
- A validator may reject invalid reality identity/lineage, but it may not invent
  a divergence, copy state, remove inherited content, or promote external
  material to canon.
- Existing owner systems remain authoritative for actual subject facts and state;
  4B is not a second owner for character sheets, locations, inventory, status,
  knowledge, Hooks, Scenarios, Encounters, Runs, abilities or rules.

## Traveler return / carry-out (boundary)

This Mission leaves the carry-out door open without implementing it:

- Leaving a reality does not automatically merge that reality into its parent.
- Leaving a reality does not automatically erase everything that happened to the
  traveler.
- A **later** consumer Mission may explicitly authorize selected consequences
  (applied status/timer, knowledge, Hook, inventory/state, or another owner-valid
  consequence) to travel with an entity through their real owners.
- No carry-out happens merely because 4B exists, and no automatic leak-back or
  blanket reset-on-return law is established here.

## External continuity

External PREQUEL / SEQUEL / disposable simulations remain non-canon and
separately owned. Reality identity grants no external content canon authority;
content is admitted only through existing canon authority.

## Relationship to POST-EV2-4A

POST-EV2-4A owns lane-scoped world-calendar/timespace **placement inside one
canonical reality**. Ordinary RUN creation, Unknown chronology, time travel,
plane travel and timespace travel are **not** automatic reality creation.
Reality identity is a separate axis: 4A places a lane in time/timespace; 4B names
which history that lane belongs to. Neither mints content or state.

## Repository surfaces

| Surface | Purpose |
| --- | --- |
| `schemas/reality.schema.json` | Reality identity + explicit parent schema |
| `scripts/validate_realities.py` | Identity/uniqueness/resolution/acyclicity proof |
| `realities/README.md` | Registry contract and inheritance-by-default |
| `realities/registry/rhc-primary.json` | The one root primary reality |
| `tests/test_reality_inheritance.py` | Bounded proof |
| `tests/fixtures/realities/valid/*` | Synthetic proof fixtures |

No runtime/Supabase migration, schema, route or `temporal_positions` change is
made. Existing Entity/Hook/Scenario/Encounter/Run schemas are unchanged. Patch 1A
and Patch 1B are unchanged.

## Deferred ownership

Later consumer Mission(s), only when actual play/product use requires them:

- owner-specific reality overlays/divergences for character/entity/location/story
  state;
- runtime registry/read of the active reality;
- explicit cross-reality lane transition;
- reality-qualified mutable state where genuinely required;
- explicit traveler carry-out/reconciliation through existing owner routes;
- counterpart/divergence handling for simultaneous mutable versions;
- reality-aware retrieval/RAG;
- alternate-history merge/reconciliation/paradox policy;
- UI controls.

Disposable PREQUEL / SEQUEL / What-If lab architecture remains with POST-EV2-8.
