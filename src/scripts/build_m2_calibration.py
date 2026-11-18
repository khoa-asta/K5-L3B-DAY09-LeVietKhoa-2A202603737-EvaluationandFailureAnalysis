"""Save M2 replay calibration evidence without changing any public CSV labels.

Run from src/: python -m scripts.build_m2_calibration
"""
from __future__ import annotations

import json
from pathlib import Path

from lab9.evalset import sha12
from lab9.judge import FLOORS, calibrate


OUTPUT = Path("../docs/evidence/m2_calibration.json")


def main() -> None:
    results = {}
    for name in ("tone", "helpful"):
        source = Path(f"data/eval/judge_{name}_public.csv")
        result = calibrate(source)
        cm = result["confusion"]
        results[name] = {
            "source": str(source.as_posix()),
            "source_sha12": sha12(source),
            "sensitivity": cm["tp"] / (cm["tp"] + cm["fn"]),
            "specificity": cm["tn"] / (cm["tn"] + cm["fp"]),
            "human_fail_rate": (cm["tp"] + cm["fn"]) / result["n"],
            **result,
        }
    evidence = {
        "generator": "python -m scripts.build_m2_calibration",
        "backend": "replay; public CSV labels unchanged",
        "positive_class": "FAIL",
        "floors": FLOORS,
        "stats_sha12": sha12(Path("lab9/stats.py")),
        "judge_sha12": sha12(Path("lab9/judge.py")),
        "results": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(f"wrote {OUTPUT}: tone={'PASS' if results['tone']['passed'] else 'FAIL'}, "
          f"helpful={'PASS' if results['helpful']['passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
