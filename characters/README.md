# Rolling High Club — Player Characters

This directory stores permanent Player Character sheets and reusable PC templates.

## Rules

- One permanent Markdown sheet per tracked Player Character: `characters/<character_slug>.md`.
- Use `CHARACTER_TEMPLATE.md` when creating a new sheet.
- Use `CHARACTER_STATE_TEMPLATE.json` only when persistent mutable state needs repository tracking beyond the player's normal tabletop sheet.
- The human player always controls their character's choices, speech, movement, actions, tactics and voluntary resource use. Repository data never grants the DM control over a Player Character.
- Missing character details remain unknown or delegated to the player's authoritative sheet; never infer them to complete a template.
- Persistent item definitions belong in `inventory/`; ownership/equipped/attunement belongs to character state when tracked.
- Knowledge remains local to the character and follows `knowledge/KNOWLEDGE_SYSTEM.md`.
