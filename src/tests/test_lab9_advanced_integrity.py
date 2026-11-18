"""M6/M7 independent vectors: numerical boundaries and report/spec gaming."""
import copy
import math

import pytest

from lab9 import gate, stats
from lab9.eval import aggregate, per_item


pytestmark = pytest.mark.student


def spec():
    return {"eval_set_version": "v2", "metrics": [
        {"id": "pass_rate", "kind": "capability", "blocking": True,
         "threshold": {"min": 0.8, "no_significant_drop": True}},
        {"id": "secret_leak", "kind": "safety", "blocking": True, "threshold": {"max": 0}},
        {"id": "cost_per_success", "kind": "efficiency", "blocking": False, "threshold": {"max_increase": 0.1}},
    ], "slices": [{"name": "group", "metric": "pass_rate", "min": 0.9,
                    "no_significant_drop": True, "blocking": True}]}


def report():
    rows = [{"item_id": f"E-{i}", "seed": seed, "pass_rate": True, "secret_leak": False,
             "cost": 1.0, "slices": ["group"] if i < 2 else []} for i in range(4) for seed in (11,22)]
    return {"manifest": {"eval_set_sha": "example", "items": 4, "seeds": [11,22]},
            "rows": rows, "metrics": aggregate(rows, ["pass_rate", "secret_leak"]), "evaluator_failures": []}


def test_pass_estimators_match_exact_combinatorics_and_ordering():
    for n in range(1, 10):
        for c in range(n + 1):
            for k in range(1, n + 1):
                expected_at = 1 - math.comb(n-c,k) / math.comb(n,k) if n-c >= k else 1.0
                expected_hat = math.comb(c,k) / math.comb(n,k) if c >= k else 0.0
                at, hat = stats.pass_at_k(n,c,k), stats.pass_hat_k(n,c,k)
                assert at == pytest.approx(expected_at, abs=1e-14)
                assert hat == pytest.approx(expected_hat, abs=1e-14)
                assert hat <= c/n + 1e-14 <= at + 2e-14


def test_pass_estimators_keep_rare_probabilities_and_near_certainty():
    assert stats.pass_at_k(10**18, 1, 1) == pytest.approx(1e-18, rel=1e-12, abs=0)
    assert stats.pass_at_k(10**18, 10**18-2, 2) == 1.0
    assert stats.pass_hat_k(10**18, 1, 2) == 0.0


def test_derived_pass_metrics_are_available_to_paired_gate_comparisons():
    sample = {"rows": [{"item_id": "A", "seed": seed, "pass_rate": seed != 55}
                       for seed in (11,22,33,44,55)]}
    assert per_item(sample, "pass_rate") == {"A": 0.8}
    assert per_item(sample, "pass_at_3") == {"A": 1.0}
    assert per_item(sample, "pass_hat_3") == {"A": 0.4}
    assert per_item(sample, "pass_hat_5") == {"A": 0.0}


def test_evalset_builder_writes_portable_lf_bytes(tmp_path, monkeypatch):
    import json
    from lab9 import evalset
    source = tmp_path / "claims.jsonl"
    source.write_text(json.dumps({"claim_id": "C-001", "matrix_id": "T01", "expected": {}}), encoding="utf-8")
    monkeypatch.setattr(evalset, "ITEMS", tmp_path / "items.jsonl")
    monkeypatch.setattr(evalset, "LABELS", tmp_path / "labels.json")
    evalset.build(source)
    assert b"\r" not in evalset.ITEMS.read_bytes()
    assert b"\r" not in evalset.LABELS.read_bytes()


@pytest.mark.parametrize("args", [(0,0,1), (-1,0,1), (5,-1,2), (5,6,1), (5,2,0),
                                  (5,2,6), (5.0,2,1), (5,2.5,1), (5,2,True)])
def test_both_pass_estimators_reject_invalid_counts(args):
    for fn in (stats.pass_at_k, stats.pass_hat_k):
        with pytest.raises(ValueError):
            fn(*args)


def test_consistent_control_and_self_comparison_pass():
    control = report()
    assert gate.integrity_check(control, control, spec(), spec()) == []
    assert gate.check(control, control, spec(), spec())[0] == []


@pytest.mark.parametrize("attack", ["duplicate", "evaluator_failure", "inflated_metric", "null_row",
                                    "nan_row", "relabel_slice", "duplicate_seed", "drop_and_resize"])
def test_green_report_traps_are_blocked_by_integrity(attack):
    base = report()
    candidate = copy.deepcopy(base)
    if attack == "duplicate":
        candidate["rows"][-1] = copy.deepcopy(candidate["rows"][0])  # Same row count, bad pair set.
    elif attack == "evaluator_failure":
        candidate["evaluator_failures"] = ["evaluator crashed despite the green summary"]
    elif attack == "inflated_metric":
        candidate["metrics"]["pass_rate"] = 0.99
    elif attack in ("null_row", "nan_row"):
        candidate["rows"][0]["pass_rate"] = None if attack == "null_row" else math.nan
    elif attack == "relabel_slice":
        for row in candidate["rows"]:
            if row["item_id"] == "E-0":
                row["slices"] = []
    elif attack == "duplicate_seed":
        candidate["manifest"]["seeds"] = [11,11]
    elif attack == "drop_and_resize":
        candidate["rows"] = candidate["rows"][2:]
        candidate["manifest"]["items"] = 3
    assert gate.check(candidate, base, spec())[0] == ["integrity"]


@pytest.mark.parametrize("attack", ["lower_min", "drop_min", "raise_max", "raise_cost", "drop_metric",
                                    "disable_blocking", "drop_ci", "drop_slice", "lower_slice", "drop_slice_ci"])
def test_ratchet_rejects_laxer_metrics_and_slices(attack):
    original = spec()
    changed = copy.deepcopy(original)
    if attack == "lower_min": changed["metrics"][0]["threshold"]["min"] = 0.5
    elif attack == "drop_min": del changed["metrics"][0]["threshold"]["min"]
    elif attack == "raise_max": changed["metrics"][1]["threshold"]["max"] = 1
    elif attack == "raise_cost": changed["metrics"][2]["threshold"]["max_increase"] = 0.5
    elif attack == "drop_metric": changed["metrics"].pop()
    elif attack == "disable_blocking": changed["metrics"][0]["blocking"] = False
    elif attack == "drop_ci": changed["metrics"][0]["threshold"].pop("no_significant_drop")
    elif attack == "drop_slice": changed["slices"] = []
    elif attack == "lower_slice": changed["slices"][0]["min"] = 0.5
    elif attack == "drop_slice_ci": changed["slices"][0].pop("no_significant_drop")
    problems = gate.integrity_check(report(), report(), changed, original)
    assert any("RATCHET" in reason for reason in problems)


def test_ratchet_allows_stricter_thresholds_and_row_reordering():
    original = spec()
    strict = copy.deepcopy(original)
    strict["metrics"][0]["threshold"]["min"] = 0.9
    strict["slices"][0]["min"] = 0.95
    candidate = report()
    candidate["rows"].reverse()
    assert gate.integrity_check(candidate, report(), strict, original) == []
