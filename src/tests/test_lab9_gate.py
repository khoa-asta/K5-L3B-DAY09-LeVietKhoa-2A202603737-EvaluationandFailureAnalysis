"""M4: paired differences, equality and the configured CI affect gate decisions."""
import math

import pytest

from lab9 import gate, stats


pytestmark = pytest.mark.student


def report(values):
    return {"manifest": {"eval_set_sha": "test-set", "items": len(values), "seeds": [11]},
            "rows": [{"item_id": f"E-{i:03}", "seed": 11, "pass_rate": value} for i, value in enumerate(values)],
            "metrics": {"pass_rate": sum(values) / len(values)}, "evaluator_failures": []}


def spec(confidence=0.95):
    return {"eval_set_version": "v1",
            "bootstrap": {"n_resamples": 1000, "rng": 2027, "confidence": confidence},
            "metrics": [{"id": "pass_rate", "blocking": True, "kind": "capability",
                         "threshold": {"min": 0.5, "no_significant_drop": True}}]}


def test_lab9_gate_blocks_significant_drop_even_above_absolute_floor():
    blocked, lines = gate.check(report([0.8] * 5), report([1.0] * 5), spec())
    assert blocked == ["pass_rate"]
    assert "Δ -0.200" in lines[0]


def test_lab9_gate_accepts_identical_and_improved_results():
    baseline = report([0.8] * 5)
    assert gate.check(baseline, baseline, spec())[0] == []
    assert gate.check(report([1.0] * 5), baseline, spec())[0] == []


def test_lab9_gate_pairs_by_item_id_despite_row_order():
    baseline = report([1.0, 0.5, 0.8, 1.0])
    reordered = report([1.0, 0.5, 0.8, 1.0])
    reordered["rows"].reverse()
    assert gate.check(reordered, baseline, spec())[0] == []


def test_lab9_gate_uses_configured_confidence():
    baseline, candidate = report([1.0] * 4), report([1.0, 1.0, 1.0, 0.2])
    assert gate.check(candidate, baseline, spec(0.95))[0] == []
    assert gate.check(candidate, baseline, spec(0.2))[0] == ["pass_rate"]


@pytest.mark.parametrize("left,right", [([], []), ([1.0], []), ([math.nan, 1.0], [1.0, 1.0]),
                                      ([[1.0], [1.0]], [[1.0], [1.0]])])
def test_lab9_bootstrap_rejects_invalid_pairs(left, right):
    with pytest.raises(ValueError):
        stats.paired_bootstrap(left, right)
