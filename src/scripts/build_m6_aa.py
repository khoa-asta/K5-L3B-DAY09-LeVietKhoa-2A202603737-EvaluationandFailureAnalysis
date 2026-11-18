"""Record the official A/A command before choosing the M6 reliability floor."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path

from lab9.eval import load_spec
from lab9.evalset import sha12
from lab9.mutation import main as mutation_main


def main():
    spec = Path("config/metric_spec_v2.yaml")
    stream = StringIO()
    with redirect_stdout(stream):
        code = mutation_main(["--spec", str(spec), "--aa", "66,77,88,99,110"])
    output = stream.getvalue()
    print(output, end="")
    if code:
        raise RuntimeError("A/A command failed")
    metrics = {}
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) == 4:
            metrics[parts[0]] = dict(zip(("baseline", "alternate", "delta"), map(float, parts[1:])))
    if not metrics or any(abs(row["delta"]) > 1e-12 for row in metrics.values()):
        raise RuntimeError("Review the observed nonzero noise before selecting a floor")
    confirmation = any(m["id"] == "pass_hat_5" for m in load_spec(spec)["metrics"])
    result = {"generator": "python -m scripts.build_m6_aa", "exit_code": code, "stdout": output,
              "spec_sha12_at_measurement": sha12(spec), "stats_sha12": sha12(Path("lab9/stats.py")),
              "eval_set_sha12": sha12(Path(load_spec(spec)["eval_set"])),
              "seeds": load_spec(spec)["seeds"], "alternate_seeds": [66,77,88,99,110], "metrics": metrics,
              "phase": "confirmation after adding the floor" if confirmation else "measurement before adding the floor",
              "note": "Noise comparison, not a gate with mismatched seeds. Initial measurement and final confirmation are kept separately."}
    path = Path("../docs/evidence/m6_aa_confirmation.json" if confirmation else "../docs/evidence/m6_aa.json")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
