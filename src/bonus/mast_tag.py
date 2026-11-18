"""Classify failed benchmark trials using explicit MAST-inspired rules."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bonus.mast_fault_variants import build_fault_trials

SYSTEM_DESIGN = "system_design"
INTER_AGENT_MISALIGNMENT = "inter_agent_misalignment"
TASK_VERIFICATION = "task_verification"
CATEGORIES = (SYSTEM_DESIGN, INTER_AGENT_MISALIGNMENT, TASK_VERIFICATION)


def trial_id(trial: dict[str, Any]) -> str:
    if "trial_id" in trial:
        return str(trial["trial_id"])
    if "fault_id" in trial:
        return str(trial["fault_id"])
    return f"public:{trial.get('shape')}:{trial.get('claim_id')}:{trial.get('seed')}"


def classify_failure(
    trial: dict[str, Any],
    trace: dict[str, Any] | None,
) -> dict[str, str]:
    reason = str(trial.get("reason", ""))
    if trace is None or not isinstance(trace.get("events"), list):
        return _tag(SYSTEM_DESIGN, "missing_or_invalid_trace", "No readable trace was available.")
    if trace.get("trace_error") or (
        trial.get("run_id") and trace.get("run_id") != trial["run_id"]
    ):
        return _tag(
            SYSTEM_DESIGN,
            "trace_integrity_failure",
            "Trace is malformed or its run_id does not match the failed trial.",
        )

    events = trace["events"]
    payloads = [
        (str(event.get("kind", "")), event.get("payload") or {})
        for event in events
        if isinstance(event, dict) and isinstance(event.get("payload", {}), dict)
    ]

    for kind, payload in payloads:
        if kind == "handoff":
            required = payload.get("required_context") or []
            facts = payload.get("facts") or {}
            missing = sorted(set(required) - set(facts))
            if missing:
                return _tag(
                    INTER_AGENT_MISALIGNMENT,
                    "missing_handoff_context",
                    f"Handoff omitted required context fields: {', '.join(missing)}.",
                )
        if kind == "investigator" and payload.get("missing_context"):
            missing = ", ".join(sorted(map(str, payload["missing_context"])))
            return _tag(
                INTER_AGENT_MISALIGNMENT,
                "missing_handoff_context",
                f"Investigator reported missing context: {missing}.",
            )

    for kind, payload in payloads:
        if kind == "approval_check" and payload.get("performed") is False:
            host_denied = any(
                event_kind == "refund_outcome"
                and event_payload.get("ok") is False
                and "approval" in str(event_payload.get("reason", "")).lower()
                for event_kind, event_payload in payloads
            )
            if host_denied:
                return _tag(
                    SYSTEM_DESIGN,
                    "approval_gate_skipped",
                    "The shape skipped its approval check and the host denied the write.",
                )

    for kind, payload in payloads:
        if kind == "model_override":
            return _tag(
                TASK_VERIFICATION,
                "unverified_ticket_override",
                "A model-derived ticket value overrode the structured order value.",
            )
        if kind in {"policy_lookup", "quote"}:
            clauses = payload.get("clause_ids") or [payload.get("clause_id")]
            if payload.get("is_current") is False or any(
                "OLD" in str(clause) for clause in clauses if clause
            ):
                return _tag(
                    TASK_VERIFICATION,
                    "stale_policy_clause",
                    "The trace shows a non-current policy clause in lookup or quote evidence.",
                )

    lowered = reason.lower()
    if lowered.startswith(
        (
            "exception",
            "invalid_result",
            "wrong_claim_id",
            "missing_trace",
            "stale_trace",
            "invalid_trace",
            "trace_run_id_mismatch",
        )
    ) or trial.get("status") == "error":
        return _tag(
            SYSTEM_DESIGN,
            "execution_or_contract_failure",
            f"Trial failed at execution or contract validation: {reason or 'status=error'}.",
        )
    if any(
        token in lowered
        for token in ("status ", "proposal_mismatch", "refund_mismatch", "committed_audit")
    ):
        return _tag(
            TASK_VERIFICATION,
            "decision_or_effect_mismatch",
            f"Observed result disagreed with the benchmark oracle: {reason}.",
        )
    return _tag(
        SYSTEM_DESIGN,
        "unclassified_failure",
        f"No more specific trace signature matched; retained conservative system-design tag. {reason}",
    )


def _tag(category: str, mode: str, rationale: str) -> dict[str, str]:
    return {"category": category, "failure_mode": mode, "rationale": rationale}


def cohen_kappa(
    manual: list[str],
    predicted: list[str],
) -> dict[str, Any]:
    if len(manual) != len(predicted):
        raise ValueError("manual and predicted labels must have equal lengths")
    if not manual:
        raise ValueError("at least one manually labeled trial is required")
    if any(label not in CATEGORIES for label in manual + predicted):
        raise ValueError("labels must use the three MAST category names")

    n = len(manual)
    observed = sum(left == right for left, right in zip(manual, predicted)) / n
    manual_counts = Counter(manual)
    predicted_counts = Counter(predicted)
    expected = sum(
        (manual_counts[category] / n) * (predicted_counts[category] / n)
        for category in CATEGORIES
    )
    kappa = 1.0 if expected == 1.0 and observed == 1.0 else (
        (observed - expected) / (1.0 - expected) if expected != 1.0 else 0.0
    )
    confusion: dict[str, dict[str, int]] = {
        category: {predicted_category: 0 for predicted_category in CATEGORIES}
        for category in CATEGORIES
    }
    for manual_label, predicted_label in zip(manual, predicted):
        confusion[manual_label][predicted_label] += 1
    return {
        "n": n,
        "observed_agreement": observed,
        "cohen_kappa": kappa,
        "manual_counts": dict(manual_counts),
        "predicted_counts": dict(predicted_counts),
        "confusion_matrix": confusion,
    }


def build_report(
    benchmark: dict[str, Any],
    *,
    traces_dir: Path,
    manual_labels: list[dict[str, str]],
) -> dict[str, Any]:
    failed_rows = [row for row in benchmark.get("trials", []) if row.get("passed") is False]
    faults = build_fault_trials()
    tagged: list[dict[str, Any]] = []
    by_shape_category: dict[str, Counter[str]] = defaultdict(Counter)

    for trial in failed_rows:
        trace = _read_trace(traces_dir / f"{trial.get('run_id', '')}.json")
        tagged_row = _tagged_row(trial, trace)
        tagged.append(tagged_row)
        by_shape_category[tagged_row["shape"]][tagged_row["category"]] += 1

    for trial in faults:
        tagged_row = _tagged_row(trial, trial["trace"])
        tagged.append(tagged_row)
        by_shape_category[tagged_row["shape"]][tagged_row["category"]] += 1

    by_id = {trial_id(row): row for row in tagged}
    matched_labels = []
    for label in manual_labels:
        record = by_id.get(label["trial_id"])
        if record is None:
            raise ValueError(f"manual label has no corresponding failed trial: {label['trial_id']}")
        matched_labels.append(
            {
                "trial_id": label["trial_id"],
                "manual_category": label["category"],
                "predicted_category": record["category"],
                "manual_failure_mode": label["failure_mode"],
                "predicted_failure_mode": record["failure_mode"],
            }
        )

    categories = {
        shape: {category: counts.get(category, 0) for category in CATEGORIES}
        for shape, counts in sorted(by_shape_category.items())
    }
    return {
        "source_benchmark": "reports/benchmark.json",
        "method": "rule-based trace and failure-reason classification; synthetic fault variants are reported separately",
        "public_failure_count": len(failed_rows),
        "fault_variant_count": len(faults),
        "manually_labeled_count": len(matched_labels),
        "by_shape_category": categories,
        "public_failures": [
            row for row in tagged if not row["trial_id"].startswith("fault_")
        ],
        "fault_variant_failures": [
            row for row in tagged if row["trial_id"].startswith("fault_")
        ],
        "manual_validation": {
            "labels": matched_labels,
            **cohen_kappa(
                [label["manual_category"] for label in matched_labels],
                [label["predicted_category"] for label in matched_labels],
            ),
        },
        "limitations": [
            "Fault variants are controlled synthetic cases, not additional production shapes.",
            "MAST categories are used as an interpretive taxonomy; this small lab set does not validate MAST generally.",
            "The public benchmark has few failures, so agreement is mainly measured on the 15 controlled fault cases plus labeled public failures.",
        ],
    }


def _tagged_row(
    trial: dict[str, Any],
    trace: dict[str, Any] | None,
) -> dict[str, Any]:
    tag = classify_failure(trial, trace)
    return {
        "trial_id": trial_id(trial),
        "shape": trial.get("shape", "unknown"),
        "claim_id": trial.get("claim_id"),
        "seed": trial.get("seed"),
        "reason": trial.get("reason", ""),
        **tag,
    }


def _read_trace(path: Path) -> dict[str, Any] | None:
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"events": [], "trace_error": type(exc).__name__}
    return body if isinstance(body, dict) else None


def _load_manual_labels(path: Path) -> list[dict[str, str]]:
    labels = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(labels, list):
        raise ValueError("manual labels file must contain a JSON list")
    return labels


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tag failed trials with MAST-inspired categories")
    parser.add_argument("--benchmark", default="reports/benchmark.json")
    parser.add_argument("--traces", default="traces")
    parser.add_argument("--manual-labels", default="bonus/mast_manual_labels.json")
    parser.add_argument("--out", default="reports/bonus_mast.json")
    args = parser.parse_args(argv)

    benchmark = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    report = build_report(
        benchmark,
        traces_dir=Path(args.traces),
        manual_labels=_load_manual_labels(Path(args.manual_labels)),
    )
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("shape × MAST category")
    for shape, counts in report["by_shape_category"].items():
        print(f"{shape}: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    agreement = report["manual_validation"]
    print(
        "manual labels: "
        f"{agreement['n']} | agreement={agreement['observed_agreement']:.3f} "
        f"| Cohen's kappa={agreement['cohen_kappa']:.3f}"
    )
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
