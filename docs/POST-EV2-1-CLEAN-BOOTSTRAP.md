# POST-EV2-1 Patch 1D — Clean Bootstrap / Baseline Equivalence

## Purpose

Patch 1D closes POST-EV2-1 by giving fresh RHC runtime environments one verified bootstrap artifact without rewriting, deleting, renaming or superseding the historical migration chain.

The historical chain remains the authoritative upgrade and audit path for existing databases.

The clean baseline is valid only for a new/empty environment.

## Exact cut point

Repository cut point:

`d3292fd53cbb162a9e13c9e6148f88cfc474fa75`

Historical migration frontier:

1. `20260908000001_rt01a_published_runtime_floor.sql`
2. `20260908000002_rt01a_bootstrap_unknown_runtime.sql`
3. `20260908000003_rt01b_save_gateway_mutation_boundary.sql`
4. `20260908000004_rt01c_runtime_published_git_handshake.sql`
5. `20260908000005_rt01c_bind_runtime_mirror_base.sql`
6. `20260908000006_rt01d_dm_read_engineering_release.sql`
7. `20260911000001_rt02_campaign_clock.sql`
8. `20260911000002_rt03_canonical_run_runtime_read.sql`
9. `20260912000001_rt04_safe_run_reconciliation.sql`
10. `20260914000001_hwb02_save_runtime_authority.sql`
11. `20260915000001_ev210_inventory_ownership.sql`
12. `20260917000001_ev211_item_custody.sql`
13. `20260919000001_ev2121_item_identity_admission.sql`
14. `20260919000002_ev213_mutable_entity_state.sql`
15. `20260920000001_ev213420_temporal_core.sql`
16. `20260920000002_ev2131_timed_status_continuity.sql`
17. `20260923000001_post_ev2_1_save_domain_policy_registry.sql`
18. `20260923000002_post_ev2_1_same_save_compatibility_dispatcher.sql`

The clean baseline artifact is:

`supabase/baselines/20260924_post_ev2_1_clean_bootstrap.sql`

## Why the baseline is a flattened replay

Patch 1D intentionally does **not** perform a semantic SQL rewrite, migration squash, history deletion, or `pg_dump`-generated canonical schema snapshot.

The safest first baseline is a single file that contains the exact reviewed historical migration bodies in the exact same order, with only baseline metadata and source-boundary comments added around them.

This shape has three useful properties:

- it creates no new runtime semantics;
- it can be proven source-identical to the exact historical frontier;
- it gives future fresh environments one bounded bootstrap artifact while preserving migration history unchanged.

A later Mission may decide whether a more compact semantic baseline is worth the extra normalization risk. Patch 1D does not make that decision.

## Authority and ownership

- RT01 remains the only Save / stage / publish / mirror / confirm spine.
- Patch 1A remains runtime mutation-domain admission truth.
- Patch 1B remains same-save compatibility truth.
- Dedicated domain routes retain semantic ownership.
- Historical migrations remain the upgrade/audit authority.
- The baseline is fresh-install convenience only. It is not a new migration system, runtime authority, or persistence path.

Mutation / Compatibility Declaration for Patch 1D: **NO**.

Patch 1D adds no mutation domain and changes no compatibility edge.

## Fresh-environment contract

A legal clean bootstrap starts from an empty PostgreSQL database that already has the Supabase baseline roles:

- `anon`
- `authenticated`
- `service_role`

The baseline then reconstructs the pinned runtime frontier, including the engine-owned verifier role and every established runtime object.

Do not apply the baseline to an existing RHC runtime database.

Existing databases continue to upgrade by applying historical migrations in order.

## Equivalence proof

`tests/post_ev2_1/test_clean_bootstrap_equivalence.py` runs on real PostgreSQL 15 and PostgreSQL 17.

The proof has two layers.

First, it proves source binding:

- the repository contains exactly the pinned 18 migration filenames;
- the baseline lives outside `supabase/migrations/`;
- the baseline body is exactly the ordered migration contents plus deterministic source markers;
- therefore a baseline drift cannot silently diverge from the pinned frontier.

Second, it proves effective runtime convergence by installing both paths into separate fresh disposable databases on each PostgreSQL version and comparing:

- public relations and RLS flags;
- columns/defaults/nullability;
- constraints;
- indexes;
- triggers;
- RLS policies;
- routine signatures, volatility, security mode, ACLs and definitions;
- views;
- relevant table/routine grants;
- verifier-role safety state;
- Unknown-safe runtime seed state;
- Patch 1A domain-policy outputs;
- Patch 1B same-save compatibility-policy outputs;
- representative Save Gateway behavior:
  - one legal generic write path;
  - one dedicated-domain generic-bypass rejection;
  - abort returns the runtime to its original unpublished state.

The proof deliberately ignores unstable object identifiers and wall-clock timestamps.

## Unknown-safe bootstrap

The baseline preserves the established RT01 bootstrap law:

- published generation = 0;
- no pinned Git ref;
- no published day;
- no active save;
- no campaign-state rows.

No real campaign data is embedded in the baseline.

## CI

The existing `.github/workflows/rt01-runtime.yml` owns runtime PostgreSQL proof.

Patch 1D extends that workflow only enough to execute `tests/post_ev2_1/**` against its already-existing PostgreSQL 15 and PostgreSQL 17 services.

No second CI runtime, migration engine or long-lived baseline generator is introduced.

## Non-goals

Patch 1D does not:

- deploy Patch 1A or Patch 1B to production Supabase;
- rewrite or squash migration history;
- change runtime behavior;
- add a mutation domain or compatibility edge;
- migrate production data;
- start POST-EV2-2;
- import real campaign data, BTH, Story/RAG or UI work;
- publish POST-EV2-1 changelog/ledger closeout before the patch itself clears merge and post-merge proof.

## Operational rule

For a fresh environment:

1. provision the Supabase baseline roles;
2. apply `supabase/baselines/20260924_post_ev2_1_clean_bootstrap.sql`;
3. continue only with migrations created **after** the pinned Patch 1D frontier.

For an existing environment:

1. never apply the clean baseline;
2. continue the historical migration chain normally.

This keeps one runtime architecture with two legitimate installation histories: historical upgrade replay for existing databases, and one verified pinned baseline for empty databases.
