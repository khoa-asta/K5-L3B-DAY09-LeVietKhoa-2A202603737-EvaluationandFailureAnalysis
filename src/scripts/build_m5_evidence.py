"""Generate M5 v2 reports and prove a slice catches a hidden aggregate regression.

Run from src/: python -m scripts.build_m5_evidence
"""
from __future__ import annotations

from collections import Counter
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile

from lab8.shapes import SHAPES
from lab9 import evalset, gate, variants
from lab9.eval import load_spec, load_world, main as eval_main, make_task, per_item
from lab9.variant_agent import make_shape


SPEC = Path("config/metric_spec_v2.yaml")
OUTPUT = Path("../docs/evidence/m5_slice_validation.json")
JOBS = {"baseline": ("swarm", "reports/baseline_v2.json"),
        "fixed": ("fixed", "reports/eval_fixed_v2.json"),
        "honest_refactor": ("honest_refactor", "reports/eval_honest_refactor_v2.json"),
        "slice_regression": ("slice_regression", "reports/eval_slice_regression.json")}


def main() -> None:
    if evalset.check(evalset.ITEMS_V2, evalset.LABELS_V2):
        raise RuntimeError("Build and check eval set v2 first")
    spec = load_spec(SPEC)
    reports, decisions = {}, {}
    for name, (shape, path) in JOBS.items():
        if eval_main(["--shape", shape, "--spec", str(SPEC), "--out", path]) != 0:
            raise RuntimeError(f"Cannot evaluate {name}")
        reports[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    for name in JOBS:
        stream = StringIO()
        with redirect_stdout(stream):
            code = gate.main(["--pr", JOBS[name][1], "--baseline", JOBS["baseline"][1], "--spec", str(SPEC)])
        decisions[name] = {"exit_code": code, "stdout": stream.getvalue()}
        print(stream.getvalue(), end="")
        if code != (1 if name == "slice_regression" else 0):
            raise RuntimeError(f"Unexpected gate decision: {name}")
    aggregate_only = gate.check(reports["slice_regression"], reports["baseline"], {**spec, "slices": []})
    if aggregate_only[0]:
        raise RuntimeError("This experiment must pass aggregate gates before slice gates are added")
    blocked, _ = gate.check(reports["slice_regression"], reports["baseline"], spec)
    if blocked != ["slice:money_movement/pass_rate"]:
        raise RuntimeError(f"Expected only the money_movement slice to block: {blocked}")

    # Keep step-level proof for FM-09 attempts and the other adversarial mechanisms.
    variants.register()
    world, claims = load_world(spec)
    labels = json.loads(evalset.LABELS_V2.read_text(encoding="utf-8"))
    cases = [("fixed", c) for c in ("C-110", "C-113", "C-114", "C-105")]
    cases += [("seeded_regression", c) for c in ("C-101", "C-105", "C-108")]
    cases += [("slice_regression", "C-105")]
    temporary_shapes = {"m5_stale_clause": "stale_clause", "m5_sibling_refund": "sibling_refund", "m5_misreport": "misreport"}
    for name, bug in temporary_shapes.items():
        SHAPES[name] = make_shape(name, {"no_override", bug})
    cases += [("m5_stale_clause", "C-103"), ("m5_sibling_refund", "C-107"), ("m5_misreport", "C-109")]
    traces = {}
    try:
        with tempfile.TemporaryDirectory(prefix="lab9-m5-", ignore_cleanup_errors=True) as tmp:
            for shape, claim in cases:
                trial = make_task(shape, world, claims, labels, Path(tmp))({"claim_id": claim, "seed": 11})
                trial.pop("blob", None)
                traces[trial["result"]["run_id"]] = trial
    finally:
        for name in temporary_shapes:
            SHAPES.pop(name, None)
    items = evalset.load_jsonl(evalset.ITEMS_V2)
    slice_values = {name: {entry["name"]: sum(values.values()) / len(values)
                          for entry in spec["slices"]
                          if (values := per_item(report, entry["metric"], entry["name"]))}
                    for name, report in reports.items()}
    evidence = {
        "generator": "python -m scripts.build_m5_evidence", "scope": "M5 local validation",
        "spec_sha12": evalset.sha12(SPEC), "gate_sha12": evalset.sha12(Path("lab9/gate.py")),
        "eval_set_sha12": evalset.sha12(evalset.ITEMS_V2),
        "pack_sha12": evalset.sha12(evalset.PACK), "fm_map_sha12": evalset.sha12(evalset.FM_MAP),
        "fm_counts": dict(sorted(Counter(fm for it in items for fm in it["failure_modes"]).items())),
        "slice_counts": dict(Counter(s for it in items for s in it["slices"])),
        "aggregate_only_blocked": aggregate_only[0], "slice_blocked": blocked,
        "slice_values": slice_values, "decisions": decisions,
        "report_paths": {name: path for name, (_, path) in JOBS.items()},
        "report_sha12": {name: evalset.sha12(Path(path)) for name, (_, path) in JOBS.items()},
        "reports": reports, "traces": traces,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: aggregate gates pass; money_movement slice blocks; controls pass")


if __name__ == "__main__":
    main()
