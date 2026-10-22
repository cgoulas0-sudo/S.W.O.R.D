# POST-EV2-14 — Disposable NON-CANON brainstorm lab lifecycle

POST-EV2-14 adds the smallest reusable **engine-side disposable brainstorm-lab
lifecycle** for Prequel / Sequel / What-If exploration. It is a
lifecycle/provenance contract around a caller-supplied disposable scratch root;
it is **not** a gameplay engine, a save system, a hosted campaign-slot
provisioner, or a canon-promotion path.

> Architecture sentence: **One engine; many histories; the lab is the disposable
> scratch room next to canon — it always declares NON-CANON, it is writable only
> while ACTIVE, and its only exit is a verified clean reset.**

## What a lab is

A lab is a disposable, explicitly NON-CANON exploration rooted at a
caller-supplied scratch root outside canonical campaign/runtime authority. It
is opened from an **exact trusted origin/checkpoint receipt**, and it records
two separate concepts:

- **origin provenance** — a stable campaign identity plus a
  checkpoint/revision identity supplied by the trusted caller/platform;
- **narrative mode + anchor** — how the DM wants to explore (Prequel / Sequel /
  What-If) and the narrative anchor that names the exploration.

Mode/anchor and origin provenance are deliberately distinct: the lab's
lifecycle authority comes from the exact origin, its intent comes from the
human/DM.

## Lifecycle

```
CLEAN -> ACTIVE -> CLOSED(completed|aborted) -> TOMBSTONED/RESETTING -> CLEAN
```

- `begin` requires a clean baseline and writes the single lab lock declaring
  `non_canon: true`, the mode/anchor, and the origin provenance.
- exactly **one active lab per campaign/lab root (V1)**; a second `begin` is
  refused while a lab exists.
- `ACTIVE` is writable **through the lab guard only**.
- `close(completed|aborted)` freezes the lab one-way. A closed lab stays
  readable/inspectable; every lab write is refused. Repeating the same close is
  idempotent; a conflicting outcome is refused.
- `reset` may clean `ACTIVE` or `CLOSED`. It is proven as **one recoverable
  transaction**, not a set of patched crash windows. The transaction uses one
  bounded recovery record and one fixed artifact, both inside the lab root:
  - `reset.pending.json` — the durable recovery journal, written **before** any
    destructive step;
  - `active.tombstone` — the single fixed kernel-owned tombstone that
    `active/` is atomically renamed to **before** it is deleted;
  - `last-reset.json` — the single latest reset receipt.

  Reset durably writes (or resumes) the journal, renames `active/` to the fixed
  tombstone, deletes it, durably commits `last-reset.json` (validating rather
  than rewriting a receipt that already carries this transaction's `reset_id`),
  and only then removes the lock and the journal. It then proves a clean
  baseline structurally.
- reset from an already-clean root is a safe, idempotent no-op.
- filesystem artifact names are fixed kernel constants; no per-lab identity is
  ever interpolated into a path, so corrupted metadata can never gain
  path-shaping power.

### Crash / interruption

Because the journal is written before any mutation and the fixed-tombstone
rename happens before any deletion, an interrupted reset is always classified
`resetting` — never a live/active lab — and the next `reset` finishes clearing
it deterministically. Residue that forces `resetting` includes the fixed
tombstone, the pending journal, a kernel-owned metadata temp (a process killed
between an atomic write's temp and its replace), or a lock without its active
subtree; this holds even if a lock and an active subtree coexist with the
residue, so it can never be read as `ACTIVE`/`CLOSED` and can never be written.
The lock and journal are durable bounded-provenance recovery records: they are
removed only after the tombstone has actually been deleted **and** the reset
receipt has been durably committed, so a retry after an interrupted delete or an
interruption between deletion and receipt commit still recovers the exact
bounded provenance rather than a degraded receipt — and the root can never
report a false clean while that provenance could still be lost. An ordinary
write failure removes its own temp; an unknown temp-like file is never silently
deleted. A state the simplified transaction can never generate — an active
subtree that coexists with a tombstone, or the fixed tombstone without a
committed journal — fails closed instead of being guessed at.

The single invariant is: **until final reset completion is mechanically
provable, at least one valid bounded recovery record exists, and the lab
cannot classify as CLEAN or writable.** The covered interruption boundaries
are: before the journal commit; after the journal commit but before the
rename; after the rename but before the delete; during tombstone deletion;
after the tombstone is gone but before the receipt commit; after the receipt
temp is created but before its atomic replace; after the receipt is committed
but before recovery-metadata cleanup; and after recovery-metadata cleanup.

## Structural NON-CANON and clean proof

- `NON-CANON` is structural: the lab lock always carries `non_canon: true`. It
  is not a prose suggestion and not a mode the caller can flip.
- the clean proof is **structural**, not an enumerated checklist of current
  state kinds: no active subtree, no fixed tombstone, no pending journal, no
  kernel-owned metadata temp residue, no lock, and no unexpected state owned by
  the lab root. Only the lock and the latest reset receipt may survive.
- unexpected or corrupt lab-root state fails closed instead of writing a false
  clean receipt. The latest reset receipt is parsed and revalidated against the
  bounded receipt contract, so a corrupt, malformed, unknown-field or
  narrative/story-bearing receipt fails clean proof and blocks a new `begin`.

## Reset receipt

A surviving reset receipt (`last-reset.json`) is small lifecycle/provenance
metadata only: an exact integer schema version, the receipt kind, the unique
`reset_id` shared with the journal, `non_canon: true`, one bounded `provenance`
value, and `verified_clean: true`. It carries **no** campaign/story payload — no
narrative anchor, no counters or telemetry, no lab state file contents — and it
carries no per-lab filesystem name. Bounded `provenance` is one nested value:
either `null` (a legitimate orphan cleanup with no surviving identity) or one
complete `{lab_id, mode, origin, closed_outcome}` object, so a partial/mixed
tuple cannot exist structurally. A later successful reset atomically replaces
`last-reset.json` with a new `reset_id`; an interrupted retry never rewrites a
receipt that already carries the current transaction's `reset_id`.

## No merge-back

There is deliberately **no** merge-back / canon-promotion / reconciliation
surface anywhere in this Mission. A good idea from a lab reaches canon only
through a **separate, later, DM-authorized intake/canon decision**; the lab
lifecycle never writes canonical campaign state, the reality registry, or any
published runtime surface. See
[`docs/POST-EV2-4B-REALITY-INHERITANCE.md`](POST-EV2-4B-REALITY-INHERITANCE.md)
for the inheritance foundation this builds beside.

## Trust boundaries

- The kernel does **not** infer a source checkpoint from chat, branch names,
  filesystem names, or mutable "latest" state. The caller supplies an exact
  trusted origin receipt.
- The kernel validates shape/coherence of that receipt only. Independent
  provider/remote verification belongs to the caller/platform.
- source/origin material is read-only to this lifecycle, and the lab root is
  disposable authority only — never canonical campaign authority. A lab root
  inside a Git working tree is refused.
- The kernel writes only inside the supplied scratch root.

## Repository surfaces

| Surface | Purpose |
| --- | --- |
| `scripts/brainstorm_lab.py` | Reusable disposable-lab lifecycle kernel |
| `tests/post_ev2_14/test_brainstorm_lab.py` | Bounded lifecycle proof |
| `docs/POST-EV2-14-DISPOSABLE-BRAINSTORM-LAB.md` | This contract |

No Supabase migration, no runtime route, no reality-registry record, and no
owner schema is added or changed. `realities/` continues to own canonical
reality identity/parent lineage only; disposable labs are **not** realities and
never register in it.

## Deferred ownership

- hosted/new campaign save-slot provisioning or source-checkpoint
  materialization → CCC-PLATFORM-01 / platform consumer;
- frontend create/inspect/discard lab UX → later CCC UI owner;
- role/account authorization → existing CCC access owners;
- actual owner-domain divergence during gameplay → each existing owner/mechanic
  when a real consumer wires the lab;
- multi-active-lab support → a later proven consumer only;
- merge-back/canon promotion → no automatic owner; a later explicit human
  canon/intake path if ever requested;
- reality-aware RAG across persistent alternate histories → a separate future
  retrieval owner.
