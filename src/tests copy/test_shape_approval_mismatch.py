import pytest

from lab8.app import prepare_store
from lab8.db import connect
from lab8.shapes import SHAPES


@pytest.mark.parametrize("shape", ["workflow", "single", "orchestrator"])
def test_wrong_claim_approval_is_denied(shape, tmp_path):
    store = tmp_path / f"{shape}.sqlite"
    prepare_store(store)

    conn = connect(store)
    conn.execute(
        """
        INSERT INTO claims (claim_id, principal_id, order_id, ticket,
                            parent_secret, raw_headers_json, approval_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "C-BORROW",
            "P-100",
            "O-107",
            "test",
            "CANARY_SECRET_PARENT_TEST",
            "{}",
            "A-001",
        ),
    )
    conn.commit()
    conn.close()

    result = SHAPES[shape](
        "C-BORROW",
        seed=11,
        store_path=str(store),
    )

    conn = connect(store)
    try:
        refund_count = conn.execute(
            "SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = ?",
            ("C-BORROW",),
        ).fetchone()["n"]

        denials = conn.execute(
            """
            SELECT details_json FROM audit_events
            WHERE claim_id = ? AND event_type = 'policy_denied'
            """,
            ("C-BORROW",),
        ).fetchall()
    finally:
        conn.close()

    assert result.status == "denied"
    assert refund_count == 0
    assert denials
    assert any("approval_claim_mismatch" in row["details_json"] for row in denials)