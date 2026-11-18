"""M2: calibration rejects weak, undefined and just-below-floor judges."""
import csv
import math
from pathlib import Path

import pytest

from lab9 import stats
from lab9.judge import calibrate


pytestmark = pytest.mark.student


def write_labels(path, pairs):
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["item_id", "reply", "human", "judge"])
        for i, (human, judge) in enumerate(pairs):
            writer.writerow([f"test-{i}", "fixture reply", human, judge])


@pytest.mark.parametrize("name,passed,cm,kappa", [
    ("tone", True, {"tp": 24, "fp": 4, "fn": 6, "tn": 66}, 0.757),
    ("helpful", False, {"tp": 9, "fp": 0, "fn": 21, "tn": 70}, 0.375),
])
def test_public_judge_decisions(name, passed, cm, kappa):
    result = calibrate(Path(f"data/eval/judge_{name}_public.csv"))
    assert result["passed"] is passed
    assert result["confusion"] == cm
    assert result["kappa"] == kappa
    assert result["corrected_fail_rate"] == 0.3
    assert len(result["disagreements"]) == cm["fp"] + cm["fn"]


@pytest.mark.parametrize("human,judge", [
    (["PASS"], []), (["UNKNOWN"], ["PASS"]), (["FAIL"], ["UNKNOWN"]),
])
def test_confusion_rejects_unpaired_or_invalid_labels(human, judge):
    with pytest.raises(ValueError):
        stats.confusion(human, judge)


def test_no_positive_predictions_have_zero_precision_and_recall():
    assert stats.precision_recall(["FAIL", "PASS"], ["PASS", "PASS"]) == (0.0, 0.0)
    assert stats.precision_recall(["PASS"], ["FAIL"]) == (0.0, 0.0)
    assert stats.precision_recall([], []) == (0.0, 0.0)
    with pytest.raises(ValueError):
        stats.cohen_kappa([], [])


def test_complete_disagreement_has_negative_kappa():
    assert stats.cohen_kappa(["FAIL", "PASS"], ["PASS", "FAIL"]) == -1.0


@pytest.mark.parametrize("label", ["PASS", "FAIL"])
def test_undefined_kappa_fails_calibration(tmp_path, label):
    source = tmp_path / "constant.csv"
    write_labels(source, [(label, label)] * 5)
    result = calibrate(source)
    assert math.isnan(result["kappa"])
    assert result["passed"] is False


def test_rounding_cannot_promote_a_judge_below_precision_floor(tmp_path):
    source = tmp_path / "near-floor.csv"
    write_labels(source, [("FAIL", "FAIL")] * 799 + [("PASS", "FAIL")] * 200
                 + [("FAIL", "PASS")] * 100 + [("PASS", "PASS")] * 1000)
    result = calibrate(source)
    assert result["precision"] == 0.8  # Displayed rounding of 799/999 < 0.8.
    assert result["kappa"] >= 0.6 and result["recall"] >= 0.7
    assert result["passed"] is False


@pytest.mark.parametrize("rates", [
    (0.5, 0.5, 0.5), (float("nan"), 0.8, 0.9), (0.2, -0.1, 0.9), (1.1, 0.8, 0.9),
])
def test_rogan_gladen_rejects_undefined_or_invalid_rates(rates):
    with pytest.raises(ValueError):
        stats.rogan_gladen(*rates)


def test_rogan_gladen_clips_above_one():
    assert stats.rogan_gladen(1.0, 0.8, 0.9) == 1.0


def test_empty_calibration_is_rejected(tmp_path):
    source = tmp_path / "empty.csv"
    write_labels(source, [])
    with pytest.raises(ValueError, match="at least one"):
        calibrate(source)
