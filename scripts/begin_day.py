#!/usr/bin/env python3
"""POST-EV2-11 -- Begin Day / Fresh-Day DM Boot conductor.

Begin Day is a *conductor*, not another truth owner. It opens exactly the next
live campaign day by:

1. reading the current publishable day-boundary bundle through the POST-EV2-11
   service read (``public.dm_begin_day_read()``);
2. refusing a day skip, a backwards day, an Unknown/incoherent current day, or a
   previous day that was never finalized into ``canon/days/day_XXX.md``;
3. reading the exact previous finalized day record directly (never through
   broad retrieval);
4. staging today's live handoff for the existing day-boundary owners plus the
   RT02 Campaign Clock, changing only the day-boundary fields;
5. dispatching only *configured* daily consumers in a deterministic bounded
   order, with every mechanic's required randomness routed through the single
   shared resolver (``scripts/dice_resolver.py``, POST-EV2-8) via a declared
   dispatch seam; production may have zero consumers, in which case no roll is
   invented. A consumer may additionally return one optional ``state_patch`` --
   a flat object of top-level ``live_status`` keys to replace -- which Begin Day
   *transports* to the existing RT01 publication path without interpreting the
   mechanic; only the already-active ``live_status`` owner is eligible, protected
   conductor/schema fields are refused, and the change is never reapplied on
   retry;
6. publishing once through the existing RT01 Save Gateway with RT02 as the only
   day authority, then requiring the existing mirror/verifier confirmation; and
7. returning a derived *Fresh-Day DM Boot Packet* -- yesterday's full finalized
   record plus today's compact published context and today's resolved mechanics.

It adds no runtime key, mutation domain, save engine, controller ledger, RNG
root, Hook lifecycle or history store. It never rewrites unrelated entities,
never fabricates elapsed time/phase/Rest, and never persists the boot packet
(that is derived read output).

Retry law: if the requested day is already the healthy published day, Begin Day
rehydrates -- it never reruns daily mechanics or produces a second set of rolls,
and it restores the exact finalized previous-day memory (identity, path and
content) in the rehydrated boot packet; a rehydration that cannot prove that
memory fails closed. Publication followed by a mirror-confirmation failure is
reported as a pending failure, never as success; the caller repairs the *same*
generation.

Durability law: under default (non-autocommit) DB-API behavior a function-level
publication success is still uncommitted client state, so the production gateway
seam commits the client transaction at publication and after confirmation. A
successful Begin Day is only ever reported for a durably committed generation.

Generation-pinning law: the returned Fresh-Day DM Boot Packet is built from one
published read pinned to the exact generation that satisfied Begin Day
confirmation. A concurrent/later publication can never mix another generation's
context into the packet; any mismatch fails closed.
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dice_resolver  # noqa: E402  (the single shared RNG root, POST-EV2-8)

MAX_DAILY_CONSUMERS = 64
MAX_DAILY_EFFECTS = 1000

# The existing generic day-boundary owners. Begin Day only ever changes their
# day-boundary fields; unrelated content is carried forward untouched.
ALWAYS_INITIALIZED_OWNERS = ("daily_recap", "day_resolution", "narrative_hooks")
OPTIONAL_DAY_STAMPED_OWNERS = ("live_status", "dm_meta")
DAY_BOUNDARY_OWNER_KEYS = ALWAYS_INITIALIZED_OWNERS + OPTIONAL_DAY_STAMPED_OWNERS

_EFFECT_KEYS = (
    "rng_rolls",
    "mechanical_resolutions",
    "persistent_effects_applied",
    "notes",
)

# A daily consumer may additionally return one optional ``state_patch``: a flat
# object of top-level ``live_status`` keys to replace. Begin Day transports the
# declared current-state change to the existing RT01 publication path; it never
# interprets the mechanic. Only the already-active ``live_status`` owner is
# eligible -- Begin Day never initializes an owner on a consumer's behalf and
# never widens this channel to another owner or a dedicated namespace.
_STATE_PATCH_KEY = "state_patch"
_MAX_STATE_PATCH_KEYS = 64

# Fields owned by the conductor / the owner's own schema. A consumer patch may
# never overwrite them, so a transported state change can never move the
# day-boundary or fabricate a schema version.
_PROTECTED_LIVE_STATUS_KEYS = frozenset({"current_day", "schema_version"})


class BeginDayError(Exception):
    """A fail-closed Begin Day authority/sequence/publication failure."""


# ---------------------------------------------------------------------------
# Finalized-day store (exact path, never broad retrieval)
# ---------------------------------------------------------------------------


class RepositoryFinalizedDayStore:
    """Reads the exact previous finalized day record from ``canon/days/``.

    The previous day is *known*, so it is read by exact path. Broad RAG/older
    story retrieval (POST-EV2-6) is deliberately never used to rediscover it.

    The SAVE boundary admits a finalized day under any legal spelling
    ``canon/days/day_<positive decimal integer>.md``: leading zeroes are legal
    and there is no digit-count ceiling (``day_1.md``, ``day_01.md``,
    ``day_001.md``, ``day_0001.md`` and ``day_12547.md`` are all legal). A record
    is therefore resolved by *numeric day identity*, never by one fixed filename
    width. ``read_finalized_record`` returns the *exact* path it opened alongside
    the text -- a legal unpadded archive is never reported or persisted as a
    fabricated canonical-looking padded path, and vice versa. If more than one
    legal file resolves to the same numeric day, the reader fails closed as
    ambiguous rather than silently choosing one.
    """

    _FINALIZED_MARKER = "Finalized Campaign Record"
    _LEGAL_NAME = re.compile(r"^day_(?P<day>[0-9]+)\.md$")

    def __init__(self, root, days_dir="canon/days"):
        self._root = str(root)
        self._days_dir = days_dir

    def _legal_names_for_day(self, day):
        directory = os.path.join(self._root, self._days_dir)
        try:
            entries = os.listdir(directory)
        except OSError:
            return []
        names = []
        for name in entries:
            match = self._LEGAL_NAME.match(name)
            if match is None or int(match.group("day")) != day:
                continue
            if os.path.isfile(os.path.join(directory, name)):
                names.append(name)
        return sorted(names)

    def read_finalized_record(self, day):
        """Return ``(exact_path, text)`` for the finalized record actually read.

        ``(None, None)`` means no finalized record exists at a legal path, so
        Begin Day fails closed. A legal file that exists but is not a finalized
        record is treated as unfinalized truth (also ``(None, None)``). Multiple
        legal files resolving to the same numeric day raise ``BeginDayError`` as
        an ambiguity that must never be resolved silently. The returned path is
        the exact path that was opened, never a synthesized alternative.
        """
        names = self._legal_names_for_day(day)
        if not names:
            return (None, None)
        if len(names) > 1:
            raise BeginDayError(
                "ambiguous finalized-day files for Day %d: %s; refusing to choose "
                "one silently" % (day, ", ".join(names))
            )
        name = names[0]
        with open(
            os.path.join(self._root, self._days_dir, name), "r", encoding="utf-8"
        ) as handle:
            text = handle.read()
        if self._FINALIZED_MARKER not in text:
            return (None, None)
        return ("%s/%s" % (self._days_dir, name), text)


# ---------------------------------------------------------------------------
# Declared dispatch seam (the only randomness path for daily consumers)
# ---------------------------------------------------------------------------


class DailyDispatchSeam:
    """The declared seam a daily consumer uses for mechanically required rolls.

    Consumers receive this object and never call raw ``random.*`` themselves.
    When no ``rng`` is injected the shared resolver uses production randomness;
    ``rng`` is an explicit test-only seam.
    """

    def __init__(self, rng=None, resolver=None):
        self._rng = rng
        self._resolver = resolver or dice_resolver.resolve
        self.calls = 0

    def roll(self, request, source):
        if not isinstance(source, str) or not source.strip():
            raise BeginDayError("daily dispatch requires a non-empty roll source")
        self.calls += 1
        return self._resolver(request, rng=self._rng)


# ---------------------------------------------------------------------------
# Candidate builders (change only day-boundary fields)
# ---------------------------------------------------------------------------


def _as_object(value):
    return dict(value) if isinstance(value, dict) else {}


def _hook_ids(hooks_value):
    hooks = _as_object(hooks_value)
    active = hooks.get("active_hooks")
    if not isinstance(active, list):
        return []
    ids = []
    for entry in active:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.append(entry["id"])
        elif isinstance(entry, str):
            ids.append(entry)
    return ids


def _new_campaign_clock(published_clock, day):
    clock = _as_object(published_clock)
    # Only the day changes. Elapsed minutes, broad phase and Long-Rest count are
    # carried forward exactly; Begin Day never invents time, phase or Rest.
    return {
        "schema_version": clock.get("schema_version", 1),
        "day": day,
        "phase": clock.get("phase", "unknown"),
        "elapsed_campaign_minutes": clock.get("elapsed_campaign_minutes", 0),
        "long_rests_completed": clock.get("long_rests_completed", 0),
    }


def _new_daily_recap(published, day, previous_path, carryover_hooks):
    recap = _as_object(published)
    recap["schema_version"] = recap.get("schema_version", 1)
    recap["status"] = "active"
    recap["current_day"] = day
    recap["current_summary"] = {
        "rng_highlights": [],
        "mechanical_handoff": [],
        "next_scene_handoff": [],
        "general_development": [],
    }
    recap["previous_day_record"] = previous_path
    recap["carryover_active_hooks_at_start"] = list(carryover_hooks)
    return recap


def _new_day_resolution(published, day):
    resolution = _as_object(published)
    resolution["schema_version"] = resolution.get("schema_version", 1)
    resolution["status"] = "active"
    resolution["current_day"] = day
    resolution["rng_rolls"] = []
    resolution["mechanical_resolutions"] = []
    resolution["persistent_effects_applied"] = []
    resolution["notes"] = []
    return resolution


def _new_narrative_hooks(published, day):
    hooks = _as_object(published)
    hooks["schema_version"] = hooks.get("schema_version", 1)
    hooks["day_status"] = "active"
    hooks["current_day"] = day
    hooks.setdefault("next_hook_id", "H01")
    hooks.setdefault("active_hooks", [])
    hooks.setdefault("dormant_hooks", [])
    # The current-day closure bucket is cleared by the conductor for the new day;
    # it never becomes a second Hook lifecycle owner.
    hooks["closed_hooks_today"] = []
    return hooks


def _new_day_stamped_owner(published, day):
    owner = _as_object(published)
    owner["current_day"] = day
    return owner


def _owner_present(value):
    return isinstance(value, dict) and bool(value)


# ---------------------------------------------------------------------------
# Consumer validation / ordering / merge
# ---------------------------------------------------------------------------


def _order_consumers(consumers):
    ordered = []
    seen = set()
    for consumer in consumers:
        consumer_id = getattr(consumer, "consumer_id", None)
        if not isinstance(consumer_id, str) or not consumer_id.strip():
            raise BeginDayError("a daily consumer requires a non-empty consumer_id")
        if consumer_id in seen:
            raise BeginDayError("duplicate daily consumer id: %r" % consumer_id)
        if not callable(getattr(consumer, "resolve", None)):
            raise BeginDayError("daily consumer %r has no resolve()" % consumer_id)
        seen.add(consumer_id)
        ordered.append(consumer)
    if len(ordered) > MAX_DAILY_CONSUMERS:
        raise BeginDayError(
            "configured daily consumers exceed the bound of %d" % MAX_DAILY_CONSUMERS
        )
    ordered.sort(key=lambda item: item.consumer_id)
    return ordered


def _merge_consumer_result(
    target, consumer_id, result, budget, live_status=None, patched_keys=None
):
    if result is None:
        return
    if not isinstance(result, dict):
        raise BeginDayError("daily consumer %r returned a non-object" % consumer_id)
    unknown = set(result) - set(_EFFECT_KEYS) - {_STATE_PATCH_KEY}
    if unknown:
        raise BeginDayError(
            "daily consumer %r returned unknown field(s): %s"
            % (consumer_id, sorted(unknown))
        )
    for key in _EFFECT_KEYS:
        entries = result.get(key)
        if entries is None:
            continue
        if not isinstance(entries, list):
            raise BeginDayError(
                "daily consumer %r field %r must be a list" % (consumer_id, key)
            )
        for entry in entries:
            if not isinstance(entry, dict):
                raise BeginDayError(
                    "daily consumer %r produced a non-object effect" % consumer_id
                )
            budget[0] += 1
            if budget[0] > MAX_DAILY_EFFECTS:
                raise BeginDayError(
                    "daily consumer effects exceed the bound of %d" % MAX_DAILY_EFFECTS
                )
            stamped = dict(entry)
            stamped["consumer_id"] = consumer_id
            target[key].append(stamped)
    if _STATE_PATCH_KEY in result:
        _merge_consumer_state_patch(
            live_status, consumer_id, result[_STATE_PATCH_KEY], patched_keys
        )


def _merge_consumer_state_patch(live_status, consumer_id, patch, patched_keys):
    """Transport one consumer's optional ``live_status`` state patch.

    The patch is a flat object of top-level ``live_status`` keys to replace; the
    value of each named key is replaced wholesale (no nested/deep merge) and
    every unmentioned key is carried forward untouched. Begin Day only
    *transports* the declared change to the existing RT01 publication path -- it
    never interprets the mechanic, never initializes an inactive owner on the
    consumer's behalf, never widens the channel to another owner or a dedicated
    namespace, and     never lets the patch overwrite a conductor/schema-owned field.
    The patch values are deep-copied so the returned consumer object cannot alias
    the staged candidate, and a key may be written by only one consumer in a day.
    An explicitly returned empty patch is malformed, not omitted, so it fails
    closed whether ``live_status`` is active or absent/inactive; an omitted
    ``state_patch`` key remains legal and transports nothing.
    """
    if not isinstance(patch, dict):
        raise BeginDayError(
            "daily consumer %r state_patch must be an object" % consumer_id
        )
    if not patch:
        raise BeginDayError(
            "daily consumer %r returned an explicitly empty state_patch; a "
            "declared patch is malformed rather than omitted and fails closed"
            % consumer_id
        )
    if live_status is None:
        raise BeginDayError(
            "daily consumer %r returned a state_patch but live_status is not an "
            "active day-boundary owner; Begin Day never initializes it on a "
            "consumer's behalf" % consumer_id
        )
    if len(patch) > _MAX_STATE_PATCH_KEYS:
        raise BeginDayError(
            "daily consumer %r state_patch exceeds the bound of %d keys"
            % (consumer_id, _MAX_STATE_PATCH_KEYS)
        )
    for key, value in patch.items():
        if not isinstance(key, str) or not key.strip():
            raise BeginDayError(
                "daily consumer %r state_patch key must be a non-empty string"
                % consumer_id
            )
        if key in _PROTECTED_LIVE_STATUS_KEYS:
            raise BeginDayError(
                "daily consumer %r state_patch may not overwrite protected "
                "live_status key %r" % (consumer_id, key)
            )
        if patched_keys is not None and key in patched_keys:
            raise BeginDayError(
                "live_status key %r was already written by another daily "
                "consumer; conflicting state_patch writes fail closed" % key
            )
        if patched_keys is not None:
            patched_keys.add(key)
        live_status[key] = copy.deepcopy(value)


# ---------------------------------------------------------------------------
# Boot packet (derived, never persisted)
# ---------------------------------------------------------------------------


def _build_boot_packet(
    mode,
    day,
    previous_day,
    previous_path,
    previous_text,
    bundle,
    today_resolution,
):
    current = _as_object(bundle.get("current"))
    resolution = _as_object(today_resolution)
    return {
        "packet_version": 1,
        "mode": mode,
        "day": day,
        "previous_day": {
            "day": previous_day,
            "finalized_record_path": previous_path,
            "finalized_record": previous_text,
        },
        "current_context": {
            "published_day": current.get("published_day"),
            "published_generation": _published_generation(bundle),
            "runtime": bundle.get("runtime"),
            "campaign_clock": current.get("campaign_clock"),
            "daily_recap": current.get("daily_recap"),
            "day_resolution": current.get("day_resolution"),
            "narrative_hooks": current.get("narrative_hooks"),
            "live_status": current.get("live_status"),
            "dm_meta": current.get("dm_meta"),
        },
        "today_mechanics": {
            "rng_rolls": resolution.get("rng_rolls", []),
            "mechanical_resolutions": resolution.get("mechanical_resolutions", []),
            "persistent_effects_applied": resolution.get(
                "persistent_effects_applied", []
            ),
            "notes": resolution.get("notes", []),
        },
    }


# ---------------------------------------------------------------------------
# Conductor
# ---------------------------------------------------------------------------


def open_next_day(
    requested_day,
    *,
    runtime,
    finalized_store,
    consumers=(),
    dispatch_rng=None,
    resolver=None,
):
    """Open exactly the next live campaign day and return a boot packet.

    ``runtime`` implements the RT01/RT02 gateway seam (published read, begin,
    stage, clock, publish, confirmation, abort). ``finalized_store`` implements
    ``read_finalized_record`` (returning the exact path read alongside the text).
    ``dispatch_rng`` is the explicit test-only RNG seam
    forwarded to the shared resolver; production leaves it ``None``.
    """
    if isinstance(requested_day, bool) or not isinstance(requested_day, int):
        raise BeginDayError("requested day must be an integer")
    if requested_day < 1:
        raise BeginDayError("requested day must be a positive campaign day")

    ordered_consumers = _order_consumers(consumers)

    bundle = runtime.read_published()
    if not isinstance(bundle, dict):
        raise BeginDayError("begin-day read returned a non-object")
    current = _as_object(bundle.get("current"))
    coherence = _as_object(bundle.get("coherence"))

    if not coherence.get("coherent", False):
        issues = coherence.get("issues") or []
        raise BeginDayError(
            "published day-boundary owners are incoherent: " + "; ".join(issues)
        )

    clock_day = coherence.get("clock_day")
    published_day = clock_day if isinstance(clock_day, int) else None
    if published_day is None:
        raise BeginDayError(
            "current published day is Unknown; Begin Day requires a healthy "
            "finalized Day N"
        )

    # Retry / rehydrate: the requested day is already the published day.
    if requested_day == published_day:
        observed_generation = _published_generation(bundle)
        if not _is_exact_int(observed_generation):
            raise BeginDayError(
                "published runtime generation is not a verifiable integer; Begin "
                "Day cannot pin a rehydrated boot packet"
            )
        if not runtime.ensure_confirmed():
            raise BeginDayError(
                "Day %d is published but not yet mirror-confirmed; repair the "
                "same generation before reporting success" % published_day
            )
        rehydrated = _pinned_confirmed_bundle(
            runtime, observed_generation, published_day
        )
        # Rehydration must restore the exact finalized previous-day memory; a
        # packet with null placeholders would silently degrade the Fresh-Day DM
        # boot contract, so a missing record fails closed.
        previous_day = published_day - 1
        previous_path, previous_text = finalized_store.read_finalized_record(
            previous_day
        )
        if previous_text is None:
            raise BeginDayError(
                "rehydrating Day %d requires the exact finalized Day %d record; "
                "degraded Fresh-Day boot memory fails closed"
                % (published_day, previous_day)
            )
        published_recap = _as_object(
            _as_object(rehydrated.get("current")).get("daily_recap")
        )
        if published_recap.get("previous_day_record") != previous_path:
            raise BeginDayError(
                "published Day %d handoff points at %r, not the finalized Day %d "
                "record %r; refusing a degraded rehydrated boot packet"
                % (
                    published_day,
                    published_recap.get("previous_day_record"),
                    previous_day,
                    previous_path,
                )
            )
        return _build_boot_packet(
            "rehydrated_day_boot",
            published_day,
            previous_day,
            previous_path,
            previous_text,
            rehydrated,
            _as_object(rehydrated.get("current")).get("day_resolution", {}),
        )

    # Exact +1 only. Skips and backwards days fail closed.
    if requested_day != published_day + 1:
        raise BeginDayError(
            "day sequence refused: requested Day %d is neither the current Day %d "
            "(retry) nor the next Day %d" % (requested_day, published_day, published_day + 1)
        )

    # The prior day is known, so it is read by exact path; the path persisted in
    # the new handoff and returned in the boot packet is the exact path that was
    # actually read (never a fabricated canonical-looking width).
    previous_path, previous_text = finalized_store.read_finalized_record(published_day)
    if previous_text is None:
        raise BeginDayError(
            "previous Day %d is not finalized; Begin Day refuses to open Day %d"
            % (published_day, requested_day)
        )

    hooks_owner = _as_object(current.get("narrative_hooks"))
    carryover_hooks = _hook_ids(hooks_owner)

    candidate = {
        "campaign_clock": _new_campaign_clock(current.get("campaign_clock"), requested_day),
        "daily_recap": _new_daily_recap(
            current.get("daily_recap"), requested_day, previous_path, carryover_hooks
        ),
        "day_resolution": _new_day_resolution(current.get("day_resolution"), requested_day),
        "narrative_hooks": _new_narrative_hooks(hooks_owner, requested_day),
    }
    for owner_key in OPTIONAL_DAY_STAMPED_OWNERS:
        if _owner_present(current.get(owner_key)):
            candidate[owner_key] = _new_day_stamped_owner(
                current.get(owner_key), requested_day
            )

    # Dispatch only configured daily consumers, in deterministic bounded order.
    dispatch = DailyDispatchSeam(rng=dispatch_rng, resolver=resolver)
    context = {
        "day": requested_day,
        "previous_day": published_day,
        "previous_day_record_path": previous_path,
        "phase": candidate["campaign_clock"]["phase"],
        "carryover_active_hooks": list(carryover_hooks),
    }
    effect_budget = [0]
    # Only an already-active live_status owner is eligible to receive a
    # consumer state patch; a consumer never implicitly initializes it. The
    # ``patched_keys`` set is shared across the bounded dispatch so two
    # consumers cannot write the same top-level live_status key in one day.
    live_status_target = (
        candidate.get("live_status")
        if _owner_present(current.get("live_status"))
        else None
    )
    patched_live_status_keys = set()

    # Persist once through the existing RT01 gateway with RT02 as day authority.
    token = runtime.begin_save()
    published = False
    try:
        for consumer in ordered_consumers:
            result = consumer.resolve(context, dispatch)
            _merge_consumer_result(
                candidate["day_resolution"],
                consumer.consumer_id,
                result,
                effect_budget,
                live_status_target,
                patched_live_status_keys,
            )
        runtime.stage_clock(token, candidate["campaign_clock"])
        for owner_key, value in candidate.items():
            if owner_key == "campaign_clock":
                continue
            runtime.stage_state(token, owner_key, value)
        result_generation = runtime.publish(token)
        published = True
        if not _is_exact_int(result_generation):
            raise BeginDayError(
                "publication did not report an exact durable generation; Begin "
                "Day refuses to return an unpinned boot packet"
            )
    except BeginDayError:
        if not published:
            _abort_quietly(runtime, token)
        raise
    except Exception as exc:  # noqa: BLE001 - fail closed, abort the candidate
        if not published:
            _abort_quietly(runtime, token)
        raise BeginDayError("Begin Day publication failed: %s" % exc) from exc

    # Publication alone is not completion: the existing mirror/read-back/verifier
    # confirmation must agree for the same generation.
    if not runtime.ensure_confirmed():
        raise BeginDayError(
            "Day %d was published but mirror confirmation is pending; repair the "
            "same generation before reporting success" % requested_day
        )

    # The packet is pinned to the exact confirmed Begin Day generation; a later
    # publication must never be mixed into the returned current context.
    final_bundle = _pinned_confirmed_bundle(runtime, result_generation, requested_day)
    return _build_boot_packet(
        "fresh_day_boot",
        requested_day,
        published_day,
        previous_path,
        previous_text,
        final_bundle,
        candidate["day_resolution"],
    )


def _published_generation(bundle):
    runtime_metadata = _as_object(bundle.get("runtime"))
    return runtime_metadata.get("generation")


def _is_exact_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _pinned_confirmed_bundle(runtime, expected_generation, expected_day):
    """Read the published world once and pin the boot packet to it.

    The returned bundle is the packet's only current-context source, so a
    concurrent/later publication can never mix another generation's facts into
    this Begin Day's result. Exact-generation coherence is proven here; anything
    else fails closed.
    """
    bundle = _as_object(runtime.read_published())
    metadata = _as_object(bundle.get("runtime"))
    generation = metadata.get("generation")
    if not _is_exact_int(generation):
        raise BeginDayError(
            "published runtime generation is not a verifiable integer; Begin Day "
            "refuses to return an unpinned boot packet"
        )
    if generation != expected_generation:
        raise BeginDayError(
            "published generation %r no longer matches the exact confirmed Begin "
            "Day generation %r; refusing a mixed-generation boot packet"
            % (generation, expected_generation)
        )
    if not (
        metadata.get("mirror_confirmed")
        and metadata.get("last_confirmed_generation") == generation
    ):
        raise BeginDayError(
            "published generation %r is not mirror-confirmed; Begin Day refuses "
            "to return an unconfirmed boot packet" % generation
        )
    coherence = _as_object(bundle.get("coherence"))
    if not coherence.get("coherent", False) or coherence.get("clock_day") != expected_day:
        raise BeginDayError(
            "the confirmed published generation no longer describes a coherent "
            "Day %r; refusing a mixed-generation boot packet" % expected_day
        )
    return bundle


def _abort_quietly(runtime, token):
    """Best-effort candidate abort that never masks the primary failure.

    The conductor is already handling a failure; whether the abort route or the
    rollback fallback discards the candidate, Day N published truth is
    unchanged. A secondary abort failure must not replace the original error.
    """
    try:
        runtime.abort_save(token)
    except Exception:  # noqa: BLE001 - the primary failure still propagates
        pass


# ---------------------------------------------------------------------------
# Optional DB-API adapter (production wiring of the RT01/RT02 gateway seam)
# ---------------------------------------------------------------------------


def _json_value(value):
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


class SqlDayBoundaryRuntime:
    """The production gateway seam over the existing RT01/RT02 SQL routes.

    It introduces no SQL of its own beyond calling the existing gateway and the
    POST-EV2-11 published read. Mirror confirmation remains owned by the existing
    runtime-published worker; ``ensure_confirmed`` only *checks* for agreement of
    the current published generation, so a pending mirror is never reported as
    success.

    Durable transaction boundary: under default (non-autocommit) DB-API
    behavior, ``begin_campaign_save`` / staging / ``publish_campaign_save`` all
    run inside one uncommitted client transaction, and a function-level success
    is not durable success. ``publish`` therefore commits the client transaction
    as soon as the gateway publication succeeds, so the published generation is
    durable before Begin Day can report it and the confirmation step can only
    observe that durable generation. The reported generation is taken from the
    gateway's own return value, computed inside the publishing transaction, so
    no later concurrent publication can be mistaken for this one. ``abort_save``
    commits the explicit gateway abort and falls back to rolling the client
    transaction back when it cannot be executed; either way the uncommitted
    candidate is durably discarded and Day N published truth is unchanged.
    """

    def __init__(self, connection, confirmation_worker=None):
        self._connection = connection
        self._confirmation_worker = confirmation_worker

    def read_published(self):
        with self._connection.cursor() as cur:
            cur.execute("select public.dm_begin_day_read()")
            return _json_value(cur.fetchone()[0])

    def begin_save(self, ttl_seconds=30):
        with self._connection.cursor() as cur:
            cur.execute("select * from public.begin_campaign_save(%s)", (ttl_seconds,))
            row = cur.fetchone()
        return row[2]  # lock_token

    def stage_state(self, token, key, value):
        with self._connection.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_state(%s, %s, %s::jsonb)",
                (token, key, json.dumps(value)),
            )

    def stage_clock(self, token, clock):
        with self._connection.cursor() as cur:
            cur.execute(
                "select public.stage_campaign_clock(%s, %s::jsonb)",
                (token, json.dumps(clock)),
            )

    def publish(self, token):
        with self._connection.cursor() as cur:
            cur.execute(
                "select (public.publish_campaign_save(%s)).published_generation",
                (token,),
            )
            row = cur.fetchone()
        published_generation = row[0] if row else None
        # A function-level success is only uncommitted client state under
        # default DB-API transaction behavior. Commit now: the publication
        # becomes durable before any success is reported, and the confirmation
        # step can only ever observe this durable generation.
        self._connection.commit()
        return published_generation

    def abort_save(self, token):
        try:
            with self._connection.cursor() as cur:
                cur.execute("select public.abort_campaign_save(%s)", (token,))
            self._connection.commit()
        except Exception:
            # The candidate never committed on this connection, so rolling the
            # client transaction back discards it and leaves Day N published
            # truth unchanged. Re-raise so the conductor's best-effort abort
            # keeps the primary failure visible.
            self._connection.rollback()
            raise

    def ensure_confirmed(self):
        if self._already_confirmed():
            return True
        if self._confirmation_worker is not None:
            self._confirmation_worker()
            # A worker sharing this connection under default DB-API transaction
            # behavior would otherwise leave its confirmation as uncommitted
            # client state. Commit it so the observed agreement is durable.
            self._connection.commit()
        return self._already_confirmed()

    def _already_confirmed(self):
        bundle = self.read_published()
        metadata = _as_object(bundle.get("runtime"))
        return bool(
            metadata.get("mirror_confirmed")
            and metadata.get("last_confirmed_generation") == metadata.get("generation")
        )


if __name__ == "__main__":  # pragma: no cover - library entry point
    print(
        json.dumps(
            {
                "module": "scripts.begin_day",
                "role": "POST-EV2-11 Begin Day conductor",
                "note": (
                    "Import open_next_day(...) with a gateway seam and a "
                    "finalized-day store. No CLI writes runtime state."
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    sys.exit(0)
