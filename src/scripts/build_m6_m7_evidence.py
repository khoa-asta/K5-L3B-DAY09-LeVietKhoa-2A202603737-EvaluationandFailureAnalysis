"""Record official M6/M7 scorecard/traps and additional independent gaming probes.

Run after build_m5_evidence, from src/: python -m scripts.build_m6_m7_evidence
"""
from __future__ import annotations

from contextlib import redirect_stdout
import copy
from io import StringIO
import json
from pathlib import Path
import subprocess

import yaml

from lab9 import gate, mutation, traps
from lab9.eval import load_spec, main as eval_main
from lab9.evalset import sha12
from scripts.build_m6_aa import main as build_aa


SPEC = Path("config/metric_spec_v2.yaml")
OUTPUT = Path("../docs/evidence/m6_m7_validation.json")


def capture(main, args):
    stream = StringIO()
    with redirect_stdout(stream):
        code = main(args)
    output = stream.getvalue()
    print(output, end="")
    return {"exit_code": code, "stdout": output}


def main():
    build_aa()  # Final A/A confirmation, with the chosen floor and portable eval-set bytes.
    for name in ("seeded_regression", "flaky_regression"):
        if eval_main(["--shape", name, "--spec", str(SPEC), "--out", f"reports/eval_{name}_v2.json"]):
            raise RuntimeError(f"Failed evaluation: {name}")
    spec = load_spec(SPEC)
    base = json.loads(Path("reports/baseline_v2.json").read_text(encoding="utf-8"))
    fixed = json.loads(Path("reports/eval_fixed_v2.json").read_text(encoding="utf-8"))
    regression = json.loads(Path("reports/eval_slice_regression.json").read_text(encoding="utf-8"))
    flaky = json.loads(Path("reports/eval_flaky_regression_v2.json").read_text(encoding="utf-8"))
    # A trusted, committed M5 spec supplies the ratchet reference for this local run.
    base_spec_path = Path("../docs/evidence/metric_spec_v2_m5.yaml")
    base_spec_path.write_bytes(subprocess.check_output(["git", "show", "6bbac68:src/config/metric_spec_v2.yaml"]))
    base_spec = yaml.safe_load(base_spec_path.read_text(encoding="utf-8"))
    scorecard = capture(mutation.main, ["--spec", str(SPEC), "--baseline", "reports/baseline_v2.json",
                                        "--base-spec", str(base_spec_path)])
    if scorecard["exit_code"] or "mutation score 3/3" not in scorecard["stdout"] or "false alarms 0" not in scorecard["stdout"]:
        raise RuntimeError("Mutation scorecard failed")
    public_command = capture(traps.main, ["--pr", "reports/eval_slice_regression.json", "--baseline",
                                          "reports/baseline_v2.json", "--spec", str(SPEC)])
    if public_command["exit_code"]:
        raise RuntimeError("Public traps leaked")
    trap_results = {}
    for name, (report, loose) in traps.build(regression, spec).items():
        blocked, lines = gate.check(report, base, loose or spec, spec if loose else None)
        if blocked != ["integrity"] or not any("INTEGRITY" in line for line in lines):
            raise RuntimeError(f"Trap not refused as INTEGRITY: {name}")
        trap_results[name] = {"blocked": blocked, "reasons": lines}

    probes = {}
    probes["duplicate_pair_same_row_count"] = copy.deepcopy(fixed)
    probes["duplicate_pair_same_row_count"]["rows"][-1] = copy.deepcopy(fixed["rows"][0])
    probes["evaluator_failure_on_green_run"] = copy.deepcopy(fixed)
    probes["evaluator_failure_on_green_run"]["evaluator_failures"] = ["independent probe: evaluator crashed"]
    probes["relabelled_slice"] = copy.deepcopy(fixed)
    for row in probes["relabelled_slice"]["rows"]:
        if row["item_id"] == "E-001":
            row["slices"] = []
    probes["inflated_summary_on_green_run"] = copy.deepcopy(fixed)
    probes["inflated_summary_on_green_run"]["metrics"]["pass_rate"] = 0.99
    probes["swapped_seed_on_green_run"] = copy.deepcopy(fixed)
    probes["swapped_seed_on_green_run"]["manifest"]["seeds"][-1] = 110
    for row in probes["swapped_seed_on_green_run"]["rows"]:
        if row["seed"] == 55:
            row["seed"] = 110
    probe_results = {}
    for name, report in probes.items():
        path = Path(f"reports/traps/local_{name}.json")
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        blocked, lines = gate.check(report, base, spec)
        if blocked != ["integrity"]:
            raise RuntimeError(f"Additional probe escaped integrity: {name}")
        probe_results[name] = {"path": str(path), "blocked": blocked, "reasons": lines}
    self_blocked, self_lines = gate.check(base, base, spec, base_spec)
    if self_blocked:
        raise RuntimeError("Valid baseline must pass against itself")
    flaky_blocked, flaky_lines = gate.check(flaky, base, spec, base_spec)
    if "pass_hat_5" not in flaky_blocked:
        raise RuntimeError("Reliability metric must independently block flaky_regression")
    reports = {"baseline": base, "fixed": fixed, "flaky_regression": flaky,
               "seeded_regression": json.loads(Path("reports/eval_seeded_regression_v2.json").read_text(encoding="utf-8")),
               "honest_refactor": json.loads(Path("reports/eval_honest_refactor_v2.json").read_text(encoding="utf-8")),
               "slice_regression": regression}
    evidence = {"generator": "python -m scripts.build_m6_m7_evidence", "scope": "local, not GitHub Actions",
                "source_sha12": {p: sha12(Path(p)) for p in ("lab9/stats.py", "lab9/eval.py", "lab9/gate.py",
                                      "lab9/integrity.py", "config/metric_spec_v2.yaml", "../.github/workflows/eval-gate.yml")},
                "eval_set_sha12": sha12(Path(spec["eval_set"])), "trusted_base_spec_commit": "6bbac68",
                "aa_initial": json.loads(Path("../docs/evidence/m6_aa.json").read_text(encoding="utf-8")),
                "aa_confirmation": json.loads(Path("../docs/evidence/m6_aa_confirmation.json").read_text(encoding="utf-8")),
                "reliability_floor": next(m["threshold"]["min"] for m in spec["metrics"] if m["id"] == "pass_hat_5"),
                "scorecard": scorecard, "public_trap_command": public_command, "public_traps": trap_results,
                "additional_probes": probe_results, "baseline_self_check": {"blocked": self_blocked, "lines": self_lines},
                "flaky_check": {"blocked": flaky_blocked, "lines": flaky_lines}, "reports": reports}
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT}: mutation 3/3, public traps 4/4, additional probes {len(probes)}/{len(probes)}")


if __name__ == "__main__":
    main()
