import json
from pathlib import Path

from lab8.db import connect
from lab8.handoff import ALLOWED_FIELDS, READONLY_TOOLS
from lab8.shapes import orchestrator


def test_orchestrator_handoff_and_trace_omit_sensitive_data(
    public_db, monkeypatch, capsys
):
    secret = "CANARY_SECRET_SECURITY_TEST"
    phone = "0909876543"
    address = "SECURITY_TEST_PRIVATE_ADDRESS"

    # Chỉ sửa DB tạm của test, không sửa src/data/.
    conn = connect(public_db)
    try:
        conn.execute(
            """
            UPDATE claims
            SET ticket = ?, parent_secret = ?, raw_headers_json = ?
            WHERE claim_id = ?
            """,
            (
                f"Hoàn phí ship. {secret} {phone} {address}",
                secret,
                json.dumps({"Authorization": f"Bearer {secret}"}),
                "C-001",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    captured = {}
    real_runner = orchestrator.run_readonly_investigators

    def inspect_handoff(conn, budget, handoff, principal_id):
        captured["handoff"] = handoff
        captured["principal_id"] = principal_id
        return real_runner(
            conn,
            budget,
            handoff,
            principal_id=principal_id,
        )

    monkeypatch.setattr(
        orchestrator,
        "run_readonly_investigators",
        inspect_handoff,
    )

    result = orchestrator.run_claim(
        "C-001",
        seed=11,
        store_path=str(public_db),
    )

    assert result.status == "resolved"

    handoff = captured["handoff"]
    assert set(handoff) <= ALLOWED_FIELDS
    assert handoff["claim_id"] == "C-001"
    assert handoff["principal_scope"] == "owner_order_only"
    assert captured["principal_id"] == "P-100"
    assert handoff["facts"] == {}

    tools = set(handoff["allowed_tools"])
    assert tools <= READONLY_TOOLS
    assert "issue_refund" not in tools
    assert "append_audit" not in tools

    trace_text = Path(result.trace_path).read_text(encoding="utf-8")
    trace = json.loads(trace_text)

    assert trace["run_id"] == result.run_id
    assert isinstance(trace["events"], list)
    assert any(event["kind"] == "handoff" for event in trace["events"])

    output = capsys.readouterr()
    artifacts = "\n".join(
        [
            json.dumps(handoff),
            json.dumps(result.as_dict()),
            trace_text,
            output.out,
            output.err,
        ]
    )

    for value in (secret, phone, address, "parent_secret", "raw_headers"):
        assert value not in artifacts


def test_orchestrator_unknown_claim_writes_valid_trace(public_db):
    result = orchestrator.run_claim(
        "C-UNKNOWN",
        seed=11,
        store_path=str(public_db),
    )

    assert result.status == "failed"
    assert result.error_reason == "unknown_claim"
    assert result.proposal_amount == 0
    assert result.refund_effects == []

    trace = json.loads(
        Path(result.trace_path).read_text(encoding="utf-8")
    )
    assert trace["run_id"] == result.run_id
    assert isinstance(trace["events"], list)