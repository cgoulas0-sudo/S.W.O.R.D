#!/usr/bin/env python3
"""BTH-01 deterministic player/DM context access projection.

One reusable, transport-neutral, request-time decision seam. A caller supplies
a trusted principal plus an explicitly classified semantic request and receives
exactly one deterministic outcome:

    ALLOW | BLOCK | SPOILER_CONFIRM

The seam never authenticates an account, never reads natural-language prompt
content to infer identity or permission, never mutates campaign truth, and
never returns or forwards protected payload unless the outcome is ALLOW. It is
designed to compose with Campaign Control Center's trusted Clerk/AccessContext
principal layer rather than duplicating authentication or role assignment.
"""

from __future__ import annotations

import re

ALLOW = "ALLOW"
BLOCK = "BLOCK"
SPOILER_CONFIRM = "SPOILER_CONFIRM"

OUTCOMES = (ALLOW, BLOCK, SPOILER_CONFIRM)

DM_ROLE = "dm"
PLAYER_ROLE = "player"
ROLES = (DM_ROLE, PLAYER_ROLE)

REQUEST_CHARACTER_CONTEXT = "character_context"
REQUEST_OWNER_KNOWLEDGE = "owner_knowledge"
REQUEST_BTH_ENTRY = "bth_entry"
REQUEST_DM_CONTEXT = "dm_context"

SUPPORTED_REQUEST_KINDS = (
    REQUEST_CHARACTER_CONTEXT,
    REQUEST_OWNER_KNOWLEDGE,
    REQUEST_BTH_ENTRY,
    REQUEST_DM_CONTEXT,
)

_ENTITY_PREFIXES = (
    "character",
    "location",
    "faction",
    "party",
    "creature",
    "item",
)
_ENTITY_ID_RE = re.compile(
    r"^(?:" + "|".join(_ENTITY_PREFIXES) + r"):[a-z0-9]+(?:-[a-z0-9]+)*\Z"
)
_CONTROLLED_ENTITY_RE = re.compile(r"^character:[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def _resolve_principal(principal):
    """Validate the trusted principal shape; never authenticate the account."""
    if not isinstance(principal, dict):
        return None, "malformed_principal"
    role = principal.get("role")
    if role == DM_ROLE:
        return {"role": DM_ROLE}, None
    if role == PLAYER_ROLE:
        controlled = principal.get("controlled_entity")
        if not isinstance(controlled, str) or not _CONTROLLED_ENTITY_RE.match(
            controlled
        ):
            return None, "malformed_controlled_entity"
        return {"role": PLAYER_ROLE, "controlled_entity": controlled}, None
    return None, "unknown_role"


def _resolve_kind(request):
    if not isinstance(request, dict):
        return None, "malformed_request"
    kind = request.get("kind")
    if kind not in SUPPORTED_REQUEST_KINDS:
        return None, "unsupported_request_kind"
    return kind, None


def _resolve_owner(request):
    owner = request.get("owner")
    if not isinstance(owner, str) or not owner.strip():
        return None, "missing_owner"
    if not _ENTITY_ID_RE.match(owner):
        return None, "malformed_owner"
    return owner, None


def _validate_kind_fields(request, kind):
    """Validate the fields a selected request kind requires.

    Runs for every principal, including DM, so a malformed request shape fails
    closed before any role authority is applied. DM authority covers which
    contexts are visible, never whether the request itself is well-formed.
    """
    if kind == REQUEST_BTH_ENTRY:
        acknowledged = request.get("acknowledged", False)
        if not isinstance(acknowledged, bool):
            return "malformed_acknowledgement"
        return None
    if kind in (REQUEST_CHARACTER_CONTEXT, REQUEST_OWNER_KNOWLEDGE):
        _, error = _resolve_owner(request)
        return error
    return None


def _evaluate_player(controlled, request, kind):
    if kind == REQUEST_DM_CONTEXT:
        return BLOCK, "player_denied_dm_context"

    if kind == REQUEST_BTH_ENTRY:
        acknowledged = request.get("acknowledged", False)
        if not isinstance(acknowledged, bool):
            return BLOCK, "malformed_acknowledgement"
        if acknowledged:
            return ALLOW, "bth_acknowledged"
        return SPOILER_CONFIRM, "bth_spoiler_acknowledgement_required"

    owner, error = _resolve_owner(request)
    if error is not None:
        return BLOCK, error
    if owner != controlled:
        if kind == REQUEST_CHARACTER_CONTEXT:
            return BLOCK, "owner_not_controlled_character"
        return BLOCK, "other_owner_private_knowledge"
    if kind == REQUEST_CHARACTER_CONTEXT:
        return ALLOW, "own_character_context"
    return ALLOW, "own_owner_knowledge"


def evaluate(principal, request):
    """Return exactly one ``(outcome, reason)`` for principal + request."""
    resolved, error = _resolve_principal(principal)
    if error is not None:
        return BLOCK, error

    kind, error = _resolve_kind(request)
    if error is not None:
        return BLOCK, error

    error = _validate_kind_fields(request, kind)
    if error is not None:
        return BLOCK, error

    if resolved["role"] == DM_ROLE:
        return ALLOW, "dm_authority"

    return _evaluate_player(resolved["controlled_entity"], request, kind)


def resolve_access(principal, request, payload=None):
    """Return the deterministic decision, forwarding payload only on ALLOW.

    Extra request keys (for example a natural-language ``query``) are ignored
    for authorization; the decision depends solely on the trusted principal and
    the declared request kind.
    """
    outcome, reason = evaluate(principal, request)
    admitted = payload if outcome == ALLOW else None
    return {"outcome": outcome, "reason": reason, "payload": admitted}
