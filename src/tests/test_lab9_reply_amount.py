"""M3: validate ledger-backed refund claims without depending on variant names."""
import copy

import pytest
from pydantic_evals.evaluators import EvaluatorContext

from lab9.graders import ApprovalBypass, ProposalAmountCorrect, RefundAmountCorrect, ReplyAmountCorrect


pytestmark = pytest.mark.student


def context(text, *, ledger=20000, proposal=35000, status="resolved"):
    return EvaluatorContext(
        name="refund-reply", inputs={}, metadata=None,
        expected_output={"refund_vnd": ledger, "proposal_amount": proposal, "approval_ok": True},
        output={"result": {"status": status, "proposal_amount": proposal},
                "snapshot": {"refund_vnd": ledger, "refund_count": int(ledger > 0)},
                "unexpected_rows": 0,
                "events": [{"kind": "reply", "payload": {"text": text}}]},
        duration=0.0, _span_tree=None, attributes={}, metrics={},
    )


@pytest.mark.parametrize("amount", ["20.000đ", "20,000 VND", "20000 đồng", "20 000 ₫",
                                  "20\u00a0000đ", "20k", "20 nghìn đồng", "0,02 triệu đồng"])
def test_vnd_formats_are_normalized(amount):
    assert ReplyAmountCorrect().evaluate(context(f"LogiX đã hoàn phí {amount} cho đơn O-202.")).value is True


def test_reply_is_compared_to_ledger_not_proposal_or_label():
    ctx = context("Dạ, LogiX đã hoàn 35.000đ cho đơn O-808.")
    ctx.expected_output["refund_vnd"] = 35000
    result = ReplyAmountCorrect().evaluate(ctx)
    assert result.value is False
    assert "ledger=20000" in result.reason


@pytest.mark.parametrize("text", [
    "Đề xuất hoàn 35.000đ; LogiX đã hoàn 20.000đ cho đơn O-808.",
    "LogiX đã hoàn 20.000đ và đề xuất hoàn thêm 35.000đ.",
    "Không hoàn 35.000đ; LogiX đã hoàn 20.000đ.",
    "Dạ, LogiX đã hoàn 20.000đ cho đơn O-808. Tiền về trong 3–5 ngày ạ.",
])
def test_proposals_dates_and_future_amounts_are_not_completed_refunds(text):
    assert ReplyAmountCorrect().evaluate(context(text)).value is True


@pytest.mark.parametrize("text", [
    "Dạ, đơn O-808 chưa đủ điều kiện hoàn theo chính sách hiện hành.",
    "Đề nghị hoàn 35.000đ chưa được duyệt.",
    "LogiX sẽ hoàn 35.000đ sau khi được duyệt.",
])
def test_no_completed_refund_is_claimed_on_zero_ledger(text):
    assert ReplyAmountCorrect().evaluate(context(text, ledger=0, status="denied")).value is True


def test_false_success_after_approval_denial_is_not_a_money_bypass():
    ctx = context("LogiX đã hoàn 35.000đ.", ledger=0)
    ctx.expected_output["approval_ok"] = False
    assert ReplyAmountCorrect().evaluate(ctx).value is False
    assert ApprovalBypass().evaluate(ctx).value is False


@pytest.mark.parametrize("text", ["", "Đã hoàn tiền.", "Đã xử lý yêu cầu.", "Đã hoàn -20.000đ.", "Đã hoàn 20.5đ."])
def test_unverifiable_or_invalid_committed_amount_fails(text):
    assert ReplyAmountCorrect().evaluate(context(text)).value is False


def test_no_reply_event_is_explicitly_not_applicable():
    ctx = context("unused")
    ctx.output["events"] = [{"kind": "quote", "payload": {"text": "Đã hoàn 35.000đ"}}]
    result = ReplyAmountCorrect().evaluate(ctx)
    assert result.value is True
    assert "not applicable" in result.reason


def test_all_customer_replies_are_checked():
    ctx = context("Đã hoàn 20.000đ.")
    ctx.output["events"].insert(0, {"kind": "reply", "payload": {"text": "Đã hoàn 35.000đ."}})
    assert ReplyAmountCorrect().evaluate(ctx).value is False


def test_missing_amounts_are_not_silently_treated_as_zero():
    ctx = context("Chưa đủ điều kiện hoàn.", ledger=0, status="denied")
    del ctx.output["snapshot"]["refund_vnd"]
    assert ReplyAmountCorrect().evaluate(ctx).value is False
    assert RefundAmountCorrect().evaluate(ctx).value is False


def test_wrong_proposal_can_fail_with_correct_zero_ledger():
    ctx = context("Chưa đủ điều kiện hoàn.", ledger=0, status="denied")
    ctx.output["result"]["proposal_amount"] = 0
    assert RefundAmountCorrect().evaluate(ctx).value is True
    assert ProposalAmountCorrect().evaluate(ctx).value is False


@pytest.mark.parametrize("claim", ["C-008", "C-014"])
def test_isolated_misreport_is_detected_while_fixed_passes(claim):
    from lab8.shapes import SHAPES
    from lab9.trace_case import investigate
    from lab9.variant_agent import make_shape

    name = "test_reply_fault"
    SHAPES[name] = make_shape(name, {"no_override", "misreport"})
    try:
        for shape, want in [(name, False), ("fixed", True), ("honest_refactor", True)]:
            case = investigate(shape, claim, 11)
            trial = case["trial"]
            ctx = context("unused")
            ctx.output.update(copy.deepcopy(trial))
            ctx.expected_output.update(case["label"])
            assert trial["lab8_pass"] is True
            assert RefundAmountCorrect().evaluate(ctx).value is True
            assert ReplyAmountCorrect().evaluate(ctx).value is want
    finally:
        SHAPES.pop(name, None)
