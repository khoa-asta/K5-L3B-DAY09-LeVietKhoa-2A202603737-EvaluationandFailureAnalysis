"""Replay M1 examples without changing the agent, fixtures, variants or graders.

Run from src/: python -m scripts.build_m1_evidence
The JSON bundle preserves events even when ignored traces/ files are not committed.
These injected examples explain the taxonomy; they are not a measured baseline.
"""
from __future__ import annotations

import json
from pathlib import Path
import platform
import tempfile

from lab8.db import load_json, load_jsonl
from lab8.shapes import SHAPES
from lab9 import variants
from lab9.eval import make_task
from lab9.evalset import sha12
from lab9.variant_agent import make_shape


OUTPUT = Path("../docs/evidence/m1_traces.json")
BUG_CASES = {
    "leaky_trace": [f"C-{i:03}" for i in range(1, 15)],
    "ignore_denied": ["C-007"],
    "ticket_trust": ["C-002"],
    "sum_parts": ["C-014"],
    "round_down": ["C-001"],
    "pre_deducted": ["C-008", "C-013", "C-014"],
    "stale_clause": ["C-006"],
    "sibling_refund": ["C-001", "C-010", "C-011", "C-012"],
    "misreport": ["C-008", "C-014"],
}


def main() -> None:
    variants.register()
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    world = load_json(Path("data/public_world_state.json"))
    labels = load_json(Path("data/eval/labels_v1.json"))
    trials = {}
    jobs = [("fixed", c["claim_id"], 11) for c in claims]
    jobs += [("swarm", "C-002", 55)]
    jobs += [("seeded_regression", c, 11)
             for c in ("C-002", "C-007", "C-008", "C-013", "C-014")]
    for bug, claim_ids in BUG_CASES.items():
        shape = f"m1_{bug}"
        # Registration is local to this process. The supplied source stays intact.
        SHAPES[shape] = make_shape(shape, {"no_override", bug})
        jobs += [(shape, c, 11) for c in claim_ids]

    with tempfile.TemporaryDirectory(prefix="lab9-m1-", ignore_cleanup_errors=True) as tmp:
        for shape, claim_id, seed in jobs:
            trial = make_task(shape, world, claims, labels, Path(tmp))(
                {"claim_id": claim_id, "seed": seed})
            run_id = trial["result"]["run_id"]
            trial["forbidden_hits"] = [
                token for token in labels[claim_id].get("forbid_substrings", [])
                if token and token in trial["blob"]
            ]
            del trial["blob"]  # Events and result already preserve the scanned content.
            if shape == "fixed" and not trial["lab8_pass"]:
                raise RuntimeError(f"Control failed: {run_id}: {trial['lab8_reason']}")
            trials[run_id] = trial

    bundle = {
        "generator": "python -m scripts.build_m1_evidence",
        "python": platform.python_version(),
        "source_sha12": sha12(Path("data/public_claims.jsonl")),
        "world_sha12": sha12(Path("data/public_world_state.json")),
        "labels_path": "src/data/eval/labels_v1.json",
        "labels_sha12": sha12(Path("data/eval/labels_v1.json")),
        "event_numbering": "1-based index in each trial.events list",
        "note": "Synthetic canary values are from public fixtures. No live LLM or API key.",
        "trials": trials,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}: {len(trials)} trials; 14/14 fixed controls PASS")


if __name__ == "__main__":
    main()
