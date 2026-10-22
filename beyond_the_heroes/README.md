# Beyond the Heroes

## 📜 Πώς λειτουργεί το Beyond the Heroes

Οι σελίδες αυτού του αρχείου δεν ανήκουν στους ήρωες.

Ανήκουν στον ίδιο τον κόσμο.

Εδώ καταγράφονται στιγμές που συμβαίνουν μακριά από τα μάτια της ομάδας. Συναντήσεις που δεν άκουσε κανείς, αποφάσεις που πάρθηκαν στις σκιές και γεγονότα που ίσως μία μέρα φτάσουν στα αυτιά των ηρώων.

Κάποιες ιστορίες μπορεί να αποκαλύψουν νέους κινδύνους.

Κάποιες μπορεί να γεννήσουν ερωτήματα.

Και κάποιες ίσως αποδειχθούν το πρώτο σημάδι μιας μεγάλης αλλαγής που ακόμα κανείς δεν μπορεί να κατανοήσει.

Όμως να θυμάστε!:

**Η γνώση του αναγνώστη δεν είναι η γνώση του ήρωα‼️**

Οι χαρακτήρες σας θα πρέπει να συνεχίσουν να ζουν, να αποφασίζουν και να φοβούνται μόνο με βάση όσα έχουν ανακαλύψει μέσα στον κόσμο του Faerûn.

Γιατί οι μεγαλύτεροι θρύλοι δεν γράφονται όταν κάποιος γνωρίζει την αλήθεια, γράφονται όταν κάποιος τολμά να την αναζητήσει.

---

## System purpose

`Beyond the Heroes` is the RHC backstage narrative and hook-development system. It lets the world move outside the heroes' point of view and gives the DM and project manager a clean place to develop cinematic cutaways, villain/faction activity, hidden consequences and future hooks.

It is deliberately small and human/AI-readable.

## Two honest states

### `ideas/` — possible, not canon

Use for brainstorming, candidate cutaways and possible future developments.

An idea here has **not happened** merely because it was written down. It may be changed, discarded or promoted later by the DM.

### `entries/` — occurred backstage

Use only after the DM establishes that the backstage event actually occurred in the RHC world.

An entry here is world truth, but it is **not automatically hero knowledge**. Characters learn it only through in-world observation, reports, discovery or revelation.

This separation is mandatory. Never silently promote an idea into an occurred event.

## Reader exposure and spoiler acknowledgement

`entries/` material is reader-visible backstage world truth, but in normal player-facing use an occurred/published entry is made available to player accounts only after an explicit **spoiler acknowledgement**. Acknowledgement changes human reader exposure only; it never creates, implies or propagates character knowledge. The deterministic request-time access seam that enforces this reader-exposure rule together with owner-aware campaign-context admission is `scripts/context_access.py`, documented in `docs/BTH-01-PLAYER-DM-ACCESS.md`.

## Lifecycle

```text
brainstorm idea
    ↓ DM decision
Beyond the Heroes entry occurs
    ↓ consequence / causal pressure
optional Hook creation or advancement
    ↓ in-world discovery
hero knowledge / reveal
    ↓
normal RHC continuity and day history
```

Not every entry needs to become a Hook. Not every Hook needs a Beyond the Heroes scene.

## Routing

- Possible backstage scene → `beyond_the_heroes/ideas/`
- Established backstage event → `beyond_the_heroes/entries/`
- Current multi-day Hook lifecycle → `quests/narrative_hooks.json`
- Who knows an established fact → `knowledge/` and the relevant character/NPC state
- Player-known active-day handoff → `state/daily_recap.json`
- Finalized day history → `canon/days/day_XXX.md`

`Beyond the Heroes` must not become a competing Hook ledger, knowledge database or day archive.

## Brainstorming rule

When using this system for brainstorming:

1. Read the smallest relevant canon sources first.
2. Treat existing `entries/` as established backstage truth.
3. Treat `ideas/` only as proposals.
4. Generate consequences from established motives and world conditions; do not invent missing canon merely to make a proposal work.
5. Keep hero knowledge separate from reader/DM knowledge.
6. Let the DM decide whether an idea is discarded, retained, or promoted into an occurred entry.

## Entry design

A useful entry should answer only what matters:

- What happened away from the heroes?
- Where and when did it happen?
- Who was involved?
- Why does it matter?
- What changed in the world because of it?
- Who actually knows about it?
- Could it create or advance a Hook?
- Has any part of it been revealed to the heroes?

Use `BEYOND_THE_HEROES_TEMPLATE.md` for both ideas and occurred entries. The folder determines whether the document is proposal or established backstage truth.

## Persistence

Beyond the Heroes follows the normal RHC manual worksystem.

- Brainstorming can remain in `ideas/` without affecting canon.
- Promoting an idea to `entries/` is a durable campaign change and must be reconciled with any affected Hook, knowledge, NPC, villain, location or current-state owner.
- Final Save may summarize meaningful backstage consequences in the day's archive when appropriate, without leaking unrevealed information into player-known recap.

## Boundary

Mission10 content does not enter this system automatically. Beyond the Heroes belongs to the real Rolling High Club continuity.
