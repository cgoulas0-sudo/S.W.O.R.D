"""RT01-C regression proof for precision-preserving JSONB candidate intake."""

from decimal import Decimal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from runtime_published_mirror import _canonical_bytes, _load_pending_from_db  # noqa: E402

VALUE = "0.12345678901234567890123456789"


def test_pending_jsonb_fraction_keeps_exact_precision_in_git_artifact(db):
    with db.cursor() as cur:
        cur.execute("select lock_token from public.begin_campaign_save(30)")
        token = cur.fetchone()[0]
        cur.execute(
            "select public.stage_campaign_state(%s, %s, %s::jsonb)",
            (token, "wallet", f'{{"amount":{VALUE}}}'),
        )
        cur.execute("select public.publish_campaign_save(%s)", (token,))

    candidate = _load_pending_from_db(db)
    amount = candidate["state"]["wallet"]["amount"]

    assert isinstance(amount, Decimal)
    assert amount == Decimal(VALUE)
    artifact = _canonical_bytes(candidate)
    assert VALUE.encode("ascii") in artifact
