"""Small, intentionally faulty trace variants for validating MAST tagging rules."""

from __future__ import annotations

from typing import Any


SEEDS = (11, 22, 33, 44, 55)


def build_fault_trials() -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    variants = (
        _handoff_drops_delay,
        _uses_stale_clause,
        _skips_approval_check,
    )
    for variant in variants:
        trials.extend(variant(seed) for seed in SEEDS)
    return trials


def _trial(
    variant: str,
    seed: int,
    reason: str,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    fault_id = f"{variant}:{seed}"
    return {
        "fault_id": fault_id,
        "shape": variant,
        "claim_id": f"FAULT-{variant}",
        "seed": seed,
        "passed": False,
        "status": "failed",
        "reason": reason,
        "trace": {"run_id": f"R-{fault_id}", "events": events},
    }


def _handoff_drops_delay(seed: int) -> dict[str, Any]:
    return _trial(
        "fault_handoff_drops_delay",
        seed,
        "investigator cannot verify the order delay",
        [
            {
                "kind": "handoff",
                "payload": {
                    "facts": {},
                    "required_context": ["delay_days"],
                    "allowed_tools": ["lookup_order"],
                },
            },
            {
                "kind": "investigator",
                "payload": {"missing_context": ["delay_days"], "result": "cannot_verify"},
            },
        ],
    )


def _uses_stale_clause(seed: int) -> dict[str, Any]:
    return _trial(
        "fault_uses_stale_clause",
        seed,
        "quote selected a non-current policy clause",
        [
            {
                "kind": "policy_lookup",
                "payload": {"clause_id": "SHIP-LATE-OLD", "is_current": False},
            },
            {
                "kind": "quote",
                "payload": {"clause_ids": ["SHIP-LATE-OLD"], "amount_vnd": 35000},
            },
        ],
    )


def _skips_approval_check(seed: int) -> dict[str, Any]:
    return _trial(
        "fault_skips_approval_check",
        seed,
        "host denied the write because the approval check was skipped",
        [
            {"kind": "approval_check", "payload": {"performed": False}},
            {"kind": "refund_outcome", "payload": {"ok": False, "reason": "approval_missing"}},
        ],
    )
