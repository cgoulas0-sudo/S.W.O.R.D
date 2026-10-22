# Rolling High Club — Major Villains

The top-level `villain/` directory is the **single major-villain root** for RHC.

## Flat Structure Rule

Use one flat file per major recurring villain:

- `villain/<villain_slug>.md`
- optional large lair companion: `villain/<villain_slug>_lair.md`

Do **not** create nested `villain/<villain_slug>/` directories. Do **not** create a competing `npc/villain/` or `npc/villains/` root.

## What a Villain File Owns

A villain card may combine durable identity, psychology, motives, signature mechanics, baseline combat chassis, combat doctrine, escape logic and standing capabilities when keeping those together makes the villain easier to run.

It does **not** own mutable campaign consequences. Current location, active injuries/effects, current operational goal, current carried/deployed equipment and local knowledge may be tracked through the normal live-state/knowledge domains when needed.

Villain files are **META by default**. Revealed sections may be marked NON_META individually.

Use `VILLAIN_TEMPLATE.md` for a new major villain. Use `VILLAIN_LAIR_TEMPLATE.md` only when a lair needs a substantial separate reusable reference.
