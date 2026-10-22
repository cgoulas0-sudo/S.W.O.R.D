# Bor — Combat Reference NPC

> Mechanical reference for Bor as a combat-capable RHC NPC. For NPC subsystem behavior, follow `npc/NPC_SYSTEM.md`. Personality stays in `npc/profiles/bor.md`; current location and live carried/deployed gear stay in `npc/npc_state.json`.

## Τύπος Reference & Πηγή

- **Combat mechanics:** npc_stat_block
- **Ruleset:** D&D 5.5e / revised fifth edition (2024)
- **Κύρια πηγή:** RHC CR build informed by the user-supplied Bor character sheet
- **Source status:** user_defined_rhc_cr_build

## Build / Ταυτότητα

- **Όνομα:** Bor
- **Είδος:** Orc
- **Combat identity:** Paladin-style divine front-liner / Oath of Devotion flavor
- **Challenge Rating:** **CR 10**
- **Proficiency Bonus:** +4
- **Alignment:** Chaotic Good

## Βασικά Στατιστικά

- **AC:** 18
- **HP:** 168 (16d10 + 80)
- **Speed:** 30 ft.
- **Initiative:** +1

| Ability | Score | Modifier |
| --- | ---: | ---: |
| STR | 16 | +3 |
| DEX | 12 | +1 |
| CON | 20 | +5 |
| INT | 10 | +0 |
| WIS | 12 | +1 |
| CHA | 18 | +4 |

## Saving Throws & Skills

- **Saving Throws:** STR +7, CON +9, WIS +5, CHA +8
- **Skills:** Athletics +7, Insight +5, Perception +5, Persuasion +8
- **Passive Perception:** 15
- **Languages / senses:** Common, Elvish, Gnomish, Orc; Darkvision 120 ft.

## Defenses / Passive Features

### Aura of Protection
Bor and allies within 10 ft. gain **+4 to saving throws** while Bor is conscious. The bonus is not already included in the saving throw numbers above.

### Aura of Devotion
Bor and allies within his Aura of Protection are immune to the **Charmed** condition.

### Aura of Courage
Bor and allies within his Aura of Protection are immune to the **Frightened** condition.

### Relentless Endurance — 1/Long Rest
When Bor would be reduced to 0 HP without being killed outright, he drops to 1 HP instead.

### Radiant Strikes
Bor's melee weapon hits deal an additional **1d8 Radiant** damage; this is already included in the +3 Maul attack below.

## Equipment and readiness

- **Armor:** not tracked as an inventory requirement; AC 18 is the resolved NPC combat value.
- **Primary weapon:** **+3 Maul**
- **Weapon Mastery:** **Topple**
- **Canonical personal item:** Bell of the Lady’s Smile; separate from the lost Vestige Bell.
- **Live carried/deployed state:** `npc/npc_state.json` wins at scene start.

## Actions

### Multiattack
Bor makes **two +3 Maul attacks**.

### +3 Maul
*Melee Weapon Attack:* **+10 to hit**, reach 5 ft., one target.  
**Hit:** **13 (2d6 + 6) Bludgeoning + 4 (1d8) Radiant** damage.

**Topple:** after a hit, Bor may force the target to make a **DC 15 Constitution save**. On a failure, the target is **Prone**.

### Divine Smite — 3/Day
Immediately after Bor hits with the +3 Maul, he can deal an additional **9 (2d8) Radiant** damage to that target.

### Abjure Foes — 1/Day
Bor targets up to three creatures he can see within 60 ft. Each target must succeed on a **DC 16 Wisdom save** or become **Frightened** of Bor for 1 minute. Affected creatures repeat the save at the end of each of their turns, ending the effect on a success.

## Bonus Actions

### Lay on Hands — 3/Day
Bor touches himself or a creature within reach and restores **20 HP**. Instead of restoring HP, he may end one of these conditions on the target: Blinded, Charmed, Deafened, Frightened, Paralyzed, Poisoned, or Stunned.

### Adrenaline Rush — 4/Short Rest
Bor takes the Dash action and gains **4 Temporary HP**.

## Spellcasting

Bor uses **Charisma** for spellcasting (**Spell Save DC 16, +8 to hit with spell attacks**).

Keep only fast-resolution spells on the battle card:

- **2/Day each:** Command, Shield of Faith
- **1/Day each:** Aid, Zone of Truth, Banishment, Revivify

## Combat Doctrine

These are DM tactical defaults, not immutable behavior.

- **Opening priorities:** Keep allies inside the aura, identify the most dangerous threat, then engage it directly.
- **Damage plan:** +3 Maul pressure; spend Divine Smite on priority targets rather than routine enemies.
- **Control:** Use Topple to create advantage for melee allies; use Abjure Foes when multiple enemies can be disrupted at once.
- **Support:** Lay on Hands when an ally would otherwise lose meaningful actions or be removed from the fight.
- **Escalation limit:** Bor avoids needless lethal force where surrender or containment is realistic, but becomes decisive when companions or innocents are threatened.
- **Retreat / surrender:** He will retreat to preserve the group, but is extremely reluctant to abandon companions.

## CR 10 Resolution Notes

This is an **NPC CR build**, not a player-character level package. The original character sheet is used for identity and Paladin/Orc flavor; this file is deliberately compressed and rebalanced for CR 10 table resolution.

The **+3 Maul** is user-defined RHC equipment and is part of this battle reference.

## Canon notes

- **Combat reference canon:** Yes
- **User-defined στοιχεία:** CR 10; +3 Maul; Alignment — Chaotic Good; RHC role — NPC.
- **Source-supported identity:** Orc; Paladin/Oath of Devotion identity; Tymora/Bell continuity.
- **DM-authored mechanical choices:** CR-balanced AC, HP, ability spread, limited-use features, simplified spell package and combat doctrine.
- **Τελευταία αναθεώρηση:** 2026-08-09
