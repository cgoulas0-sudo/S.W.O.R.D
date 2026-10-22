# Rolling High Club — Inventory / Item Definitions

This directory stores permanent definitions for important unique/custom items, weapons and other equipment that require durable RHC reference.

## Ownership Boundary

A static item file answers **what is this item and how does it work?** It does not automatically establish who owns, carries, equips or attunes to it.

Current ownership/equipment belongs in the relevant Player Character or NPC mutable state when repository tracking is needed.

## Structure

- Use `ITEM_TEMPLATE.md` for a generic important item.
- Category subfolders such as `inventory/weapons/` are acceptable when useful.
- Hidden properties are META until legitimately revealed.
- Never grant an item merely because a character is proficient with it or because the item file exists.
