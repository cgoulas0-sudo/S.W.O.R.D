# POST-EV2-Z — Clean Campaign Canvas Export

## Purpose

POST-EV2-Z produces **one deterministic clean campaign canvas** from the exact
tracked Git HEAD of Rolling High Club (RHC). The canvas is a structural
copy-out: reusable engine/runtime/mechanics/proof surfaces are copied
byte-for-byte; RHC's one living campaign's instance data, canon, story and
history are excluded; the declared mutable campaign roots are generated as
EMPTY / UNKNOWN starting state; and any tracked path without a declared
structural disposition fails the export closed.

The canvas is the input for **RHC-Bootstrap (PORT-01)**, which owns consuming
it (repository placement, provisioning, template tooling). This Mission owns
only producing a clean, deterministic, versioned source tree. RHC remains the
single engine authority; this exporter never creates a second maintained engine
fork.

## Factory-only machinery

The whole Mission is factory control-plane and never appears in the exported
customer tree:

- `bootstrap/CLEAN_CAMPAIGN_EXPORT_POLICY.json` — the machine-read policy;
- `scripts/export_clean_campaign.py` — the exporter;
- `docs/POST-EV2-Z-CLEAN-CAMPAIGN-EXPORT.md` — this document;
- `tests/post_ev2_z/test_clean_campaign_export.py` — the proof;
- `.github/workflows/post-ev2-z-clean-canvas.yml` — the Mission-local CI.

The export receipt/manifest is written *outside* the customer tree.

## How to run

```bash
python scripts/export_clean_campaign.py \
  --repo-root . --ref HEAD --output /path/to/new/canvas
```

The output must be a new, non-existent child directory of an already-existing
real parent directory outside the source worktree. The exporter refuses a
destination that already exists, a destination inside the source tree, and a
receipt path inside the repository or the canvas. A diagnostic
`--report-references` flag prints dangling retained routes instead of failing
and is not part of normal operation.

## Engine version

The export receipt carries a comparable, explicit `engine_version` field
alongside the already-recorded `source_commit` (the peeled `--ref`). The value
is a [SemVer 2.0.0](https://semver.org) string (for example `1.0.0`) and comes
from **one single root-level source of truth**, the tracked `ENGINE_VERSION`
file, so it is independent of Git history: a raw commit SHA has no
ordering/comparability semantics, which is what RHC-Bootstrap (PORT-01) needs
for Copier `check-update` drift detection across campaign repos.

The exporter reads `ENGINE_VERSION` from the **exact source commit** (like the
portability policy), so the receipt's version is bound to the exported tree and
does not depend on the working tree, branch name, or history ordering. The
version source path is itself classified `EXCLUDE`: the value is control-plane
metadata recorded in the receipt, not a shipped customer-tree surface.

The export fails closed if the version source is missing or is not a valid
semver string. Deciding *when* to bump the version, and what counts as a
breaking engine change, is a human-owned policy decision outside this exporter;
consuming the receipt field (including placing the version in a template) is
PORT-01's.

## Dispositions

- **COPY** — reusable engine/runtime/mechanics/schema/validator/migration/
  control surface/selected reusable proof. Bytes are fetched verbatim from the
  exact Git blob; the Git file mode is preserved.
- **EXCLUDE** — RHC campaign instance material, story/history, canaries,
  engineering-history payload, and factory-only POST-EV2-Z machinery. Absent
  from the exported tree (the campaign **folder skeleton** is still preserved).
- **GENERATE_EMPTY** — a declared mutable campaign root, emitted as
  contract-valid EMPTY / UNKNOWN state from fixed generation constants in the
  policy, materialized at the rule's declared `output_path` when one is
  present (otherwise at the source path).

The classification is **strictly structural and path-based**. The exporter never
scans, reads, redacts, detects, rewrites, or otherwise interprets file
*content* to decide a disposition. No content scanning, name detection, SHA
detection, or text rewriting is used.

### Classification Granularity Rule

No folder may be labelled COPY as a single unit. `COPY` rules are always exact
repository-relative paths (the policy parser rejects a `COPY` rule that ends in
`/`). A folder is mixed-ownership the moment it contains one lore/instance file;
every file inside a reusable-looking folder is individually classified. This
directly closes the attempt-2 failure where blanket `docs/` and `supabase/`
rules leaked campaign history.

### Match semantics

Each rule `match` is an exact path, or (for `EXCLUDE` only) a directory prefix
ending in `/`. A path resolves to the rule with the **longest** matching string.
No match fails closed (unclassified); two rules tied at the winning length fail
closed (ambiguous).

### Remap target validation

A `GENERATE_EMPTY` target declaring a campaign-neutral `output_path` is itself
validated fail-closed against every other policy path before anything is
written. A target containing a `.` or `..` path component is rejected: such a
raw string normalizes onto a different real path (`./README.md` materializes
`README.md`), which raw-string comparison could never see. The normalized
target must also not equal any other policy path or generated output, must not
nest inside one or have one nested inside it (a remapped file and an existing
destination cannot share a file/directory boundary), and must never land
inside an `EXCLUDE`-owned directory prefix. The intended neutral mapping
`realities/registry/rhc-primary.json` -> `realities/registry/campaign-root.json`
is unaffected.

## Reference integrity

A retained control-plane route must not ship as a dead or unprovable reference.
After dispositions are fixed structurally, the exporter reads every retained
control-plane surface — COPY surfaces through their source bytes and
GENERATE_EMPTY surfaces through their generated policy bytes — and verifies
that its internal repository-relative routes resolve to a real dependency of
the exported tree. A route into an excluded source path, a route that names a
path existing nowhere in the source tree, and an executable route satisfied
only by an empty preserved skeleton directory all fail the export closed.

Satisfied-ness is species-aware on purpose, because the two route species
resolve differently at runtime:

- **Markdown documents** — a route is a Markdown hyperlink target (`](target)`).
  Inline code spans and prose mentions are document *content* (examples,
  commands, symbol names), not navigational routes, and are deliberately not
  treated as routes. A navigational route may be satisfied by a COPY file, a
  generated file, or a preserved skeleton directory: a reader sent to
  `npc/profiles/` still finds the directory that exists. Link candidates that
  never resolved to a real source path (forward placeholders such as
  `canon/days/day_XXX.md`, runtime facades) are ignored: the source tree never
  contained them, so they cannot dangle into an excluded file.
- **Workflow/automation files** under `.github/workflows/` — an *executable*
  dependency: a repository-relative command argument in a `run:` step
  (including folded blocks), a local `uses: ./path` action directory, and a
  statically declared step `working-directory`. The workflow YAML is parsed
  with a real parser (PyYAML) and the values are read by structurally walking
  `jobs.*.steps[]`, so every YAML-equivalent spelling of the `run` key — bare,
  single-quoted, double-quoted, or double-quoted with escape sequences such as
  `"\u0072un":` — is decoded exactly as GitHub Actions decodes it. Each
  relative `run:` argument is resolved against its step's effective working
  directory (step-level `working-directory`, else the job's
  `defaults.run.working-directory`, else the workflow's
  `defaults.run.working-directory`, else the repository root), because that is
  the directory GitHub Actions actually executes the command in. An executable
  route is satisfied **only by a real exported file** at or under the resolved
  path: an empty preserved skeleton directory collects zero tests (pytest exit
  5, "no tests ran") and satisfies nothing. A local `uses: ./path` step is
  stricter still: the action root must ship its `action.yml`/`action.yaml`
  metadata file, because a folder of unrelated files without metadata cannot
  load as an action. A repo-root local action (`uses: ./`, or the equivalent
  `uses: .//`) is checked too — never silently discarded as an empty path — and
  must ship a root-level `action.yml`/`action.yaml`. A static
  `working-directory` names a **directory** the runner changes into, so it is
  validated for directory-ness, not merely for exported-file existence: it
  resolves only when a real exported file exists at or under the resolved path,
  never when the resolved path is itself an exported *file* (changing directory
  into a file is impossible), and never when the only match is an empty
  preserved skeleton or an all-`EXCLUDE` directory that holds no exported
  descendant. A
   `working-directory` that cannot be resolved structurally to a repository-
  relative location — an Actions `${{ ... }}` expression, an absolute or `~`
  path, a `..` escape, or a backslash path — leaves the step's real run
  location unknown, so its repo-relative operands are recorded as consciously
  unproven (never silently treated as rooted at the repository root, where a
  root-level path could falsely satisfy a dependency the step never reaches).
  A statically written argument naming a path that exists nowhere in the source
  tree fails the export closed (it cannot resolve in any exported tree either).

A path operand (one shell argument) that carries any part of an Actions
`${{ ... }}` expression is dynamically computed (for example `refs/pull/`
inside `refs/pull/${{ github.event.pull_request.number }}/head`) and cannot be
statically resolved. The boundary is the *operand*, not the `_TOKEN_RE`
fragment: an expression separated from a path fragment by a path separator
(`${{ matrix.dir }}/tests/unit`, or `tests/${{ matrix.dir }}/unit.py`) is still
one dynamic operand, so no token inside it -- the trailing `tests/unit` or
`unit.py` fragment included -- can be claimed a proved repository-root
dependency, while an argument separated by whitespace (`${{ matrix.dir }}
unit.py`) is an independent operand that stays statically checked. Because an
Actions expression may itself contain whitespace (`${{ matrix.dir }}`),
classification tests each non-whitespace word against the parsed expression span
rather than trusting the word boundary, so expression-internal whitespace never
loses or misclassifies the operand. Such operands are never silently accepted
and never claimed as proved: the export records them in the receipt's
`unresolved_dynamic_routes` as explicitly classified, consciously unproven.
Deduplication is by normalized route **and** dynamic/static classification, not
by route alone: the same route can occur both as a dynamic fragment and as a
static argument in either order, so a static occurrence is still checked (and a
missing static dependency still fails the export closed) even when the route was
also mentioned dynamically, and the dynamic fragment is still recorded as
unproven even when the route also occurs statically. Each classification is
preserved independently; only exact same-class duplicates are collapsed.
A step whose effective `working-directory` is itself unresolvable is a second,
separate dropped dimension of the same route-classification boundary: because
the command's real run location is unknown, every repo-relative operand it runs
is recorded in `unresolved_dynamic_routes` (together with the unresolvable
working directory) instead of being proved as though the operand resolved at
the repository root. A static occurrence of the same route still resolves and
is still checked, in either order.
This closes the attempt-2 P1 where copied routers routed to excluded authority
files while the proof only checked that the excluded files were absent, the
round-1 gap where the check covered only Markdown `](link)` routes, the
round-2/round-3 regex gap (the check parses workflow structure with a real
parser instead of pattern-matching raw text), the round-4 gap (each decoded
`run:` argument resolves against its step's effective working directory), and
the POST-EV2-Z6 skeleton false positive (a directory named in a pytest command
was treated as present despite containing zero exported test modules), plus the
fourth Codex P2 (a static `working-directory` was validated by exact path
membership instead of the species-aware descendant-file rule, falsely rejecting
a real exported directory whose path is itself not a file), and the Z6
path-kind pair: a repo-root local action (`uses: ./`) was stripped to the empty
string and silently discarded so its `action.yml`/`action.yaml` was never
checked, and a static `working-directory` naming an exported *file* was falsely
accepted even though a runner cannot change directory into a file. Workflows
whose `run:` steps invoke only excluded paths — `entity-v2-identity.yml`,
`flight-control.yml`, `story-retrieval.yml` — are still classified `EXCLUDE`
rather than shipped broken.

Residual limits, declared honestly: the exporter performs no shell-program
equivalence analysis. It cannot prove dynamically computed dependencies
(recorded, not proved), cannot distinguish an echo label containing a slash
from a path argument (a static candidate that exists nowhere fails the export,
so slash-bearing prose must not be written into `run:` blocks), and does not
parse every conceivable command grammar. The closure guarantee that remains is
the one that can be stated exactly: every statically written route of every
shipped control-plane surface resolves to a real exported dependency, and the
shipped commands themselves are executed (see the exported product acceptance
below).

## Copied executable portability

A COPY-shipped executable/test surface must keep working inside the exported
canvas, where the Z classification has remapped or excluded RHC-only source
paths. The concrete failure class: the copied POST-EV2-14 brainstorm-lab suite
hard-coded RHC's canonical primary-reality path, so after POST-EV2-Z3 remapped
clean genesis to the campaign-neutral root it failed immediately inside the
canvas while every source-repository check stayed green. The durable guard has
three halves:

- **Structural resolution over hard-coded source paths, and no discriminator.**
  A shipped test that needs the primary-reality record resolves it by its
  structural role — the unique parentless root record — rather than hard-coding
  RHC's source path. The copied POST-EV2-14 suite additionally carries **no**
  source/factory-only assertion at all, so it runs unchanged in source RHC and
  inside an exported canvas. There is deliberately no source-vs-canvas context
  discriminator: earlier repairs kept hardening one (identity, schema,
  hardened-JSON parsing) and each layer proved to be the next defect
  (CODEX P1/P2 rounds on this Mission). Removing the source/factory assertions
  from the copied suite removes the only reason that context inference existed.
- **Factory/source wiring assertions are owned by this EXCLUDE factory proof.**
  The assertions that police the RHC factory machinery run only here, in source
  RHC, where the factory actually exists: the source Entity V2 workflow runs
  the POST-EV2-14 suite (`entity-v2-identity.yml`); the export policy
  classifies every POST-EV2-14 surface as COPY; and a fresh export of exact
  HEAD contains them. The copied suite never needs to infer its context, and
  the factory assertions never need skipping.
- **Fail-closed identity guard.** No shipped executable/structured surface
  (`*.py`, templates, scripts, workflows — everything except prose `*.md`,
  which may legitimately reference RHC source material; COPY blobs and
  policy-generated content alike) may carry the RHC-only primary-reality
  identity token; the Z proof fails closed when one does, and a synthetic
  stale copied reference proves the guard is not vacuous.
- **Trigger coverage for the guard's scan surface.** The guard's scan is only
  as durable as its admission: the mission-local workflow's path filters
  declare directory-prefix patterns (`schemas/**`, `scripts/**`, `tests/**`,
  …) plus the two root-level scanned files, and the Z proof proves that every
  shipped surface the guard scans (COPY plus GENERATE_EMPTY, minus prose
  `*.md`) is selected by at least one declared pattern in both the
  `pull_request` and `push` events. A future shipped surface landing outside
  every pattern fails the proof closed and forces the admission to be
  extended; a scanned surface therefore can never change without the guard
  running.

## Portable exported test boundary

The clean canvas is not only structurally copyable; the intended exported test
suite must run green in a **fresh independent repository that has no RHC
ancestry and no remotes**. POST-EV2-Z5 closes the concrete downstream failure
class: PORT-01's full exported-suite run reported 1104 passed / 1003 skipped /
13 failed because some shipped tests assumed RHC commit objects exist in the
generated repository. The 13 failures divide into two species with two different
owners:

- **Reusable Git-anchor behavior tests stay exported and become self-contained.**
  `tests/test_offscreen_anchor_context.py`, `tests/test_offscreen_run_resolution.py`
  and `tests/test_run_validation.py` test real `campaign_anchor.base_commit`
  behavior, but their fixtures historically carried one fixed RHC SHA. They now
  build a **temporary synthetic Git history** — a `main` branch whose first
  commit carries the reusable Scenario/Hook records and their schemas — and
  point the validator's Git seam at it. Each test therefore exercises the same
  anchor semantics (object-type resolution, canonical-branch reachability,
  anchored record/schema reads at commit, objective-context snapshotting)
  against a real, reachable, test-local commit instead of an RHC ancestor. The
  fixture records' historical anchor is materialized as that synthetic commit;
  no test is deleted, skipped, or converted into a blanket ignore.
- **Genuine RHC source-history/provenance proof stays in source RHC.**
  `tests/post_ev2_1/test_clean_bootstrap_equivalence.py`'s frontier assertion
  reads a pinned historical RHC commit to prove the clean baseline stays a
  byte-exact replay of that frontier. That is RHC source-repository provenance,
  not a portable Bootstrap invariant, so its policy disposition is reclassified
  `COPY` → `EXCLUDE`: it remains an RHC source proof and never ships into a
  canvas that cannot contain its ancestral commit.

The reusable anchor tests `tests/test_offscreen_anchor_context.py`,
`tests/test_offscreen_run_resolution.py`, `tests/test_run_validation.py` and
`tests/test_run_anchor_git_validation.py` remain COPY; the provenance proof is
EXCLUDE. The Mission-local workflow adds a `portable-suite` job that exports
exact HEAD, initializes a brand-new independent Git repository on `main` with no
commits but its own, asserts there are no remotes, and runs the **full exported
test suite** there — so the proof is the portable product itself, not only a
representative source subset, and no portable test can depend on unavailable
fixed RHC commits or hidden ancestor objects.

## Exported product acceptance (POST-EV2-Z6)

Z5 proved the full exported suite; Z6 closes the remaining exported-product
acceptance gap: the exported product's **shipped CI** must be coherent and
must actually execute what it invokes. PORT-01's Bootstrap PR #4 stayed red
because the copied RT01 runtime workflow still invoked four test trees the
policy excludes, so two shards ran commands that prove nothing, and the
exporter's own reference-integrity check blessed the invocation because an
empty preserved skeleton directory counted as a present dependency.

### Three non-overlapping acceptance layers

The exported product's executable coherence is proven by three layers with
disjoint responsibilities, so no single homegrown parser is asked to emulate
the whole GitHub Actions runner:

- **Layer A — pinned `actionlint` (GitHub Actions syntax/shape).** The
  Mission-local `clean-canvas` job downloads the official `rhysd/actionlint`
  v1.7.12 Linux amd64 release, verifies the archive SHA-256
  `8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8` *before*
  extracting or executing it, and lints the **two actual emitted workflows**
  (`.github/workflows/rt01-runtime.yml`,
  `.github/workflows/hard-write-boundary.yml`) from inside the canvas. The
  binary and its negative fixture live under `$RUNNER_TEMP`, never in the
  emitted tree, so the product/receipt is not polluted; `-shellcheck=` and
  `-pyflakes=` keep this layer scoped to Actions syntax rather than an
  unrelated shell-linter refactor. A deliberately invalid workflow fixture
  must make actionlint exit non-zero, or the job fails — the gate is
  non-vacuous. actionlint does **not** report a missing local action directory
  (a workflow may clone one at runtime) and does not resolve a static
  `working-directory` path kind, so it neither resolves the `uses: ./` case
  nor replaces the exporter's output-tree closure; it complements it.
- **Layer B — the Z exporter (tree inventory, path kinds, static closure).**
  The exporter remains the authority for exact exported tree inventory,
  deterministic COPY/EXCLUDE/GENERATE_EMPTY bytes/modes, path-type checks for
  local action metadata and static `working-directory`, static repo-local
  dependency closure, and the honest `unresolved_dynamic_routes` receipt.
- **Layer C — actual execution (runtime proof).** The exported shard commands
  run verbatim inside a fresh independent canvas with PostgreSQL 15/17, and
  the full portable suite runs in a brand-new repository; arbitrary shell
  semantics and remote marketplace behavior are proven by execution, not by
  static analysis.

### The exported RT01 runtime workflow is a policy-generated portability adaptation

The source `rt01-runtime.yml` legitimately invokes four test trees whose proof
stays in source RHC:

- `tests/ev2121` — generalized item identity admission;
- `tests/post_ev2_2` — HOT Run registry;
- `tests/post_ev2_9` — character vitals/resources;
- `tests/post_ev2_10` — character rest.

**Ownership audit** (POST-EV2-Z6): each of the four suites is a real-PostgreSQL
runtime proof over synthetic data whose *test code* nevertheless carries RHC
campaign-identity strings — `item:vampire` / `character:gork` in
`tests/ev2121` and `tests/post_ev2_2`, `character:mugen` in
`tests/post_ev2_9` and `tests/post_ev2_10`. The durable invariant that the
exported test suite is free of RHC character/NPC fixture names therefore makes
these suites source-only proof: they must not ship (and the exporter's job is
never to silence a failing command by copying a source-only test or stripping a
live source check). Their proof remains live in source CI, where the source
workflow keeps invoking them unchanged.

The policy classifies the shipped workflow itself
(`.github/workflows/rt01-runtime.yml`) as **GENERATE_EMPTY**: its exported
bytes are a fixed policy constant equal to the source workflow minus exactly
those four source-only pytest arguments — the one explicit, proven portability
adaptation of the COPY-exactness rule. The Z proof carries a sync guard (the
generated bytes must equal the source workflow minus exactly the audited
arguments, structurally — including the whole top-level workflow contract
`name`/`on`/`env`/`defaults`/`permissions`, so only the four `run:` arguments
may differ, with a non-vacuous top-level-divergence negative), and the
exporter's reference-integrity check proves the generated bytes reference only
shipped executable surfaces. A source-side
workflow change therefore cannot silently drift away from the shipped
adaptation: either the sync guard or the route check fails the proof closed.

### The proof is the exported product's own CI

`rt01-runtime.yml`'s shard commands declare PostgreSQL-backed proof shards with
a stable `prove-runtime-foundation` aggregate that succeeds only when every
shard succeeds (a failed, cancelled, or skipped shard turns it red). The
Mission-local workflow's clean-canvas job exports exact HEAD, initializes a
brand-new independent Git repository, and **executes every exported shard
command verbatim inside that canvas** with the PostgreSQL services those
commands require, failing closed on a non-zero exit or a shard that proves
nothing (zero tests passed — a DB-gated proof silently skipping is a failure,
not a pass).

### Shipped hard-write-boundary fence

`.github/workflows/hard-write-boundary.yml` ships COPY with the canvas. Its
authority contract is repo-contextual, not RHC-ancestry-bound: it runs
`pull_request_target` from the trusted base, grades the exact PR head/base with
the base-defined `scripts/validate_write_boundary.py`, and reads the live
write authority from the **issues of its own repository** (`$GITHUB_REPOSITORY`,
`$PR_HEAD_REPO` from trusted event context). A fresh independent repository
therefore gets a default-deny fence: BUILD-lane PRs fail closed until that
repository establishes its own branch-bound authority issue, and the `save/*`
repository-history lane works with no issue at all. The shipped fence needs no
RHC remote, branch, secret, or setting; the exported tree ships
`ORCHESTRATOR.md`, `BUILDER.md`, `AGENT_HANDOFF.md`, the validator and the hook
installer, so the contract is self-servable by the consuming repository. This
is an assessment of the shipped product, not a redesign: any dedicated
hard-write-boundary policy/product change remains separately owned work.

### Python import closure

The Z proof additionally verifies the exported Python import closure: every
exported `.py` file parses (syntax closure), and every absolute import either
resolves to an exported file (by the repository's own import conventions: the
importer's directory, `scripts/`, and the `tests/` suite directories) or is the
standard library or a module declared by the shipped `requirements.txt`. A
locally-imported module excluded from the export fails the proof closed.
Relative imports are resolved by Python's own package machinery at collection
time and are outside the static guard's reach (documented residual limit).

## Product identity acceptance (POST-EV2-Z7)

A clean canvas is a new campaign's starting tree, so it must not assert the
source campaign's identity. Two current defects are owned here, and neither is
grounds to alter an existing RHC source file:

- the root `README.md` was COPY, so the exported canvas shipped RHC's own
  README declaring itself the live Rolling High Club campaign;
- `characters/madma/NARRATIVE_DIRECTION.md` was GENERATE_EMPTY at a
  campaign-specific path, and the exporter preserved the named
  `characters/madma/` folder skeleton even though its generated body was neutral.

The repairs are structural and live in the policy; they touch no source byte:

- `README.md` is now **GENERATE_EMPTY**: the exported root README is a fixed,
  campaign-neutral policy constant (it names no campaign and links only to
  retained control surfaces). RHC's source `README.md` is untouched.
- every named source-owned skeleton is gone: `characters/madma/` (which held
  only the neutral `NARRATIVE_DIRECTION.md`) and the empty `npc/profiles/bor-family/`
  are **EXCLUDE** directory prefixes whose stale named folder skeletons the
  policy's `identity.omitted_skeleton_prefixes` omits, so neither a file nor an
  empty named directory is created. Every generic campaign folder skeleton
  (`characters/`, `npc/profiles/`, …) is unaffected.

The policy carries an `identity` block that declares what the *emitted artifact*
must not carry:

- `path_tokens` — source-owned campaign identity tokens that must not appear in
  any emitted path (file **or** preserved directory skeleton);
- `content_surfaces` — emitted user-facing surfaces whose actual bytes must not
  contain the declared content tokens (`README.md` must not carry
  `Rolling High Club` or `rhc-primary`);
- `omitted_skeleton_prefixes` — directory prefixes whose stale named skeleton is
  not recreated. Each is validated fail-closed: it must be a clean
  repository-relative directory owned by an EXCLUDE directory rule.

`identity_acceptance` is **independent verification of the emitted artifact** —
not a classification input: it never rewrites a copied byte and never
reclassifies a path. The export applies it in two stages:

- an **early expected-tree preflight** on the planned output paths and intended
  bytes (COPY blob or generated constant), so a predicted leak fails fast with
  no output tree created; then
- an authoritative **post-materialization inspection** of the ACTUAL completed
  output: it scans the real emitted path set (exported files **and** directory
  skeletons) with one strict, no-follow `os.scandir` walk for every path token,
  reads each declared content surface through its real on-disk bytes, compares
  the actual path inventory against the authorized expected inventory, and
  verifies the **path kind** of every authorized output with a no-follow
  `os.lstat` — so a regular file and a symlink that share a relative path are not
  collapsed onto the same bare string. The walk fails closed on any unscannable
  directory or unreadable entry, so `os.walk`'s documented silent drop of a
  `scandir` error (or a swallowed `DirEntry` classification error) can never
  certify a partial inventory. A regular file substituted by a symlink, or a
  preserved skeleton replaced by a symlink, fails closed, while a legitimate Git
  `120000` COPY symlink is expected to remain an actual on-disk symlink (it is
  never silently treated as a regular file). A leaked path token, a mutated
  content surface, an extra (even token-free) path, a missing authorized path, a
  substituted path kind, altered bytes, a changed executable bit, or any
  unreadable path/scan failure fails the export closed **before any accepted
  receipt is written**, so the receipt can never certify the predicted pre-write
  tree, a substituted link, or bytes/modes that are not on disk.

Alongside the path/kind inventory, every emitted regular file's real bytes — or a
legitimate authorized symlink's real `readlink` target — are attested by SHA-256
against the exact intended digest the receipt records for that output, closing the
sibling false-certification where a token-free but altered materialized file could
otherwise pass while the receipt held only the intended blob SHA, and every
emitted regular file's real POSIX mode is verified against its authorized Git
`100755`/`100644` mode, closing the sibling where a post-write executable-bit
change (a 0755 → 0644 ``100755`` COPY downgrade, or an accidental 0644 → 0755 bit)
leaves the path kind and bytes identical. A declared content surface is read only
from an `lstat`-confirmed regular path (or scanned by its link target), never by
following a substituted symlink to a file outside the canvas.

POSIX permission fidelity is a platform-bounded guarantee: it is asserted only
where the host exposes permission bits (`os.name == 'posix'`). On Windows
`os.chmod` only toggles the read-only attribute, so a Git `100755` executable bit
is not representable; there the mode contract is not asserted, while
path/kind/byte attestation still applies. The Ubuntu CI job runs the
executable-mode proofs for real.

On acceptance the receipt records that post-write evidence. A top-level,
machine-readable `artifact_attestation` states what this host actually proved:
`path_inventory`, `path_kind` and `content_digest` are `verified` on every host,
while `posix_mode` is derived from the same capability predicate the verifier
uses — `verified` where the host exposes permission bits and every emitted
regular file passed its authorized Git `100755`/`100644` mode, or
`not_observable` where the host cannot represent them and the mode contract was
not asserted. The receipt therefore never implies a mode proof it did not make.
The durable `identity_acceptance` evidence is kept as identity-only evidence
(`accepted`, `violations: []`, the declared tokens/surfaces, the omitted skeleton
prefixes and the ACTUAL emitted path count); its `accepted` boolean is not
overloaded to mean platform mode proof.

The scope is deliberately narrow. This is **not** general de-branding: stable
runtime/SQL/API identifiers containing `RHC`, reusable engine docs, historical
provenance and attributions stay out of scope, and no generic `RHC` substring
removal is performed anywhere. The exception surface is exactly the declared
`identity` block, so the durable guard cannot invent product requirements or
confuse source attribution with new-campaign canon.

## Shape of a clean canvas

- reusable engine: `schemas/`, `scripts/`, `supabase/migrations/`,
  `supabase/baselines/`, `config/`, `systems/`, `.githooks/`, and the reusable
  engine/proof tests;
- reusable control/docs: the workspace routers and engine contracts, kept only
  where their link routes resolve;
- campaign folder skeleton preserved (`canon/`, `characters/`, `npc/`,
  `locations/`, `quests/`, `inventory/`, `state/`, `knowledge/`, `realities/`,
  `entities/`, `beyond_the_heroes/`, `planned/`, `brainstorm/`, `villain/`);
- declared mutable campaign roots generated EMPTY / UNKNOWN:
  `state/daily_recap.json`, `state/day_resolution.json`, `state/dm_meta.json`,
  `state/live_status.json`, `knowledge/facts.json`, `npc/npc_state.json`,
  `quests/narrative_hooks.json`, and the campaign-neutral root reality
  `realities/registry/campaign-root.json` emitted with the neutral
  `reality:campaign-root` identity, plus the campaign-neutral generated
  `README.md`, blank `canon/timeline.md`, `CHANGELOG.md` and
  `ENGINE_CHANGELOG.md`.

The clean genesis emits a campaign-neutral root identity **and path**, not the
RHC-specific `reality:rhc-primary`: POST-EV2-Z3 removed the reusable engine's
hard dependency on that one literal id, so the root is now the structural role
of the unique parentless reality. The source rule still matches RHC's tracked
`realities/registry/rhc-primary.json` (classification is source-path-based),
but its GENERATE_EMPTY rule declares the campaign-neutral `output_path`
`realities/registry/campaign-root.json`, so the generated root is materialized
there and the RHC-specific path is never created in the canvas. RHC itself
keeps its existing canonical `reality:rhc-primary` record unchanged (it
remains the RHC root), but a clean or new campaign initializes a different
valid root reality id without editing or forking the engine. Real campaign
instance records and campaign-history prose are excluded.

## Proof matrix

`tests/post_ev2_z/test_clean_campaign_export.py` proves:

- branch/base binding and the cumulative Mission diff stays in the Surface
  Budget (the POST-EV2-Z five created files plus the single authorized
  `requirements.txt` PyYAML line; and, for the POST-EV2-Z.1 extension, the
  created `ENGINE_VERSION` source plus the modified policy, exporter, proof,
  workflow and this document);
- every tracked path has exactly one disposition; unclassified and ambiguous
  paths fail closed; a `COPY` directory prefix is rejected;
- the receipt records a comparable `engine_version` read from the exact
  commit's single `ENGINE_VERSION` source of truth, and a missing or malformed
  version source fails the export closed;
- classification is path-only;
- COPY bytes/modes are byte-identical to the exact Git blobs;
- EXCLUDE surfaces, lore docs, lore tests and factory machinery are absent;
- generated mutable roots are EMPTY/UNKNOWN and pass the canonical-root
  validator; the clean genesis root reality is emitted at the campaign-neutral
  `realities/registry/campaign-root.json` path (never the RHC-specific
  `rhc-primary.json` path) and the exported neutral registry passes the engine
  reality validator;
- every retained control-plane route (Markdown links **and** workflow `run:`
  command routes, decoded by a structural YAML parse and resolved against each
  step's effective working directory) resolves, and a synthetic dangling route
  of either species — including an escaped-key `run:` step invoking an excluded
  path and a working-directory-relative `run:` step invoking an excluded path —
  fails closed. POST-EV2-Z6 extends the check to the generated policy bytes of
  GENERATE_EMPTY control-plane surfaces, makes executable workflow routes
  unsatisfiable by empty preserved skeletons, fails closed on a static route
  naming a path that exists nowhere, on a local `uses: ./action` directory
  whose files lack the required `action.yml`/`action.yaml` metadata, and on a
  static `working-directory` that exists nowhere — each with its own
  non-vacuous negative. The Z6 path-kind repair adds: a repo-root local action
  (`uses: ./` or `uses: .//`) is checked (never silently discarded) and
  resolves only when the exported root ships `action.yml`/`action.yaml`, with
  missing, unrelated-file-only and EXCLUDE-only root metadata failing closed;
  and a static `working-directory` naming an exported *file* fails closed at
  every effective level (workflow, job and step), since a runner cannot change
  directory into a file;
- dynamically computed workflow route operands (a path operand carrying a
  `${{ ... }}` expression anywhere, including a fragment separated from it by a
  slash), and every repo-relative operand of a step whose
  effective `working-directory` cannot be statically resolved, are consciously
  unproven: the receipt records them in `unresolved_dynamic_routes` instead of
  silently accepting them, so a shipped root-level path can never falsely
  satisfy a dependency the referencing step does not actually reach;
- the exported RT01 runtime workflow is the policy-generated portability
  adaptation: its bytes are a fixed policy constant equal to the source
  workflow minus exactly the four audited source-only pytest arguments
  (`tests/ev2121`, `tests/post_ev2_2`, `tests/post_ev2_9`,
  `tests/post_ev2_10`), the four source-only trees stay policy-EXCLUDE with
  their recorded ownership rationale, and the Z proof's sync guard proves the
  generated bytes cannot drift from the source workflow across the whole
  top-level contract as well as the job bodies, with a non-vacuous
  top-level-divergence negative;
- the Mission-local workflow's clean-canvas job executes every exported RT01
  shard command verbatim inside the exported canvas with the shipped
  PostgreSQL services, failing closed on a non-zero exit or a shard that
  proves nothing (no tests passed), with an inside-canvas binding negative;
- the exported Python import closure resolves (syntax + absolute imports
  against exported files / stdlib / the declared requirements), and excluding
  a locally-imported module fails the guard closed;
- the Mission-local workflow's clean-canvas job lints the two emitted
  workflows with the immutably pinned `rhysd/actionlint` v1.7.12 release
  (archive SHA-256 verified before extraction/execution), from outside the
  emitted tree, with shellcheck/pyflakes disabled and no broad suppression,
  and a deliberately invalid workflow fixture provably makes the lint gate
  fail (non-vacuous);
- `--repo-root` must equal the true Git top level before the source/destination
  overlap guards are trusted;
- `--ref` resolves to an exact, peeled commit object, never a tag/tree object;
- `--report-references` prints the dangling-route diagnostic it computes;
- repeated export is byte/path/mode/receipt deterministic;
- the source tree is unchanged;
- destructive overwrite and source/output overlap are refused;
- the export initializes as an independent repository;
- the exported test suite is free of RHC character/NPC fixture names;
- the ACTUAL emitted artifact carries no declared source campaign identity: no
  emitted path (exported file or preserved directory skeleton) carries a
  declared identity path token, and every declared identity content surface
  (`README.md`) is emitted campaign-neutral; the receipt records the
  machine-readable `identity_acceptance` evidence for the completed tree, and an
  intentionally injected named entity path, a synthetic campaigned root README,
  and a named `characters/madma/` skeleton without its file each fail the export
  closed. The guard is applied to the ACTUAL post-materialization output: an
  identity-bearing file or empty named directory injected during writing, a root
  README altered after the precheck, and a token-free unlisted extra path each
  fail the export closed with no accepted receipt ever written; the inspector
  reads each entry's no-follow filesystem kind, so a root README or a regular
  non-content file substituted by a symlink to a neutral external file fails the
  path-kind contract, a legitimate Git `120000` COPY symlink is accepted by its
  exact `readlink` target rather than as a regular file, and a token-free but
  altered materialized regular file fails the byte-provenance attestation. The
  inspector is also traversal-complete and executable-mode-aware: an expected
  preserved directory that cannot be scanned (with a hidden unlisted child) fails
  the export closed instead of being silently dropped, and a post-write
  executable downgrade (0755 → 0644) or an accidental execute bit (0644 → 0755)
  fails the POSIX-mode attestation — proven on the Ubuntu CI job, and not
  asserted on a host such as Windows that cannot represent the bit — while a
  clean export keeps `.githooks/pre-commit` at 0755 and non-executable surfaces
  at 0644. The receipt records this capability-honestly in a top-level
  `artifact_attestation`: `path_inventory`, `path_kind` and `content_digest` are
  `verified` on every host, and `posix_mode` is `verified` only where the host
  exposes permission bits and the mode contract fully passed, else
  `not_observable` — never a silent `verified`;
- RHC's own source `README.md`, `characters/madma/NARRATIVE_DIRECTION.md` and
  every canon/gameplay surface are unchanged, and the exported root README is
  the campaign-neutral generated genesis;
- no shipped executable/structured surface (COPY or policy-generated) carries
  the remapped RHC-only primary-reality identity (a synthetic stale copied
  reference fails the guard closed), and the mission-local workflow executes
  the COPY-shipped POST-EV2-14 suite from inside the exported canvas, where it
  resolves the primary reality by its structural role. The copied suite is a
  portable bounded-lifecycle proof with no source/factory-only assertion and
  no context discriminator; this EXCLUDE-owned factory proof owns the
  equivalent source wiring assertions — the source Entity V2 workflow runs the
  POST-EV2-14 suite, the export policy classifies the POST-EV2-14 surfaces as
  COPY, and a fresh export contains them;
- every shipped surface the guard scans is admitted into this proof: the
  workflow's declared path-filter patterns provably select every scanned
  surface (COPY plus GENERATE_EMPTY, minus prose `*.md`) in both events, and
  an uncovered scanned surface fails closed;
- the Z workflow is Mission-local, triggers on every Mission surface including
  `ENGINE_VERSION` (so a version-only change still runs the proof),
  `requirements.txt` and the copied POST-EV2-14 test surface, and checks out
  the exact PR head;
- existing global workflows are unmodified and `git diff --check` is clean.

## Non-goals

POST-EV2-Z does not place, publish or provision the canvas repository, build a
Copier template, provision per-campaign databases/save slots, import real RHC
campaign history, or move RHC's own campaign out of this repository. It does
not harden against hostile concurrent filesystem mutation (this exporter is
trusted local/CI build tooling). It does not add or change any runtime mutation
domain or same-save compatibility edge (Mutation / Compatibility Declaration:
**NO**).
