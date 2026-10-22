# realities/

Repository-authored reality identity and parent-lineage registry (POST-EV2-4B).

A **reality** is one admitted history. It is identity plus explicit parent
lineage — **not** a per-subject availability/scoping list and **not** a state
copy or override payload.

## Registry contract

- The root reality is a **structural role**, not a fixed identity: it is the
  single record that declares no `parent_reality_id`. RHC's current canonical
  example is `registry/rhc-primary.json` → `reality:rhc-primary`, which declares
  no parent and remains the RHC root.
- A clean or new campaign may instead initialize a different valid
  `reality:<lower-slug>` root id without editing or forking the engine. Exactly
  one parentless root must exist.
- An alternate reality is explicitly authored and declares exactly one admitted
  `parent_reality_id`.
- Parent lineage is explicit, resolves to an admitted reality, and is acyclic.
  It is never inferred from similar names, dates, planes or Runs.
- Reality IDs use the strict grammar `reality:<lower-slug>`
  (`[a-z0-9]+(-[a-z0-9]+)*`). The `reality:` prefix is outside the Entity V2
  identity types.

## Inheritance by default

**A child reality is its parent unchanged unless an explicit divergence later
says otherwise.** Starting a new history does not require re-listing every
character, location, spell, ability, Hook, Scenario, Encounter, Run, item or
system definition, and it does not clone, remove, rewrite or reality-scope any
of them.

Reality identity alone therefore creates **no** new copy of anything. A future
divergence (a named character, location, story or state difference) must be
represented through the real owning domain, not through this registry. Owning a
reality ID grants no external content canon authority and never mutates the
parent/source reality.

## Validation

`scripts/validate_realities.py <directory> [...]` validates records against
`schemas/reality.schema.json` and enforces the batch lineage law above. See
`docs/POST-EV2-4B-REALITY-INHERITANCE.md` for the full contract and the rejected
availability-scope design it replaces.

Disposable non-canon brainstorm labs (POST-EV2-14) are **not** realities and
never register here; they are separately owned disposable scratch state, not
canonical reality identity or lineage.
