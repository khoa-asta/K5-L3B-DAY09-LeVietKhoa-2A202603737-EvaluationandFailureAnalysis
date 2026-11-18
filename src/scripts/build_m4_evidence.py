"""Generate baseline, PR reports and exact M4 CLI gate evidence from src/."""
from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess

from lab9 import ci_check, gate, stats
from lab9.eval import load_spec, main as eval_main, per_item
from lab9.evalset import sha12


OUTPUT = Path("../docs/evidence/m4_gate_validation.json")
JOBS = {"baseline": ("swarm", "reports/baseline_v1.json"),
        "pr": ("swarm", "reports/eval_pr.json"),
        "fixed": ("fixed", "reports/eval_fixed.json"),
        "seeded_regression": ("seeded_regression", "reports/eval_seeded_regression.json")}


def capture(main, argv):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(argv)
    output = stream.getvalue()
    print(output, end="")
    return {"exit_code": code, "stdout": output}


def main() -> None:
    reports = {}
    for name, (shape, path) in JOBS.items():
        if eval_main(["--shape", shape, "--out", path]) != 0:
            raise RuntimeError(f"Cannot generate {name} report")
        reports[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    decisions = {}
    for name in ("pr", "fixed", "seeded_regression"):
        decisions[name] = capture(gate.main, ["--pr", JOBS[name][1], "--baseline", JOBS["baseline"][1]])
        expected = 1 if name == "seeded_regression" else 0
        if decisions[name]["exit_code"] != expected:
            raise RuntimeError(f"Wrong gate decision for {name}")
    if "pass_rate" not in decisions["seeded_regression"]["stdout"].split("blocked: ")[-1]:
        raise RuntimeError("Regression must be explicitly blocked on pass_rate")
    sanity = capture(ci_check.main, ["--pr", JOBS["pr"][1], "--baseline", JOBS["baseline"][1]])
    if sanity["exit_code"] != 0:
        raise RuntimeError("Baseline/spec sanity check failed")
    spec = load_spec()
    bootstrap = spec["bootstrap"]
    comparisons = {}
    for name in ("pr", "fixed", "seeded_regression"):
        comparisons[name] = {}
        for metric in ("pass_rate", "refund_amount_correct", "reply_amount_correct"):
            candidate = per_item(reports[name], metric)
            baseline = per_item(reports["baseline"], metric)
            keys = sorted(baseline)
            delta, lo, hi = stats.paired_bootstrap(
                [candidate[k] for k in keys], [baseline[k] for k in keys],
                n_resamples=bootstrap["n_resamples"], rng=bootstrap["rng"],
                confidence=bootstrap["confidence"],
            )
            comparisons[name][metric] = {"delta": delta, "lo": lo, "hi": hi}
    evidence = {
        "generator": "python -m scripts.build_m4_evidence",
        "scope": "local workflow checks; GitHub Actions has not been run by this script",
        "source_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        "source_sha12": {p: sha12(Path(p)) for p in (
            "lab9/stats.py", "lab9/graders.py", "lab9/gate.py", "config/metric_spec.yaml", "harness_map.yaml")},
        "bootstrap": bootstrap, "comparisons": comparisons,
        "decisions": decisions, "ci_check": sanity,
        "report_paths": {name: path for name, (_, path) in JOBS.items()},
        "report_sha12": {name: sha12(Path(path)) for name, (_, path) in JOBS.items()},
        "reports": reports,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: swarm/fixed exit 0, seeded_regression exit 1, ci_check exit 0")


if __name__ == "__main__":
    main()
