"""Render M5 documentation from the generated v2 experiment evidence."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

import yaml

from lab9 import stats
from lab9.eval import per_item
from lab9.evalset import ITEMS_V2, load_jsonl


DOCS = Path("../docs")
HEADING = "\n## M5 — Eval set v2 và slice gate\n"


def main() -> None:
    evidence = json.loads((DOCS / "evidence/m5_slice_validation.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load(Path("config/metric_spec_v2.yaml").read_text(encoding="utf-8"))
    mapping = yaml.safe_load(Path("config/fm_map.yaml").read_text(encoding="utf-8"))
    reports, values = evidence["reports"], evidence["slice_values"]
    candidate = per_item(reports["slice_regression"], "pass_rate")
    baseline = per_item(reports["baseline"], "pass_rate")
    keys = sorted(baseline)
    delta, lo, hi = stats.paired_bootstrap([candidate[k] for k in keys], [baseline[k] for k in keys],
                                         n_resamples=spec["bootstrap"]["n_resamples"],
                                         rng=spec["bootstrap"]["rng"], confidence=spec["bootstrap"]["confidence"])
    items = load_jsonl(ITEMS_V2)
    adversarial = Counter(fm for it in items if it["split"] == "adversarial" for fm in it["failure_modes"])
    counts = "\n".join(f"| {fm} | {count} | {adversarial[fm]} |" for fm, count in evidence["fm_counts"].items())
    table = "\n".join(
        f"| {name} | `{report['run_id']}` | {report['metrics']['pass_rate']:.4f} | "
        f"{values[name]['money_movement']:.4f} | {values[name]['adversarial']:.4f} | "
        f"{evidence['decisions'][name]['exit_code']} |" for name, report in reports.items())
    summary = f"""{HEADING}
Eval set v2 SHA `{evidence['eval_set_sha12']}` có {len(items)} item ({len(items) - evidence['slice_counts']['adversarial']} regression + {evidence['slice_counts']['adversarial']} adversarial), chạy {len(spec['seeds'])} seed/item, metric spec {spec['metric_spec_version']}. Chi tiết và trace: [M5 validation](m5_evalset_and_slices.md).

| Shape | Run ID | pass_rate toàn bộ | money_movement | adversarial | Gate exit |
|---|---|---|---|---|---|
{table}

Global pass_rate của slice_regression có Δ {delta:+.3f}, CI [{lo:+.3f}, {hi:+.3f}], vẫn qua sàn {next(m['threshold']['min'] for m in spec['metrics'] if m['id']=='pass_rate')}; CI còn chứa 0. Slice money_movement có {evidence['slice_counts']['money_movement']} item, đạt {values['slice_regression']['money_movement']:.2f} < sàn 0.90 nên chặn. Bỏ slices khỏi cùng spec thì gate cho qua; giữ slices thì chỉ `slice:money_movement/pass_rate` bị chặn. Fixed và honest_refactor đều qua.

Bằng chứng mới tách riêng tại [m5_slice_validation.json](evidence/m5_slice_validation.json); các report và eval set v1 giữ nguyên. Phần M6 (pass@k/pass^k, A/A) và M7 (integrity/ratchet, mutation scorecard, traps) được trình bày tiếp ở mục M6–M7 và [m6_m7_reliability_and_integrity.md](m6_m7_reliability_and_integrity.md).
"""
    text = f"""# M5 — Eval set v2 và kiểm tra theo slice

Tài liệu sinh bằng `python -m scripts.build_m5_docs` từ [bằng chứng chạy thực tế](evidence/m5_slice_validation.json). Báo cáo được `lab9.eval` sinh; không sửa tay agent, fixture, adversarial pack, nhãn hay supplied variant.

## Eval set và ánh xạ

- {len(items)} item, {len(items)} nhãn riêng, eval set SHA `{evidence['eval_set_sha12']}`; v2 giữ toàn bộ v1 và thêm nguyên pack adversarial.
- Cơ chế tấn công → mã taxonomy: `{json.dumps(mapping, ensure_ascii=False)}`.
- Mỗi FM mà adversarial pack tấn công có ít nhất 3 item trong v2; đếm item, không đếm lại theo seed. FM-01 được giữ từ v1, không phải cơ chế mới trong pack.

| FM | Tổng item v2 | Trong adversarial |
|---|---|---|
{counts}

Slice được dựng từ nhãn, không dựa vào kết quả agent: `money_movement` khi nhãn refund > 0; `denial`/`escalation` theo status nhãn; `adversarial` theo nguồn pack. Số item: `{evidence['slice_counts']}`. Các item adversarial giữ provenance instructor/attack và được replay trên fixed trong thí nghiệm này.

## Gate theo slice

Spec {spec['metric_spec_version']} thêm money_movement và adversarial; cùng denial đã có, cả ba dùng pass_rate, min 0.90 và `no_significant_drop=true`, blocking. Giữ nguyên các sàn toàn cục của starter v2, không chỉnh theo kết quả để ép qua/chặn. Spec v1 và baseline v1 giữ nguyên.

`slice_check` lấy mean qua seed cho từng item rồi mean các item; paired bootstrap ghép theo item ID, dùng confidence/RNG/resample trong spec. Một slice không được lấy điểm tổng để thay thế. Slice bắt buộc thiếu/rỗng, metric thiếu/NaN/inf, coverage item không khớp hoặc CI không tính được đều có lý do và bị chặn; slice không blocking chỉ cảnh báo. Các kiểm tra này phối hợp với `integrity_check` toàn report ở M7.

{summary.split(HEADING, 1)[1]}

## Trace đối chiếu và FM-09

- `slice_regression C-105@11`: event 3 quote đúng 150.000đ, event 4 proposal thành 180.000đ do cộng clause, host ghi 150.000đ thay vì nhãn 120.000đ. Đối chứng fixed truyền quote 150.000đ, host ghi đúng 120.000đ.
- Lỗi sum_parts xuất hiện ở C-014/C-105/C-106 trên các seed lẻ 11/33/55: 9 trial fail trong 140 trial; trong slice chuyển tiền là 9/60, làm tỷ lệ còn 0.85. Đây là lỗi tập trung trong nhóm cần bảo vệ, dù global còn 0.9357.
- `fixed C-110/C-113/C-114@11`: event 2 `investigator.lookup_order` đều có `visible=false`, `reason=outside_principal_scope`; event 3 trả escalated, ledger 0, Lab 8 PASS. Đây là bằng chứng **tấn công FM-09 bị chặn**, không phải khẳng định đã quan sát một vụ rò dữ liệu giữa principal. Không tạo agent vượt quyền giả để làm đẹp taxonomy.
- Bundle còn có trace riêng cho ticket_over_db, stale_policy, double_deduct, denied_ignored, sibling_refund và reply_ledger_mismatch; mapping và bước sai đầu tiên được bổ sung ở [taxonomy](failure_taxonomy.md).

## Tái tạo

Chạy trong `src/`:

```powershell
.\\.venv\\Scripts\\python.exe -m lab9.evalset --v2 --build
.\\.venv\\Scripts\\python.exe -m lab9.evalset --v2 --check
.\\.venv\\Scripts\\python.exe -m pytest -q -m student -o addopts= tests/test_lab9_advanced.py tests/test_lab9_advanced_slices.py -k slice
.\\.venv\\Scripts\\python.exe -m scripts.build_m5_evidence
.\\.venv\\Scripts\\python.exe -m scripts.build_m5_docs
```

Builder evidence dừng với lỗi nếu aggregate gate đã chặn regression, slice nào khác money_movement chặn nó, hoặc baseline/fixed/honest_refactor không qua. Xem tiếp [M6–M7 validation](m6_m7_reliability_and_integrity.md) cho kiểm định `pass@k`/`pass^k`, nhiễu A/A và `integrity_check`.
"""
    (DOCS / "m5_evalset_and_slices.md").write_text(text, encoding="utf-8")
    for name in ("eval_card.md", "PRD_v1.1.md"):
        path = DOCS / name
        core = path.read_text(encoding="utf-8").split(HEADING, 1)[0].rstrip()
        path.write_text(core + "\n" + summary, encoding="utf-8")
    path = DOCS / "PR_DESCRIPTION.md"
    description = path.read_text(encoding="utf-8").split(HEADING, 1)[0].rstrip()
    description = description.replace("chưa làm Advanced/Expert", "đã hoàn thành M5–M7 local")
    path.write_text(description + "\n" + summary, encoding="utf-8")
    print("wrote docs/m5_evalset_and_slices.md and M5 addenda in eval card, PRD, PR description")
    if (DOCS / "evidence/m6_m7_validation.json").is_file():
        from scripts.build_m6_m7_docs import main as build_m6_m7_docs
        build_m6_m7_docs()


if __name__ == "__main__":
    main()
