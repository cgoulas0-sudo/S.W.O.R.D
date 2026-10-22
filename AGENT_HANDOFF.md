# AGENT_HANDOFF.md — Repository Dropgate

This is the vendor-neutral cold-start router for Rolling High Club. It is the one universal Dropgate: it classifies the request, then sends the agent to the smallest repository cockpit that owns the lane. It does not own Mission state, implementation truth, project history, campaign canon, or account workflow.

## Route First

Read this door, classify the request into exactly one lane, then load only the authority that lane names. Do not treat this router as a source of truth, and do not pull previous chat history or a whole-repository dump from it. The no-Asana boundary is **not** global: it belongs specifically to BUILD Builder cold-start (below), so a fresh Builder consumes JOHNNY instead of reopening Asana. The READ lane is the exception — it may consult live Asana for current-workflow status, because reading status changes nothing.

## Lanes

### BUILD — change repository engineering (docs, workflow, code, schema, tests)

- **Approved BUILD Mission that still needs JOHNNY Issue / BUILD-branch setup** → read [`ORCHESTRATOR.md`](./ORCHESTRATOR.md).
- **Prepared BUILD Mission with its JOHNNY Issue and BUILD branch already established** → read [`BUILDER.md`](./BUILDER.md).

BUILD authority is the branch-bound JOHNNY plus repository implementation truth. BUILD never reconstructs the Mission from Asana or chat.

### PLAY — actively run or continue the tabletop campaign (live scenes, narration, DM session work)

- **Running or continuing a live campaign session — a DM scene, narration, or in-session DM work** → read [`PLAY.md`](./PLAY.md), which routes into [`docs/DM_CONTROL_ROOM.md`](./docs/DM_CONTROL_ROOM.md). A running session reads canon internally as it needs to; that stays PLAY.

A **standalone** canon / rules / state look-up that is not part of continuing a live session is **READ**, not PLAY — route it there. PLAY never loads BUILD engineering machinery (JOHNNY, Flight Control, ledgers, validators).

### SAVE — persist durable campaign continuity

- **Quicksave / Autosave / Final Save / day rollover / durable campaign change** → read [`docs/RHC_WORKSYSTEM.md`](./docs/RHC_WORKSYSTEM.md) and use the activated RT01 guarded persistence procedure.

SAVE routes only to the real active persistence authority. There is **no direct-write shortcut** and no chat-level success claim. A direct repository write, a raw SQL write, a manual `runtime-published` change, or a chat-level "saved" claim is not a completed save. RT01 save completion requires guarded SQL publication plus exact remote `runtime-published` read-back and verifier confirmation for the same database-owned generation/token. Repository `main` remains implementation + campaign-canon truth; SQL/Supabase is the live operational published-world surface; `runtime-published` is durable checkpoint/provenance evidence. When the procedure also requires a repository canon/history artifact, that artifact must exist in committed repository state, but the repository commit does not replace runtime publication confirmation. Never claim success before the confirmed generation/ref exists.

### READ — answer from current truth without changing anything

- **Current workflow status — "What is the current job / active gate / next authorized action?"** → consult **live Asana first** as the control-plane authority when it is available, then fall back to the smallest relevant repository control doc. This is the read-only exception to the BUILD no-Asana boundary: READ may look at Asana, it just never writes.
- **Standalone current operational-state look-up** → use the supported SQL-first runtime facade (`public.dm_runtime_read()`) for published current state and checkpoint metadata. If more detail is required, follow only the exact confirmed Git fallback ref returned by trusted runtime metadata and read the needed value from the checkpoint artifact's `state` map at that ref; never treat bare `main`, the mutable `runtime-published` branch head, or a stale state-domain file at that ref as a discovered fallback.
- **Standalone canon / rules / static repository look-up** → read the smallest authoritative source through the [`README.md`](./README.md) domain router. Repository `main` remains campaign-canon / implementation truth even though mutable operational state is served from the published runtime.

READ performs no mutation. It never writes files, never commits, never saves, and never advances a lifecycle gate — reading live Asana status included. If answering would require a write, it is not a READ — reclassify.

### UNKNOWN / CONFLICT — the lane is not clear, or two lanes are requested at once

- **STOP and ASK a narrow classifying question. Do not default to BUILD.** Do not guess, do not write, do not start engineering work to "make progress."

UNKNOWN/CONFLICT fails closed. A request that mixes BUILD and PLAY, an ambiguous instruction, or a lane you cannot confidently place is resolved by asking, never by assuming. Use [`README.md`](./README.md) only to help classify, then follow the smallest relevant lane.

## Rule

Route first, then load only the authority required by that lane. This door is a router only — not truth, state, history, or campaign canon. Vendor entry stubs (`CLAUDE.md`, `AGENTS.md`) point here and carry no independent authority.
