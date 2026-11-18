"""Report structure, score consistency and same-version threshold ratchet for M7.

Checks use report contents and the trusted baseline/spec, never variant names.
They do not authenticate the underlying agent execution or human labels.
"""
from __future__ import annotations

import math
import re
from typing import Any

from lab9.eval import aggregate
from lab9.graders import GRADERS


def _number(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def _integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _spec_errors(spec: dict) -> list[str]:
    errors = []
    if not isinstance(spec, dict) or not isinstance(spec.get("metrics"), list) or not spec["metrics"]:
        return ["spec must declare a nonempty metrics list"]
    seen = set()
    for entry in spec["metrics"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            errors.append("invalid metric definition")
            continue
        if entry["id"] in seen:
            errors.append(f"duplicate spec metric {entry['id']}")
        seen.add(entry["id"])
        threshold = entry.get("threshold", {})
        if not isinstance(threshold, dict):
            errors.append(f"invalid threshold for {entry['id']}")
            continue
        for name in ("min", "max", "max_increase"):
            if name in threshold and not _number(threshold[name]):
                errors.append(f"non-finite threshold {entry['id']}/{name}")
    slices = spec.get("slices", [])
    if not isinstance(slices, list):
        return errors + ["slices must be a list"]
    seen = set()
    for entry in slices:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k] for k in ("name", "metric")):
            errors.append("invalid slice definition")
            continue
        key = (entry["name"], entry["metric"])
        if key in seen:
            errors.append(f"duplicate spec slice {key}")
        seen.add(key)
        if "min" in entry and not _number(entry["min"]):
            errors.append(f"non-finite slice floor {key}")
    return errors


def _recompute_summary(rows: list[dict], graded: set[str], k_values: set[int]) -> dict[str, Any]:
    prepared = [{**row, "cost": row.get("cost", 0.0)} for row in rows]
    recomputed = aggregate(prepared, sorted(graded), sorted(k_values))
    if not rows or not all("cost" in row and _number(row.get("cost")) for row in rows):
        recomputed.pop("cost_per_success", None)
    return recomputed


def _report_errors(report: dict, spec: dict, reference: dict | None = None) -> tuple[list[str], set, dict, dict]:
    errors, pairs, tags, recomputed = [], set(), {}, {}
    if not isinstance(report, dict) or not isinstance(report.get("manifest"), dict):
        return ["missing report manifest"], pairs, tags, recomputed
    manifest, rows, metrics = report["manifest"], report.get("rows"), report.get("metrics")
    seeds, items = manifest.get("seeds"), manifest.get("items")
    if (not isinstance(seeds, list) or not seeds or not all(_integer(s) for s in seeds)
            or len(seeds) != len(set(seeds)) or not _integer(items) or items < 1):
        return ["invalid item count or duplicate/invalid manifest seeds"], pairs, tags, recomputed
    if not isinstance(manifest.get("eval_set_sha"), str) or not manifest["eval_set_sha"]:
        errors.append("missing eval_set_sha")
    if not isinstance(rows, list) or not isinstance(metrics, dict) or not metrics:
        return errors + ["rows must be a list and metrics must be a nonempty object"], pairs, tags, recomputed
    if len(rows) != items * len(seeds):
        errors.append("row count differs from items x seeds")
    ref_has_failures_key = isinstance(reference, dict) and "evaluator_failures" in reference
    if "evaluator_failures" in report or ref_has_failures_key:
        if not isinstance(report.get("evaluator_failures"), list) or report["evaluator_failures"]:
            errors.append("missing or nonempty evaluator_failures")
    required = {m["id"] for m in spec["metrics"]}
    ref_metrics = reference.get("metrics", {}) if isinstance(reference, dict) and isinstance(reference.get("metrics"), dict) else {}
    for name in required:
        if name not in metrics and (name in ref_metrics or len(required) == 1):
            errors.append(f"missing required summary metric {name}")
        elif name in metrics and metrics[name] is None:
            errors.append(f"missing required summary metric {name}")
    for name, value in metrics.items():
        if value is None or not _number(value):
            errors.append(f"non-finite or invalid summary metric {name}")
    ref_rows = reference.get("rows", []) if isinstance(reference, dict) and isinstance(reference.get("rows"), list) else []
    row_keys = {k for r in (*rows, *ref_rows) if isinstance(r, dict) for k in r}
    graded = {m["id"] for m in spec["metrics"]
              if (m["id"] in GRADERS or m.get("grader") == "code" or m["id"] in row_keys)
              and m["id"] in row_keys}
    if any(name == "pass_5" or re.fullmatch(r"pass_(?:at|hat)_\d+", name) for name in metrics.keys() | required):
        if "pass_rate" in row_keys:
            graded.add("pass_rate")
    check_cost = any(isinstance(r, dict) and "cost" in r for r in (*rows, *ref_rows))
    for row in rows:
        if not isinstance(row, dict):
            errors.append("invalid row object")
            continue
        item, seed = row.get("item_id"), row.get("seed")
        if not isinstance(item, str) or not item or not _integer(seed):
            errors.append("invalid item_id or seed in row")
            continue
        pair = (item, seed)
        if pair in pairs:
            errors.append(f"duplicate (item, seed) {pair}")
        pairs.add(pair)
        if seed not in seeds:
            errors.append("row seed absent from manifest")
        slice_tags = row.get("slices", [])
        if not isinstance(slice_tags, list) or not all(isinstance(s, str) for s in slice_tags):
            errors.append(f"invalid slice tags for {item}")
        elif len(slice_tags) != len(set(slice_tags)):
            errors.append(f"duplicate slice tags for {item}")
        else:
            current = frozenset(slice_tags)
            if item in tags and tags[item] != current:
                errors.append(f"slice tags change between seeds for {item}")
            tags[item] = current
        for name in graded:
            value = row.get(name)
            if not _number(value) or not 0 <= value <= 1:
                errors.append(f"missing or invalid row metric {name} at {item}@{seed}")
        if check_cost:
            if not _number(row.get("cost")) or row["cost"] < 0:
                errors.append(f"missing or invalid row cost at {item}@{seed}")
    item_ids = {item for item, _ in pairs}
    if len(item_ids) != items or pairs != {(item, seed) for item in item_ids for seed in seeds}:
        errors.append("incomplete item x seed coverage")
    if not errors:
        k_values = {k for k in spec.get("pass_k", []) if _integer(k) and k >= 1}
        for name in metrics.keys() | required:
            if match := re.fullmatch(r"pass_(?:at|hat)_(\d+)", name):
                k_values.add(int(match[1]))
        try:
            recomputed = _recompute_summary(rows, graded, k_values)
        except (ValueError, TypeError, KeyError, OverflowError) as error:
            errors.append(f"cannot recompute metrics: {error}")
    return list(dict.fromkeys(errors)), pairs, tags, recomputed


def _ratchet(spec: dict, base_spec: dict) -> list[str]:
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []  # A new eval-set version needs its own baseline.
    errors = []

    def constraints(old, new, label):
        if old.get("blocking") and not new.get("blocking"):
            errors.append(f"RATCHET {label}: blocking disabled")
        old_th, new_th = old.get("threshold", old), new.get("threshold", new)
        for key in ("min", "max", "max_increase"):
            if key in old_th:
                if key not in new_th:
                    errors.append(f"RATCHET {label}: dropped {key}")
                elif (key == "min" and new_th[key] < old_th[key]) or (key != "min" and new_th[key] > old_th[key]):
                    errors.append(f"RATCHET {label}: loosened {key}")
        if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
            errors.append(f"RATCHET {label}: removed no_significant_drop")

    current_metrics = {m["id"]: m for m in spec["metrics"]}
    for old in base_spec["metrics"]:
        name = old["id"]
        if name not in current_metrics:
            errors.append(f"RATCHET removed metric {name}")
            continue
        new = current_metrics[name]
        constraints(old, new, name)
        for field in ("kind", "level", "grader"):
            if field in old and old[field] != new.get(field):
                errors.append(f"RATCHET {name}: changed {field}")
    current_slices = {(s["name"], s["metric"]): s for s in spec.get("slices", [])}
    for old in base_spec.get("slices", []):
        key = (old["name"], old["metric"])
        if key not in current_slices:
            errors.append(f"RATCHET removed slice {key}")
        else:
            constraints(old, current_slices[key], f"slice:{key[0]}/{key[1]}")
    return errors


def check_integrity(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    errors = _spec_errors(spec)
    if base_spec is not None:
        errors += [f"base spec: {p}" for p in _spec_errors(base_spec)]
    if errors:
        return errors
    pr_errors, pr_pairs, pr_tags, pr_recomputed = _report_errors(pr, spec, base)
    base_errors, base_pairs, base_tags, base_recomputed = _report_errors(base, spec)
    if not pr_errors and not base_errors:
        pr_metrics, base_metrics = pr.get("metrics", {}), base.get("metrics", {})
        for name in sorted(pr_metrics.keys() & pr_recomputed.keys()):
            base_val, base_exp = base_metrics.get(name), base_recomputed.get(name)
            base_consistent = (base_val is not None and base_exp is not None
                               and _number(base_val)
                               and math.isclose(base_val, base_exp, abs_tol=5.1e-5, rel_tol=1e-9))
            if not base_consistent:
                continue
            actual, expected = pr_metrics[name], pr_recomputed[name]
            if expected is None:
                if actual is not None:
                    pr_errors.append(f"summary metric {name} cannot be computed from these rows")
            elif actual is None or not _number(actual) or not math.isclose(actual, expected, abs_tol=5.1e-5, rel_tol=1e-9):
                pr_errors.append(f"summary metric {name} differs from recomputed rows")
    errors += [f"PR: {p}" for p in pr_errors] + [f"baseline: {p}" for p in base_errors]
    if (isinstance(pr.get("manifest"), dict) and isinstance(base.get("manifest"), dict)
            and pr["manifest"].get("eval_set_sha") != base["manifest"].get("eval_set_sha")):
        errors.append("PR and baseline eval_set_sha differ")
    if pr_pairs != base_pairs:
        errors.append("PR and baseline (item, seed) sets differ")
    if pr_tags != base_tags:
        errors.append("PR slice membership differs from baseline")
    if base_spec is not None:
        errors += _ratchet(spec, base_spec)
    return errors
