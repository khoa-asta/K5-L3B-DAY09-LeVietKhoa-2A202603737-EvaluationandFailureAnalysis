"""Shape C — orchestrator plus read-only investigators. Student work.

1. Build a handoff with `lab8.handoff.make_handoff`. Allowed tools are read-only.
   Never put parent_secret, raw headers, or the full claim row into facts.
2. `lab8.runtime.run_readonly_investigators` runs those tools.
3. The orchestrator quotes from the investigator's order view and calls
   `durability.issue_refund`. Investigators have no write registry.
   Pass the full quote; the host subtracts earlier refunds on the same order.
   `lookup_refund_history` is a read-only tool you may hand to an investigator.
4. Trace the sanitized handoff, not the parent context.

An LLM summary of the parent context is not a sanitizer. Use the allowlist.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3

from lab8.db import connect
from lab8.durability import issue_refund
from lab8.handoff import make_handoff
from lab8.runtime import run_readonly_investigators
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import get_claim_view, tool_cost
from lab8.trace import Trace


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(
            conn,
            claim_id,
            seed=seed,
            crash_at=crash_at,
        )
    finally:
        conn.close()


def _run(
    conn: sqlite3.Connection,
    claim_id: str,
    *,
    seed: int,
    crash_at: str | None,
) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id("orchestrator", claim_id, seed))

    # Mọi nhánh kết quả đều dùng finish để ghi trace,
    # đọc ledger và tổng hợp budget theo cùng một contract.
    def done(
        status: str,
        proposal: int = 0,
        reason: str | None = None,
    ) -> RunResult:
        trace.add(
            "decision",
            {
                "status": status,
                "proposal_amount": proposal,
                "reason": reason,
            },
        )
        return finish(
            conn,
            shape="orchestrator",
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    # 1. Đọc claim bằng tool có sẵn.
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)

    # Chỉ ghi trạng thái tìm kiếm, không ghi nguyên claim/ticket.
    trace.add("claim_lookup", {"found": claim["found"]})

    if not claim["found"]:
        return done("failed", reason="unknown_claim")

    if not claim.get("order_id"):
        return done("needs_info", reason="missing_order_id")

    # 2. Tạo handoff tối thiểu, chỉ cấp tool đọc.
    handoff = make_handoff(
        request_id=f"REQ-{claim_id}",
        claim_id=claim_id,
        task="check_applicable_policy",
        facts={},
        allowed_tools=[
            "lookup_order",
            "lookup_policy",
            "compute_compensation",
        ],
    )
    trace.add("handoff", handoff)

    # 3. Investigator chỉ đọc dữ liệu trong phạm vi principal.
    investigated = run_readonly_investigators(
        conn,
        budget,
        handoff,
        principal_id=claim["principal_id"],
    )

    order_view = investigated["tools"].get("lookup_order", {})

    # Chỉ ghi kết quả kiểm tra quyền, không dump dữ liệu order.
    trace.add(
        "order_lookup",
        {
            "visible": bool(order_view.get("visible")),
            "reason": order_view.get("reason"),
        },
    )

    if not order_view.get("visible"):
        return done("escalated", reason=order_view.get("reason"))

    # 4. Quote do code compute_compensation tính từ order và policy.
    quote_payload = investigated["tools"]["compute_compensation"]
    proposal = int(quote_payload["amount_vnd"])
    trace.add("quote", quote_payload)

    if proposal <= 0:
        return done("denied", reason=quote_payload.get("reason"))

    # 5. Orchestrator gọi cổng ghi của host.
    # Truyền quote đầy đủ và để InjectedCrash truyền ra ngoài.
    outcome = issue_refund(
        conn,
        claim_id,
        proposal,
        crash_at=crash_at,
    )

    trace.add(
        "refund_outcome",
        {
            "ok": outcome["ok"],
            "conflict": outcome["conflict"],
            "reason": outcome["reason"],
        },
    )

    if outcome["ok"]:
        return done("resolved", proposal=proposal)

    if outcome["conflict"]:
        return done(
            "failed",
            proposal=proposal,
            reason=outcome["reason"],
        )

    return done(
        "denied",
        proposal=proposal,
        reason=outcome["reason"],
    )