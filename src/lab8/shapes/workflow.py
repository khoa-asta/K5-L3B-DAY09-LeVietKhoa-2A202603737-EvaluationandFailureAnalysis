"""Shape A — deterministic workflow. Student work.

Signature (do not change):

    run_claim(claim_id, *, seed, store_path, crash_at=None) -> RunResult

Suggested steps. Money stays in code (`lab8.tools.compute_compensation`).

1. Open the store. Read the claim through `get_claim_view` (not SELECT *).
2. Missing order_id -> status `needs_info`. Do not write the ledger.
3. `lookup_order`. If not visible -> `escalated`. Do not copy phone, address, item, internal note.
4. Quote from the order row. Ignore delay numbers written in the ticket.
5. Quote amount 0 -> `denied`. Do not call issue_refund.
6. Quote amount > 0 -> `durability.issue_refund(conn, claim_id, <full quote>)`.
   Pass the FULL quote. The host checks the claim's own approval and subtracts
   what earlier claims already got for the same order (T13, T14). Do not
   subtract it yourself or the host subtracts twice.
   Auth failure or order already refunded -> `denied` (the host writes `policy_denied`).
   `proposal_amount` stays the full quote. Amount conflict -> `failed`.
7. Success -> `resolved`. One ledger row, one `refund_committed` audit.
8. Use MockLLM only to draft the reply text, if you want a model call at all.

The model must not choose the refund amount and must not commit the refund.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.

Trace policy of this shape (what is deliberately NOT written):
- the ticket text (free user text, may carry secrets or PII),
- `principal_id` and any raw claim / order row (only the allowlisted
  `lookup_order` view is traced),
- the drafted reply text and the full ledger row returned by the host.
"""

from __future__ import annotations

import sqlite3

from lab8 import durability
from lab8.db import connect
from lab8.mock_llm import complete
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish
from lab8.tools import compute_compensation, get_claim_view, lookup_order, tool_cost
from lab8.trace import Trace

SHAPE = "workflow"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    trace = Trace(make_run_id(SHAPE, claim_id, seed))

    def done(status: str, proposal: int, reason: str | None) -> RunResult:
        # Model only drafts the customer reply; it never sees amounts it could change.
        complete(budget, seed=seed, purpose="draft", prompt=f"status={status}")
        trace.add("decision", {"status": status, "proposal_amount": int(proposal), "reason": reason})
        return finish(
            conn,
            shape=SHAPE,
            claim_id=claim_id,
            seed=seed,
            status=status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=reason,
        )

    # Step 1: claim through the allowlisted view.
    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim["found"]:
        trace.add("claim", {"claim_id": claim_id, "found": False})
        return done("failed", 0, "unknown_claim")
    order_id = claim.get("order_id")
    trace.add("claim", {"claim_id": claim_id, "found": True, "has_order_id": bool(order_id)})

    # Step 2: never infer the order id from ticket text.
    if not order_id:
        return done("needs_info", 0, "missing_order_id")

    # Step 3: ownership / existence checked by the read tool.
    budget.add_tool(tool_cost())
    order_view = lookup_order(conn, order_id, claim["principal_id"])
    if not order_view["visible"]:
        trace.add("lookup_order", {"visible": False, "reason": order_view["reason"]})
        return done("escalated", 0, order_view["reason"])
    order = order_view["order"]
    trace.add("lookup_order", {"visible": True, "order": order})

    # Step 4: quote from the order row and current policies only.
    budget.add_tool(tool_cost())
    quote_payload = compute_compensation(conn, order)
    proposal = int(quote_payload["amount_vnd"])
    trace.add("quote", quote_payload)

    # Step 5: nothing to pay -> deny without touching the host.
    if proposal <= 0:
        return done("denied", 0, quote_payload.get("reason"))

    # Step 6: host is the only writer. Full quote in, crash_at forwarded, InjectedCrash not caught.
    try:
        outcome = durability.issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except durability.InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise
    trace.add(
        "issue_refund",
        {"ok": outcome["ok"], "reason": outcome["reason"], "conflict": outcome["conflict"]},
    )

    if not outcome["ok"]:
        return done("failed" if outcome["conflict"] else "denied", proposal, outcome["reason"])

    # Step 7: committed (or idempotent replay of the same amount).
    return done("resolved", proposal, None)
