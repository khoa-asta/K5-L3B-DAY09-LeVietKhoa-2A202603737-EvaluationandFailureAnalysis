import json
from pathlib import Path

from bonus.mast_fault_variants import build_fault_trials
from bonus.mast_tag import (
    INTER_AGENT_MISALIGNMENT,
    SYSTEM_DESIGN,
    TASK_VERIFICATION,
    _load_manual_labels,
    build_report,
    classify_failure,
    cohen_kappa,
)


def test_three_intentionally_broken_variants_cover_mast_categories():
    trials = build_fault_trials()
    assert len(trials) == 15
    assert all(trial["passed"] is False for trial in trials)

    observed = {}
    for trial in trials:
        tag = classify_failure(trial, trial["trace"])
        observed[trial["shape"]] = tag["category"]

    assert observed == {
        "fault_handoff_drops_delay": INTER_AGENT_MISALIGNMENT,
        "fault_uses_stale_clause": TASK_VERIFICATION,
        "fault_skips_approval_check": SYSTEM_DESIGN,
    }


def test_missing_or_mismatched_trace_is_system_design_failure():
    trial = {"run_id": "R-run", "reason": "status resolved != denied"}

    missing = classify_failure(trial, None)
    mismatched = classify_failure(
        trial,
        {"run_id": "R-other", "events": [{"kind": "model_override", "payload": {}}]},
    )

    assert missing["category"] == SYSTEM_DESIGN
    assert missing["failure_mode"] == "missing_or_invalid_trace"
    assert mismatched["category"] == SYSTEM_DESIGN
    assert mismatched["failure_mode"] == "trace_integrity_failure"


def test_manual_labels_report_agreement_and_public_failure_tag(tmp_path):
    benchmark = {
        "trials": [
            {
                "shape": "swarm",
                "claim_id": "C-002",
                "seed": 55,
                "run_id": "R-swarm-C-002-s55",
                "passed": False,
                "status": "resolved",
                "reason": "status resolved != denied",
            }
        ]
    }
    trace_dir = tmp_path / "traces"
    trace_dir.mkdir()
    (trace_dir / "R-swarm-C-002-s55.json").write_text(
        json.dumps(
            {
                "run_id": "R-swarm-C-002-s55",
                "events": [
                    {"kind": "model_override", "payload": {"delay_days": 5}},
                    {"kind": "quote", "payload": {"amount_vnd": 20000}},
                ],
            }
        ),
        encoding="utf-8",
    )
    labels_path = Path(__file__).parent.parent / "bonus" / "mast_manual_labels.json"
    manual_labels = _load_manual_labels(labels_path)
    report = build_report(
        benchmark,
        traces_dir=trace_dir,
        manual_labels=manual_labels,
    )
    assert report["manual_validation"]["n"] == 16
    assert report["manual_validation"]["observed_agreement"] == 1.0
    assert report["manual_validation"]["cohen_kappa"] == 1.0
    assert report["public_failures"][0]["category"] == TASK_VERIFICATION


def test_cohen_kappa_rejects_empty_or_unpaired_labels():
    try:
        cohen_kappa([], [])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("empty labels should not produce an agreement score")

    try:
        cohen_kappa([SYSTEM_DESIGN], [])
    except ValueError as exc:
        assert "equal lengths" in str(exc)
    else:
        raise AssertionError("unpaired labels should not produce an agreement score")


def test_cohen_kappa_uses_observed_and_expected_agreement():
    result = cohen_kappa(
        [SYSTEM_DESIGN, SYSTEM_DESIGN, TASK_VERIFICATION, TASK_VERIFICATION],
        [SYSTEM_DESIGN, TASK_VERIFICATION, TASK_VERIFICATION, TASK_VERIFICATION],
    )

    assert result["observed_agreement"] == 0.75
    assert result["cohen_kappa"] == 0.5
