import io
import json
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import reputation_resolver  # noqa: E402
from reputation_resolver import (  # noqa: E402
    resolve_reputation,
    validate_config,
)

TEMPLATE_PATH = ROOT / "config" / "REPUTATION_TEMPLATE.json"

DEFAULT_CONFIG = {
    "schema_version": 1,
    "status": "template_inert_until_explicitly_instantiated",
    "score_bounds": {"min": 0, "max": 100},
    "consequence_scale": {
        "minor": 1,
        "meaningful": 2,
        "major": 5,
        "city_defining": 10,
    },
    "high_standing": {
        "threshold": 80,
        "positive_gain_multiplier": 0.5,
        "rounding": "floor",
    },
    "tiers": [
        {"name": "wary", "min": 0, "max": 29},
        {"name": "neutral", "min": 30, "max": 59},
        {"name": "recognized", "min": 60, "max": 79},
        {"name": "institutional", "min": 80, "max": 94},
        {"name": "key_civic_link", "min": 95, "max": 99},
        {"name": "legendary", "min": 100, "max": 100},
    ],
}


def cfg(**overrides):
    base = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in overrides.items():
        base[key] = value
    return base


# --- Proof 1: every configured consequence class resolves its exact signed delta


@pytest.mark.parametrize(
    "cls,direction,current,expected_delta,expected_score",
    [
        ("minor", "positive", 50, 1, 51),
        ("meaningful", "positive", 50, 2, 52),
        ("major", "positive", 50, 5, 55),
        ("city_defining", "positive", 50, 10, 60),
        ("minor", "negative", 50, -1, 49),
        ("meaningful", "negative", 50, -2, 48),
        ("major", "negative", 50, -5, 45),
        ("city_defining", "negative", 50, -10, 40),
    ],
)
def test_consequence_classes_exact_delta(
    cls, direction, current, expected_delta, expected_score
):
    result = resolve_reputation(
        {"current_score": current, "consequence_class": cls, "direction": direction},
        DEFAULT_CONFIG,
    )
    assert result["applied_delta"] == expected_delta
    assert result["resulting_score"] == expected_score
    assert result["high_standing_asymmetry_applied"] is False


# --- Proof 2: 0/100 bounds clamp correctly


def test_lower_bound_clamps():
    result = resolve_reputation(
        {"current_score": 0, "consequence_class": "major", "direction": "negative"},
        DEFAULT_CONFIG,
    )
    assert result["resulting_score"] == 0
    assert result["applied_delta"] == -5
    assert result["bounded"] is True


def test_upper_bound_clamps():
    result = resolve_reputation(
        {"current_score": 100, "consequence_class": "major", "direction": "positive"},
        DEFAULT_CONFIG,
    )
    assert result["resulting_score"] == 100
    assert result["bounded"] is True


# --- Proof 3: positive above-80 asymmetry + floor behavior


@pytest.mark.parametrize(
    "current,cls,expected_applied,expected_score",
    [
        (85, "minor", 0, 85),  # floor(1 * 0.5) == 0
        (85, "meaningful", 1, 86),  # floor(2 * 0.5) == 1
        (85, "major", 2, 87),  # floor(5 * 0.5) == 2
        (85, "city_defining", 5, 90),  # floor(10 * 0.5) == 5
        (81, "meaningful", 1, 82),
    ],
)
def test_positive_high_standing_asymmetry(current, cls, expected_applied, expected_score):
    result = resolve_reputation(
        {"current_score": current, "consequence_class": cls, "direction": "positive"},
        DEFAULT_CONFIG,
    )
    assert result["high_standing_asymmetry_applied"] is True
    assert result["applied_delta"] == expected_applied
    assert result["resulting_score"] == expected_score


def test_threshold_boundary_is_not_above_threshold():
    # current == threshold (80) is NOT "above 80", so no asymmetry applies.
    result = resolve_reputation(
        {"current_score": 80, "consequence_class": "minor", "direction": "positive"},
        DEFAULT_CONFIG,
    )
    assert result["high_standing_asymmetry_applied"] is False
    assert result["applied_delta"] == 1
    assert result["resulting_score"] == 81


# --- Proof 4: negative changes are not reduced by positive asymmetry


def test_negative_change_ignores_asymmetry():
    result = resolve_reputation(
        {"current_score": 90, "consequence_class": "major", "direction": "negative"},
        DEFAULT_CONFIG,
    )
    assert result["high_standing_asymmetry_applied"] is False
    assert result["applied_delta"] == -5
    assert result["resulting_score"] == 85


# --- Proof 3b: positive-gain floor arithmetic is decimal-safe / exact
#
# A configured multiplier parsed as a binary float can sit just below the
# mathematically exact product (100 * 0.29 == 28.999999999999996), so flooring
# the float product would silently lose a whole Reputation point.


def test_decimal_safe_floor_known_scar_case():
    config = cfg(
        consequence_scale={"huge": 100},
        high_standing={
            "threshold": 80,
            "positive_gain_multiplier": 0.29,
            "rounding": "floor",
        },
    )
    result = resolve_reputation(
        {"current_score": 81, "consequence_class": "huge", "direction": "positive"},
        config,
    )
    assert result["high_standing_asymmetry_applied"] is True
    assert result["applied_delta"] == 29


@pytest.mark.parametrize(
    "magnitude,multiplier,expected_applied",
    [
        (100, 0.29, 29),  # float product is 28.999999999999996
        (100, 0.5, 50),
        (7, 0.29, 2),  # float product is 2.0299999999999998
        (5, 0.29, 1),  # float product is 1.45 exactly; floor 1
        (3, 0.29, 0),  # float product is 0.8699999999999999; floor 0
    ],
)
def test_decimal_safe_floor_multiplier_cases(magnitude, multiplier, expected_applied):
    config = cfg(
        consequence_scale={"probe": magnitude},
        high_standing={
            "threshold": 80,
            "positive_gain_multiplier": multiplier,
            "rounding": "floor",
        },
    )
    result = resolve_reputation(
        {"current_score": 81, "consequence_class": "probe", "direction": "positive"},
        config,
    )
    assert result["high_standing_asymmetry_applied"] is True
    assert result["applied_delta"] == expected_applied


# The default Decimal context precision is 28 significant digits. A valid
# configured magnitude whose exact product is wider than that must still floor
# correctly instead of being rounded by the ambient context and silently
# gaining or losing whole Reputation points.


@pytest.mark.parametrize(
    "magnitude,multiplier,expected_applied",
    [
        # 123456789012345678901234567890 * 0.29 == ...24768.10, floor ...24768.
        (123456789012345678901234567890, 0.29, 35802468813580246881358024688),
        # 10**30 + 7, product ...00000.49, floor ...00000.
        (1000000000000000000000000000007, 0.07, 70000000000000000000000000000),
        # 32 nines * 0.5 == ...999.5, floor ...999.
        (99999999999999999999999999999999, 0.5, 99999999999999999999999999999999 // 2),
        # 10**40 * 0.29 == 2.9e39 exactly.
        (10**40, 0.29, 29 * 10**38),
    ],
)
def test_decimal_safe_floor_large_magnitude(
    magnitude, multiplier, expected_applied
):
    config = cfg(
        consequence_scale={"colossal": magnitude},
        high_standing={
            "threshold": 80,
            "positive_gain_multiplier": multiplier,
            "rounding": "floor",
        },
    )
    result = resolve_reputation(
        {"current_score": 81, "consequence_class": "colossal", "direction": "positive"},
        config,
    )
    assert result["high_standing_asymmetry_applied"] is True
    assert result["applied_delta"] == expected_applied


# A high-precision multiplier literal must be preserved exactly at JSON parse
# time. Parsing it as a binary float first loses digits, and recovering it with
# ``Decimal(str(float))`` only yields the float's shortest round-tripping
# representation rather than the configured literal, so a valid large magnitude
# would floor to the wrong whole point.

HIGH_PRECISION_MULTIPLIER = "0.12345678901234567890123456789"


def test_config_loader_preserves_high_precision_multiplier_literal(tmp_path):
    magnitude = 10**20
    payload = {
        "score_bounds": {"min": 0, "max": 100},
        "consequence_scale": {"colossal": magnitude},
        "high_standing": {
            "threshold": 80,
            "positive_gain_multiplier": "MULTIPLIER_PLACEHOLDER",
            "rounding": "floor",
        },
        "tiers": DEFAULT_CONFIG["tiers"],
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(payload).replace('"MULTIPLIER_PLACEHOLDER"', HIGH_PRECISION_MULTIPLIER),
        encoding="utf-8",
    )

    loaded = reputation_resolver.load_config(str(config_path))
    assert isinstance(loaded["high_standing"]["positive_gain_multiplier"], Decimal)

    # floor(10**20 * 0.12345678901234567890123456789) == 12345678901234567890.
    # The binary-float path would floor to ...568000, losing 110 whole points.
    result = resolve_reputation(
        {"current_score": 81, "consequence_class": "colossal", "direction": "positive"},
        loaded,
    )
    assert result["high_standing_asymmetry_applied"] is True
    assert result["applied_delta"] == 12345678901234567890


# --- Proof 5: every boundary score derives exactly one correct tier
#
# The resolver derives the tier from the *resulting* score, so each case picks a
# request whose resulting score is exactly the boundary under test.


def _request_for_score(score):
    if score == 0:
        return {"current_score": 0, "consequence_class": "major", "direction": "negative"}
    if score == 100:
        return {"current_score": 100, "consequence_class": "major", "direction": "positive"}
    return {"current_score": score + 1, "consequence_class": "minor", "direction": "negative"}


@pytest.mark.parametrize(
    "score,expected_tier",
    [
        (0, "wary"),
        (29, "wary"),
        (30, "neutral"),
        (59, "neutral"),
        (60, "recognized"),
        (79, "recognized"),
        (80, "institutional"),
        (94, "institutional"),
        (95, "key_civic_link"),
        (99, "key_civic_link"),
        (100, "legendary"),
    ],
)
def test_boundary_scores_exact_tier(score, expected_tier):
    result = resolve_reputation(_request_for_score(score), DEFAULT_CONFIG)
    assert result["resulting_score"] == score
    assert result["tier"] == expected_tier


# --- Proof 6: malformed / out-of-range current score fails closed


@pytest.mark.parametrize(
    "current",
    [None, -1, 101, 50.5, "50", True, [], {}],
)
def test_malformed_current_score_fails_closed(current):
    with pytest.raises(ValueError):
        resolve_reputation(
            {
                "current_score": current,
                "consequence_class": "minor",
                "direction": "positive",
            },
            DEFAULT_CONFIG,
        )


def test_missing_current_score_fails_closed():
    with pytest.raises(ValueError):
        resolve_reputation(
            {"consequence_class": "minor", "direction": "positive"}, DEFAULT_CONFIG
        )


# --- Proof 7: unknown consequence class fails closed


def test_unknown_consequence_class_fails_closed():
    with pytest.raises(ValueError):
        resolve_reputation(
            {
                "current_score": 50,
                "consequence_class": "catastrophic",
                "direction": "positive",
            },
            DEFAULT_CONFIG,
        )


def test_missing_consequence_class_fails_closed():
    with pytest.raises(ValueError):
        resolve_reputation(
            {"current_score": 50, "direction": "positive"}, DEFAULT_CONFIG
        )


@pytest.mark.parametrize("direction", ["up", "down", "", None, 1, "positivex"])
def test_invalid_direction_fails_closed(direction):
    with pytest.raises(ValueError):
        resolve_reputation(
            {
                "current_score": 50,
                "consequence_class": "minor",
                "direction": direction,
            },
            DEFAULT_CONFIG,
        )


def test_unknown_request_field_fails_closed():
    with pytest.raises(ValueError):
        resolve_reputation(
            {
                "current_score": 50,
                "consequence_class": "minor",
                "direction": "positive",
                "desired_score": 99,
            },
            DEFAULT_CONFIG,
        )


# --- Proof 8: malformed config fails closed


def test_bad_bounds_fail_closed():
    with pytest.raises(ValueError):
        validate_config(cfg(score_bounds={"min": 100, "max": 0}))
    with pytest.raises(ValueError):
        validate_config(cfg(score_bounds={"min": 50, "max": 50}))


def test_tier_gap_fails_closed():
    broken = json.loads(json.dumps(DEFAULT_CONFIG))
    broken["tiers"][0]["max"] = 28  # leaves 29 uncovered
    with pytest.raises(ValueError):
        validate_config(broken)


def test_tier_overlap_fails_closed():
    broken = json.loads(json.dumps(DEFAULT_CONFIG))
    broken["tiers"][1]["min"] = 29  # overlaps 0-29
    with pytest.raises(ValueError):
        validate_config(broken)


def test_tier_must_cover_full_range():
    broken = json.loads(json.dumps(DEFAULT_CONFIG))
    broken["tiers"].pop()  # drops legendary 100
    with pytest.raises(ValueError):
        validate_config(broken)


def test_invalid_multiplier_fails_closed():
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": 80, "positive_gain_multiplier": 1.0, "rounding": "floor"}))
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": 80, "positive_gain_multiplier": 0, "rounding": "floor"}))
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": 80, "positive_gain_multiplier": 1.5, "rounding": "floor"}))


def test_invalid_rounding_fails_closed():
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": 80, "positive_gain_multiplier": 0.5, "rounding": "ceil"}))


def test_threshold_out_of_bounds_fails_closed():
    # threshold must satisfy min < threshold <= max, so threshold at/below min fails.
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": 0, "positive_gain_multiplier": 0.5, "rounding": "floor"}))
    with pytest.raises(ValueError):
        validate_config(cfg(high_standing={"threshold": -5, "positive_gain_multiplier": 0.5, "rounding": "floor"}))


def test_empty_consequence_scale_fails_closed():
    broken = json.loads(json.dumps(DEFAULT_CONFIG))
    broken["consequence_scale"] = {}
    with pytest.raises(ValueError):
        validate_config(broken)


# --- Proof 9: caller / config inputs are not mutated


def test_inputs_not_mutated():
    request = {
        "current_score": 50,
        "consequence_class": "major",
        "direction": "positive",
    }
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    request_snapshot = json.dumps(request, sort_keys=True)
    config_snapshot = json.dumps(config, sort_keys=True)

    resolve_reputation(request, config)

    assert json.dumps(request, sort_keys=True) == request_snapshot
    assert json.dumps(config, sort_keys=True) == config_snapshot


# --- Proof 10: no RNG required or invoked; resolution is deterministic


def test_resolution_requires_no_rng_and_is_deterministic():
    request = {
        "current_score": 85,
        "consequence_class": "major",
        "direction": "positive",
    }
    first = resolve_reputation(request, DEFAULT_CONFIG)
    second = resolve_reputation(request, DEFAULT_CONFIG)
    assert first == second


# --- Proof 11: fixtures remain generic / template-portable


def test_template_file_is_valid_and_matches_reference():
    assert TEMPLATE_PATH.is_file()
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    # The shipped template validates and exposes the reference semantics.
    validated = validate_config(template)
    assert validated["min"] == 0
    assert validated["max"] == 100
    assert validated["scale"] == DEFAULT_CONFIG["consequence_scale"]
    assert validated["multiplier"] == 0.5
    # Resolving against the real template works.
    result = resolve_reputation(
        {"current_score": 50, "consequence_class": "major", "direction": "positive"},
        template,
    )
    assert result["resulting_score"] == 55
    assert result["tier"] == "neutral"


# --- Proof 12: association semantics documented, never persisted/duplicated


def test_result_contains_only_mechanical_fields():
    result = resolve_reputation(
        {"current_score": 50, "consequence_class": "major", "direction": "positive"},
        DEFAULT_CONFIG,
    )
    assert set(result) == {
        "current_score",
        "consequence_class",
        "direction",
        "magnitude",
        "high_standing_asymmetry_applied",
        "applied_delta",
        "resulting_score",
        "tier",
        "bounded",
    }
    # No person / association / persistence surface is produced.
    assert not any("person" in key or "association" in key for key in result)


# --- Proof: CLI and API share the same contract


def test_cli_and_api_share_contract(tmp_path, capsys):
    request = {
        "current_score": 85,
        "consequence_class": "major",
        "direction": "positive",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    expected = resolve_reputation(request, DEFAULT_CONFIG)

    code = reputation_resolver.main(
        [str(request_path), "--config", str(TEMPLATE_PATH)]
    )
    assert code == 0
    emitted = json.loads(capsys.readouterr().out)
    assert emitted["resulting_score"] == expected["resulting_score"]
    assert emitted["tier"] == expected["tier"]
    assert emitted["applied_delta"] == expected["applied_delta"]


def test_cli_invalid_request_exits_nonzero(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps({"current_score": 999}), encoding="utf-8")
    code = reputation_resolver.main(
        [str(request_path), "--config", str(TEMPLATE_PATH)]
    )
    assert code == 2
    assert "error" in capsys.readouterr().err


# --- Proof 14: request-file/stdin load + parse failures use the CLI fail-closed path


def test_cli_missing_request_file_fails_closed(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.json"
    code = reputation_resolver.main([str(missing), "--config", str(TEMPLATE_PATH)])
    assert code == 2
    assert "error" in capsys.readouterr().err


def test_cli_malformed_request_file_fails_closed(tmp_path, capsys):
    request_path = tmp_path / "request.json"
    request_path.write_text("{not valid json", encoding="utf-8")
    code = reputation_resolver.main(
        [str(request_path), "--config", str(TEMPLATE_PATH)]
    )
    assert code == 2
    assert "error" in capsys.readouterr().err


def test_cli_malformed_stdin_fails_closed(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not valid json"))
    code = reputation_resolver.main(["--config", str(TEMPLATE_PATH)])
    assert code == 2
    assert "error" in capsys.readouterr().err
