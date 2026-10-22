import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dice_resolver  # noqa: E402
from dice_resolver import main, parse_notation, resolve  # noqa: E402


class ScriptedRNG:
    """Explicit test-only RNG seam returning a fixed scripted sequence."""

    def __init__(self, values):
        self._values = list(values)

    def randint(self, low, high):
        value = self._values.pop(0)
        assert low <= value <= high, (low, high, value)
        return value


class NoCallRNG:
    """RNG seam that fails if a bounded-out request ever reaches RNG."""

    def randint(self, low, high):
        raise AssertionError("RNG must not be invoked for a bounded-out request")


def test_plain_notation_returns_values_in_bounds():
    for seed in range(50):
        result = resolve({"notation": "1d20"}, rng=random.Random(seed))
        assert result["dice_count"] == 1
        assert result["sides"] == 20
        assert len(result["rolls"]) == 1
        assert 1 <= result["rolls"][0] <= 20
        assert result["total"] == result["kept_rolls"][0]


def test_multiple_dice_expose_each_die_and_aggregate():
    result = resolve({"notation": "4d6"}, rng=random.Random(7))
    assert len(result["rolls"]) == 4
    assert all(1 <= roll <= 6 for roll in result["rolls"])
    assert result["kept_rolls"] == result["rolls"]
    assert result["dropped_rolls"] == []
    assert result["total"] == sum(result["rolls"])


def test_positive_and_negative_modifiers_require_source_and_calculate():
    result = resolve(
        {
            "notation": "1d20",
            "modifiers": [
                {"value": 3, "source": "proficiency"},
                {"value": -1, "source": "exhaustion"},
            ],
        },
        rng=ScriptedRNG([10]),
    )
    assert result["modifiers"] == [
        {"value": 3, "source": "proficiency"},
        {"value": -1, "source": "exhaustion"},
    ]
    assert result["modifier_total"] == 2
    assert result["total"] == 10 + 2


def test_bonus_and_penalty_dice_require_source_and_expose_components():
    result = resolve(
        {
            "notation": "1d20",
            "bonus_dice": [{"notation": "1d4", "source": "bless"}],
            "penalty_dice": [{"notation": "2d4", "source": "bane"}],
        },
        rng=ScriptedRNG([12, 3, 1, 2]),
    )
    assert result["rolls"] == [12]
    assert result["bonus_dice"] == [
        {"notation": "1d4", "source": "bless", "rolls": [3], "total": 3}
    ]
    assert result["penalty_dice"] == [
        {"notation": "2d4", "source": "bane", "rolls": [1, 2], "total": 3}
    ]
    assert result["bonus_total"] == 3
    assert result["penalty_total"] == 3
    assert result["total"] == 12 + 3 - 3


def test_advantage_rolls_two_d20_and_keeps_highest():
    result = resolve(
        {"notation": "1d20", "advantage": ["flanking"]},
        rng=ScriptedRNG([7, 15]),
    )
    assert result["mode"] == "advantage"
    assert result["rolls"] == [7, 15]
    assert result["kept_rolls"] == [15]
    assert result["dropped_rolls"] == [7]
    assert result["total"] == 15


def test_disadvantage_rolls_two_d20_and_keeps_lowest():
    result = resolve(
        {"notation": "1d20", "disadvantage": ["prone"]},
        rng=ScriptedRNG([18, 4]),
    )
    assert result["mode"] == "disadvantage"
    assert result["kept_rolls"] == [4]
    assert result["dropped_rolls"] == [18]
    assert result["total"] == 4


def test_advantage_and_disadvantage_cancel_to_one_normal_d20():
    result = resolve(
        {
            "notation": "1d20",
            "advantage": ["flanking"],
            "disadvantage": ["prone"],
        },
        rng=ScriptedRNG([11]),
    )
    assert result["mode"] == "normal"
    assert result["rolls"] == [11]
    assert result["kept_rolls"] == [11]
    assert result["dropped_rolls"] == []
    assert result["advantage_sources"] == ["flanking"]
    assert result["disadvantage_sources"] == ["prone"]


def test_duplicate_advantage_sources_do_not_stack():
    result = resolve(
        {"notation": "1d20", "advantage": ["flanking", "inspiration", "luck"]},
        rng=ScriptedRNG([3, 19]),
    )
    assert result["rolls"] == [3, 19]
    assert len(result["rolls"]) == 2
    assert result["kept_rolls"] == [19]


@pytest.mark.parametrize(
    "payload",
    [
        {"notation": "1d20", "modifiers": [{"value": 2, "source": ""}]},
        {"notation": "1d20", "modifiers": [{"value": 2, "source": "   "}]},
        {"notation": "1d20", "modifiers": [{"value": 2}]},
        {"notation": "1d20", "modifiers": [{"source": "blessing"}]},
        {"notation": "1d20", "bonus_dice": [{"notation": "1d4"}]},
        {"notation": "1d20", "penalty_dice": [{"notation": "1d4", "source": ""}]},
        {"notation": "1d20", "advantage": [""]},
        {"notation": "1d20", "disadvantage": [None]},
    ],
)
def test_missing_or_empty_sources_fail_closed(payload):
    with pytest.raises(ValueError):
        resolve(payload, rng=random.Random(0))


@pytest.mark.parametrize(
    "payload",
    [
        {"notation": "d20"},
        {"notation": "1d"},
        {"notation": "1d20x"},
        {"notation": "0d20"},
        {"notation": "1d1"},
        {"notation": "1d20", "modifiers": [{"value": "3", "source": "x"}]},
        {"notation": "1d20", "modifiers": [{"value": 1.5, "source": "x"}]},
        {"notation": "1d20", "advantage": "flanking"},
        {"notation": "2d6", "advantage": ["flanking"]},
        {"notation": "1d12", "disadvantage": ["prone"]},
        {},
        ["1d20"],
        {"notation": "1d20", "modifiers": {}},
        {"notation": "1d20", "surprise": 1},
    ],
)
def test_invalid_requests_fail_cleanly(payload):
    with pytest.raises(ValueError):
        resolve(payload, rng=random.Random(0))


@pytest.mark.parametrize(
    "payload",
    [
        {"notation": True},
        {"notation": "1d20", "modifiers": [{"value": True, "source": "x"}]},
        {"notation": "1d20", "modifiers": [{"value": False, "source": "x"}]},
        {"notation": "1d20", "bonus_dice": [{"notation": True, "source": "x"}]},
    ],
)
def test_booleans_are_not_accepted_as_integers(payload):
    with pytest.raises(ValueError):
        resolve(payload, rng=random.Random(0))


def test_parse_notation_is_strict():
    assert parse_notation("2d6") == (2, 6)
    assert parse_notation("1D20") == (1, 20)


def test_oversized_base_expression_fails_closed_before_rolling():
    oversized = f"{dice_resolver.MAX_DICE_PER_REQUEST + 1}d6"
    with pytest.raises(ValueError):
        resolve({"notation": oversized}, rng=NoCallRNG())


def test_oversized_aggregate_dice_fails_closed_before_rolling():
    cap = dice_resolver.MAX_DICE_PER_REQUEST
    payload = {
        "notation": "1d20",
        "bonus_dice": [{"notation": f"{cap}d4", "source": "bless"}],
        "penalty_dice": [{"notation": "1d4", "source": "bane"}],
    }
    with pytest.raises(ValueError):
        resolve(payload, rng=NoCallRNG())


def test_dice_budget_at_limit_is_accepted():
    cap = dice_resolver.MAX_DICE_PER_REQUEST
    result = resolve({"notation": f"{cap}d6"}, rng=random.Random(0))
    assert len(result["rolls"]) == cap
    assert result["total"] == sum(result["rolls"])


def test_production_default_uses_runtime_rng_module(monkeypatch):
    stub = ScriptedRNG([9])
    monkeypatch.setattr(dice_resolver, "random", stub)
    result = resolve({"notation": "1d20"})
    assert result["rolls"] == [9]


def test_explicit_seed_seam_is_deterministic():
    first = resolve({"notation": "3d8"}, rng=random.Random(1234))
    second = resolve({"notation": "3d8"}, rng=random.Random(1234))
    assert first == second


def test_resolve_does_not_mutate_request():
    request = {
        "notation": "1d20",
        "modifiers": [{"value": 2, "source": "proficiency"}],
        "advantage": ["flanking"],
    }
    snapshot = json.dumps(request, sort_keys=True)
    resolve(request, rng=random.Random(0))
    assert json.dumps(request, sort_keys=True) == snapshot


def test_cli_and_api_share_the_same_contract(tmp_path, capsys):
    request = {"notation": "2d6", "modifiers": [{"value": 1, "source": "blessing"}]}
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    expected = resolve(request, rng=random.Random(42))

    code = main([str(request_path)])
    assert code == 0
    emitted = json.loads(capsys.readouterr().out)
    assert set(emitted) == set(expected)


def test_cli_invalid_request_exits_nonzero(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"notation": "nope"}), encoding="utf-8")
    code = main([str(request_path)])
    assert code == 2
    assert "error" in capsys.readouterr().err
