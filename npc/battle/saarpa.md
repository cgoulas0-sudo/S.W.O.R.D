# Sa’arpa — Combat Reference NPC

> Mechanical reference for Sa’arpa as a combat-capable RHC NPC. For NPC subsystem behavior, follow `npc/NPC_SYSTEM.md`. Permanent personality and durable identity belong in her NPC profile when present; current location and live carried/deployed gear stay in `npc/npc_state.json`.

## Τύπος Reference & Πηγή

- **Combat mechanics:** npc_stat_block
- **Ruleset:** D&D 5.5e / revised fifth edition (2024)
- **Κύρια πηγή:** RHC CR build based on established Sa’arpa canon and current Paladin mechanics
- **Source status:** user_defined_rhc_cr_build

## Build / Ταυτότητα

- **Όνομα:** Sa’arpa
- **Είδος:** Human
- **Class / subclass:** Paladin — Oath of Devotion style
- **Challenge Rating:** **CR 7**
- **Proficiency Bonus:** +3
- **Alignment:** **Chaotic Good**

## Βασικά Στατιστικά

- **AC — common reference state:** **18** (plate)
- **AC — alternate equipment states:** determined by live equipment state if armor changes
- **HP:** **120 (16d8 + 48)**
- **Hit Dice:** 16d8 + 48
- **Speed:** **30 ft.**
- **Initiative:** +1

| Ability | Score | Modifier |
| --- | ---: | ---: |
| STR | 18 | +4 |
| DEX | 12 | +1 |
| CON | 16 | +3 |
| INT | 10 | +0 |
| WIS | 14 | +2 |
| CHA | 16 | +3 |

## Saving Throws & Skills

- **Saving Throws:** CON +6, WIS +5, CHA +6
- **Skills:** Athletics +7, Insight +5, Perception +5, Persuasion +6, Survival +5
- **Passive Perception:** 15
- **Languages / senses:** Common; normal human senses

## Defenses / Passive Features

### Aura of Protection
Sa’arpa and allies within 10 ft. gain **+3 to saving throws** while Sa’arpa is conscious. The bonus is not already included in the saving throw numbers above.

### Aura of Courage
Sa’arpa and allies within 10 ft. are immune to the **Frightened** condition while she is conscious.

### Protective Resolve
Sa’arpa has **Advantage on saving throws against being Charmed or Frightened**.

## Equipment and readiness

- **Everyday presentation:** armored desert warrior and daughter of the Great Khan; practical travel gear rather than ceremonial equipment
- **Armor:** plate armor
- **Primary weapon:** **Glaive**
- **Secondary weapons:** 3 javelins
- **Holy symbol / focus:** Paladin holy symbol carried on her person
- **Canonical magic items:** **None currently assigned on this battle card**
- **Readiness / access:** `npc/npc_state.json` wins at scene start; equipment is never granted retroactively from this reference

## Actions, features and spells

### Multiattack
Sa’arpa makes **two Glaive attacks**.

### Glaive
*Melee Weapon Attack:* **+7 to hit**, reach 10 ft., one target.  
**Hit:** **9 (1d10 + 4) Slashing** damage.

**Graze:** when Sa’arpa misses with the Glaive, she can deal **4 Slashing damage** to the target. This damage can’t be increased in any way.

### Divine Smite — 3/Day
Immediately after Sa’arpa hits with the Glaive, she can deal an additional **9 (2d8) Radiant** damage to that target.

### Sacred Weapon — 1/Day
As a Bonus Action, Sa’arpa empowers her Glaive for 1 minute. While empowered, she gains **+3 to attack rolls** made with it. The weapon emits Bright Light in a 20-foot radius and Dim Light for an additional 20 feet.

## Bonus Actions

### Lay on Hands — 3/Day
Sa’arpa touches herself or a creature within reach and restores **15 HP**. Instead of restoring HP, she may end one of these conditions on the target: Blinded, Charmed, Deafened, Frightened, Paralyzed, Poisoned, or Stunned.

## Reactions

### Protective Interposition
When a creature Sa’arpa can see within 5 ft. of her is hit by an attack, Sa’arpa can impose **Disadvantage** on the attack roll if she is able to interpose herself before the result is resolved.

## Spellcasting

Sa’arpa uses **Charisma** for spellcasting (**Spell Save DC 14, +6 to hit with spell attacks**).

Keep only fast-resolution spells on the battle card:

- **2/Day each:** Command, Shield of Faith
- **1/Day each:** Aid, Lesser Restoration, Zone of Truth

## Combat Doctrine

These are DM tactical defaults, not immutable behavior.

- **Opening priorities:** Put herself between the main threat and vulnerable allies; keep nearby allies inside her aura whenever possible.
- **Damage plan:** Use reach to control space and reserve Divine Smite for dangerous or narratively important targets.
- **Defensive priorities:** Protect wounded allies, civilians and members of the Bait Mahwa before pursuing personal advantage.
- **Support / command priorities:** Lay on Hands is used to keep an ally active rather than for minor chip damage; Command is used when it can prevent harm without requiring lethal force.
- **Escalation limit:** Sa’arpa prefers honorable, decisive action but does not kill surrendered or helpless enemies without a compelling immediate threat.
- **Retreat / surrender:** She will retreat if doing so protects others or preserves the group, but is highly reluctant to abandon an ally in immediate danger.
- **Likely deviations:** Threats against her companions, family or the people of Anauroch can make her act more aggressively and emotionally than her normal disciplined style.

## CR 7 Resolution Notes

This is an **NPC CR build**, not a player-character level package. **CR 7 does not mean Paladin level 7.** The Paladin identity is compressed into fast-resolution NPC mechanics intended for RHC combat simulations.

## Canon notes

- **Combat reference canon:** Yes
- **Published-source στοιχεία:** revised 5e Paladin-derived mechanics, standard glaive/javelin/plate equipment concepts and common combat resolution
- **User-defined στοιχεία:** Sa’arpa is Human; Paladin; daughter of the Great Khan Saar; **CR 7**; **Chaotic Good**
- **DM-authored choices:** ability scores, HP, limited-use feature counts, simplified spell package, mundane combat loadout and combat doctrine
- **Τελευταία αναθεώρηση:** 2026-08-09
