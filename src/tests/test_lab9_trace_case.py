"""M1 regression case: a ticket must not override authoritative DB delay days."""
import pytest


pytestmark = pytest.mark.student


@pytest.mark.parametrize(
    "shape,seed,db_fact_kept,refund_vnd",
    [("seeded_regression", 11, False, 20000),
     ("swarm", 55, False, 20000),
     ("fixed", 11, True, 0)],
)
def test_lab9_trace_case_ticket_db_conflict(shape, seed, db_fact_kept, refund_vnd):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import DbFactKept
    from lab9.trace_case import investigate

    case = investigate(shape, "C-002", seed)
    trial = case["trial"]
    ctx = EvaluatorContext(
        name=f"{shape}:C-002@{seed}", inputs={"claim_id": "C-002", "seed": seed},
        metadata=None, expected_output=case["label"], output=trial,
        duration=0.0, _span_tree=None, attributes={}, metrics={},
    )
    assert DbFactKept().evaluate(ctx).value is db_fact_kept
    assert trial["lab8_pass"] is db_fact_kept
    assert trial["snapshot"]["refund_vnd"] == refund_vnd
    assert trial["events"][1]["payload"]["lookup_order"]["order"]["delay_days"] == 2
    if db_fact_kept:
        assert trial["result"]["status"] == "denied"
        assert trial["result"]["proposal_amount"] == 0
    else:
        assert trial["events"][2] == {"kind": "model_override", "payload": {"delay_days": 5}}
        assert trial["result"]["status"] == "resolved"
