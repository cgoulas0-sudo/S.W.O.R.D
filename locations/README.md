# Rolling High Club — Locations

This directory stores the RHC location subsystem.

A permanent location profile answers **what is this place?** A location-state record answers **what persistent mutable condition is true about this place right now?** Those are separate questions and must not become competing sources.

## Structure

- `locations/LOCATION_PROFILE_TEMPLATE.md` — reusable permanent location-card shape.
- `locations/LOCATION_STATE_TEMPLATE.json` — reusable mutable-state shape.
- `locations/profiles/<location_slug>.md` — one permanent card per important tracked location.
- `locations/state/<location_slug>.json` — create only when persistent mutable location state is worth tracking.

## Permanent Profile

Store stable geography, appearance, function, durable affiliations, established history, lasting hazards/features, normal access baseline and source notes.

Do not store today's guards, temporary damage, current controller, temporary closure, present NPCs or unresolved operations in the permanent profile.

## Mutable State

Create a state file only when a place gains persistent mutable continuity that may matter later, such as:

- current control / ownership;
- access status;
- condition / damage;
- current security posture;
- persistent active function;
- durable presence of tracked entities;
- location-bound assets.

Use `Unknown` or `null` instead of inventing a current state.

## Knowledge and Visibility

Location files may reference canonical `fact_id` values from `knowledge/facts.json`. Who knows a location secret belongs to character/NPC knowledge state, not to the location merely because the fact exists.

META/NON-META handling follows `knowledge/META_NON_META_PROTOCOL.md`.

Mission 10 or other simulation continuity must never enter this subsystem unless the Dungeon Master explicitly imports a specific element into RHC canon.
