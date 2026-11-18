"""M5 slice gates must use item-level scores and reject unusable slice evidence."""
import copy
import math

import pytest

from lab9.gate import slice_check


pytestmark = pytest.mark.student


def report(values=(1.0, 1.0)):
    return {"rows": [{"item_id": f"E-{i}", "seed": 11, "pass_rate": value,
                      "slices": ["custom_group"]} for i, value in enumerate(values)]}


def spec(**overrides):
    entry = {"name": "custom_group", "metric": "pass_rate", "min": 0.9, "blocking": True}
    entry.update(overrides)
    return {"bootstrap": {"rng": 2027, "n_resamples": 1000, "confidence": 0.95}, "slices": [entry]}


def test_slice_accepts_identical_control():
    base = report()
    assert slice_check(base, base, spec(no_significant_drop=True))[0] == []


def test_slice_blocks_significant_drop_above_floor():
    blocked, lines = slice_check(report((0.8, 0.8)), report(), spec(min=0.5, no_significant_drop=True))
    assert blocked == ["slice:custom_group/pass_rate"]
    assert "CI [-0.200, -0.200]" in lines[0]


def test_slice_nonblocking_failure_warns():
    blocked, lines = slice_check(report((0.0, 0.0)), report(), spec(blocking=False))
    assert blocked == [] and lines[0].endswith("warn")


def test_slice_weights_each_item_equally_instead_of_each_row():
    base = {"rows": [{"item_id": "A", "seed": seed, "slices": ["custom_group"], "pass_rate": 1.0}
                     for seed in (11, 22, 33)]
                    + [{"item_id": "B", "seed": 11, "slices": ["custom_group"], "pass_rate": 1.0}]}
    candidate = copy.deepcopy(base)
    candidate["rows"][-1]["pass_rate"] = 0.0
    blocked, lines = slice_check(candidate, base, spec(min=0.6))
    assert blocked == ["slice:custom_group/pass_rate"]
    assert "0.5000" in lines[0]  # Row-weighted mean 0.75 would incorrectly pass.


@pytest.mark.parametrize("bad", [None, math.nan, math.inf])
def test_slice_rejects_missing_or_nonfinite_scores(bad):
    candidate = report()
    candidate["rows"][0]["pass_rate"] = bad
    assert slice_check(candidate, report(), spec())[0] == ["slice:custom_group/pass_rate"]


def test_slice_rejects_empty_or_dropped_item_coverage():
    candidate = report()
    candidate["rows"].pop()
    assert slice_check(candidate, report(), spec())[0] == ["slice:custom_group/pass_rate"]
    assert slice_check({"rows": []}, report(), spec())[0] == ["slice:custom_group/pass_rate"]


def test_slice_aligns_items_when_row_order_changes():
    base = report((0.8, 1.0))
    candidate = copy.deepcopy(base)
    candidate["rows"].reverse()
    assert slice_check(candidate, base, spec(min=0.8, no_significant_drop=True))[0] == []
