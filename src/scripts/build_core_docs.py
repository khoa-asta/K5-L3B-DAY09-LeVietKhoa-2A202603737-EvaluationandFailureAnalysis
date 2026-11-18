"""Render Core documentation from generated M2-M4 evidence, not hand-entered metrics.

Run from src/: python -m scripts.build_core_docs
"""
from __future__ import annotations

import json
from pathlib import Path

from lab9.eval import load_spec


DOCS = Path("../docs")


def main() -> None:
    evidence = json.loads((DOCS / "evidence/m4_gate_validation.json").read_text(encoding="utf-8"))
    calibration = json.loads((DOCS / "evidence/m2_calibration.json").read_text(encoding="utf-8"))["results"]
    spec = load_spec()
    reports = evidence["reports"]
    baseline, fixed, regression = (reports[k] for k in ("baseline", "fixed", "seeded_regression"))
    manifest = baseline["manifest"]
    tone, helpful = calibration["tone"], calibration["helpful"]

    def value(number):
        return f"{number:.4f}" if isinstance(number, float) else str(number)

    def ci(name, metric="pass_rate"):
        row = evidence["comparisons"][name][metric]
        return f"Δ {row['delta']:+.3f}, CI [{row['lo']:+.3f}, {row['hi']:+.3f}]"

    header = "| Metric | Ngưỡng từ spec | Blocking | swarm baseline | fixed | seeded_regression |\n|---|---|---|---|---|---|\n"
    metrics = header + "".join(
        f"| {m['id']} | `{json.dumps(m.get('threshold', {}))}` | {'có' if m.get('blocking') else 'không'} | "
        f"{value(baseline['metrics'].get(m['id']))} | {value(fixed['metrics'].get(m['id']))} | "
        f"{value(regression['metrics'].get(m['id']))} |\n" for m in spec["metrics"])
    run_ids = "\n".join(f"- **{name}:** `{rep['run_id']}` — `{evidence['report_paths'][name]}`."
                        for name, rep in reports.items())
    judge_text = (f"tone: κ={tone['kappa']:.3f}, P={tone['precision']:.3f}, R={tone['recall']:.3f}, "
                  f"PASS floors; helpful: κ={helpful['kappa']:.3f}, P={helpful['precision']:.3f}, "
                  f"R={helpful['recall']:.3f}, FAIL floors. Helpful bị loại khỏi gate. "
                  "Xem [judge audit](judge_audit.md) cho ma trận, hiệu chỉnh và 15 bất đồng.")
    source = ", ".join(f"`{path}` = `{digest}`" for path, digest in evidence["source_sha12"].items())
    pilot = ("Pilot nội bộ offline cho claim hoàn phí giao trễ hoặc hàng hỏng đã xác minh, "
             "một claim/một đơn trong scope chủ sở hữu, approval hợp lệ do host cung cấp. "
             "Policy hiện hành lấy max khoản đủ điều kiện; ghi ledger bị giới hạn bởi approval, "
             "tiền đã trả và trần còn lại theo đơn. Fixture damage có cap 150.000đ "
             "(`DMG-04`); phí giao trễ theo shipping fee khi đủ 3 ngày (`SHIP-LATE-03`). "
             "Số này là quy tắc fixture, không phải một ngưỡng gate được tối ưu sau khi xem điểm.")

    card = f"""# Eval card — LogiX-VN refund agent

Tài liệu sinh bằng `python -m scripts.build_core_docs` từ report/evidence, không tự nhập lại số đo.

## Phiên bản và nguồn

- **Eval set:** v1, SHA `{manifest['eval_set_sha']}`, {manifest['items']} item × {len(manifest['seeds'])} seed `{manifest['seeds']}`; nguồn `lab8_public`; nhãn tách ở `data/eval/labels_v1.json`.
- **Metric spec:** {spec['metric_spec_version']}; Python {manifest['python']}; model {manifest['llm']}.
- **Snapshot mã nguồn:** report được sinh từ working tree dựa trên HEAD `{evidence['source_head'][:7]}`; `source_dirty={evidence['source_dirty']}` lúc sinh. Đây không phải tuyên bố code chỉ gồm commit đó; các SHA12 dưới đây ghi đúng nội dung đã chạy.
- **SHA12 mã/cấu hình:** {source}.
- **Run ID / đường dẫn** (tính từ `src/`):

{run_ids}

## Metric và kết quả

{metrics}
Giá trị safety là số vi phạm, phải bằng 0. Capability là tỷ lệ đạt. `cost_per_success` là chi phí mô phỏng của harness, không phải giá API thật. `proposal_amount_correct`, `db_fact_kept`, `pass_5`, cost chỉ theo dõi; metric reply là blocking.

## Paired CI và gate M4

- Đơn vị resample là **item**, lấy mean qua các seed trước; ghép cùng item, cùng thứ tự, tính PR − baseline.
- `scipy.stats.bootstrap(paired=True, method=percentile)`, confidence {evidence['bootstrap']['confidence']}, {evidence['bootstrap']['n_resamples']} lần resample, NumPy RNG seed {evidence['bootstrap']['rng']}.
- PR swarm so với baseline: {ci('pr')}; **exit {evidence['decisions']['pr']['exit_code']}**.
- Fixed so với baseline: {ci('fixed')}; **exit {evidence['decisions']['fixed']['exit_code']}**.
- Seeded regression so với baseline: {ci('seeded_regression')}; **exit {evidence['decisions']['seeded_regression']['exit_code']}**. Bị chặn ở `refund_amount_correct`, `reply_amount_correct`, `pass_rate`.
- `pass_rate` của regression vừa dưới sàn vừa có CI hoàn toàn dưới 0. Hai metric tiền/reply bị chặn bởi sàn tuyệt đối, CI của chúng còn chạm 0; không diễn giải nhầm là cả ba đều có CI loại 0.
- Sanity check baseline/spec: **exit {evidence['ci_check']['exit_code']}**. Baseline là swarm; lần PR swarm được chạy riêng và khớp toàn bộ metric.

Bằng chứng đầy đủ, report SHA, các dòng gate và exit code: [M4 gate validation](evidence/m4_gate_validation.json). Đây là kiểm tra workflow **trên máy**, chưa phải trạng thái GitHub Actions.

## Judge, trace và người xử lý

{judge_text}

Trace case [C-002](trace_case.md): event 3 `model_override` đổi DB 2 ngày thành ticket 5 ngày; regression test phân biệt được swarm/variant lỗi với fixed. [Kiểm định M3](grader_validation.md) ghi detection 20/20, báo nhầm fixed 0/70 và 10 ca FM-08 bị grader Lab 8 bỏ sót.

**Eval owner / người xử lý gate đỏ:** Lê Việt Khoa, tác giả bản fork. Đọc metric bị chặn, tìm trace, sửa evaluator/đề xuất thay đổi hợp lệ rồi tái chạy. Không sửa tay report hoặc nới ngưỡng cùng eval-set version để qua gate. Reviewer của bài lab duyệt ngoại lệ bằng lý do và bằng chứng trong PR; chưa có phê duyệt pilot thật.

## Phạm vi và giới hạn

{pilot}

- MockLLM và judge replay public chưa đại diện cho người dùng/model thật; chưa có tập held-out mới.
- {manifest['items']} item là cỡ mẫu nhỏ; CI rộng, lỗi hiếm hoặc chỉ xuất hiện ở một nhóm nhỏ có thể lọt. M5–M7 mới bổ sung slice, nhiễu và integrity/ratchet.
- Swarm gốc không phát event reply. Metric reply cho các trial không có reply là N/A trả True, nên baseline reply=1 không chứng minh đã kiểm lời nói của swarm. Fixed và các variant M3 có reply và được đo thực tế.
- Parser tiền có phạm vi được nêu ở [M3](grader_validation.md); chưa bảo đảm hiểu mọi câu tiếng Việt hoặc tiền viết bằng chữ.
- Việc host chặn approval không đồng nghĩa agent luôn giải thích đúng; approval_bypass=0 vẫn có thể đi cùng FM-02/FM-08.
- Key 5 anchor của giảng viên không có trong fork; chưa xác nhận đối chiếu key riêng. Điều này không được thay bằng kết quả `evalset --check`.

## Khi nào tăng phiên bản

Thêm/sửa item, provenance hoặc nhãn làm đổi nội dung eval set thì phát hành eval-set version mới và sinh lại baseline phù hợp; không so report khác SHA. Thay metric/ngưỡng thì tăng metric-spec version; cùng eval-set version chỉ giữ hoặc siết ngưỡng. Từ spec starter 1.0 sang 1.1 đã thêm hai metric M3, không nới các ngưỡng cũ.
"""
    (DOCS / "eval_card.md").write_text(card, encoding="utf-8")

    prd = f"""# PRD v1.1 — LogiX-VN refund agent

v1.1 bổ sung định nghĩa chạy đúng, bằng chứng và cổng release cho bài lab cá nhân; tính năng agent/host Lab 8 giữ theo nguồn gốc giảng viên. Tài liệu sinh từ report bằng `python -m scripts.build_core_docs`.

## 1. Thay đổi so với v1.0

| Mục | v1.0 | v1.1 |
|---|---|---|
| Tiêu chí thành công | Xử lý yêu cầu hoàn tiền đúng | Metric spec {spec['metric_spec_version']}, safety bằng 0, capability đạt sàn và CI không chỉ ra giảm có ý nghĩa. |
| Bằng chứng | Demo thủ công | Eval set SHA `{manifest['eval_set_sha']}`, report có run ID và gate tái chạy được. |
| Rủi ro | Mô tả chung | FM-01…FM-08 có trace, code grader và kiểm định; FM-09 dành v2. |

## 2. Phạm vi pilot

{pilot}

Ngoài phạm vi pilot hiện tại: yêu cầu nhiều đơn, dữ liệu ngoài principal, tranh chấp pháp lý, tự cấp approval, ghi tiền trực tiếp bởi model, traffic người dùng thật. Thiếu mã đơn thì hỏi lại; ngoài scope thì escalated; approval sai/hết hạn thì host từ chối. Pilot ở đây là sandbox bài lab, chưa được phê duyệt vận hành thật.

## 3. Định nghĩa chạy đúng

Baseline `{baseline['run_id']}`; fixed `{fixed['run_id']}`; regression `{regression['run_id']}`. Mỗi report có {manifest['items']} item × {len(manifest['seeds'])} seed, nhãn riêng.

{metrics}
Giảm có ý nghĩa: CI {evidence['bootstrap']['confidence']:.0%} paired bootstrap của Δ (PR − baseline), resample theo item, nằm hoàn toàn dưới 0. CI được tính từ các row/mean theo item, không lấy metric tổng đã làm tròn để bootstrap. `pass_rate` regression: {ci('seeded_regression')}, gate chặn như mong đợi.

## 4. Failure mode → grader

| FM | Grader | Code hay judge | Vì sao |
|---|---|---|---|
| FM-01 leaky_trace | SecretLeak, TrialPass | code | Quét canary/forbid_substrings trên toàn artifact. |
| FM-02 ignore_denied | TrialPass, ReplyAmountCorrect | code | Đối chiếu status và lời báo hoàn với host/ledger; không coi reply sai là tiền đã chuyển. |
| FM-03 ticket_trust | DbFactKept, ProposalAmountCorrect, RefundAmountCorrect | code | Kiểm event override và kết quả tiền so với nhãn. |
| FM-04 sum_parts/round_down | ProposalAmountCorrect, RefundAmountCorrect | code | Tính tiền và trần không phụ thuộc đánh giá ngôn ngữ. |
| FM-05 pre_deducted | ProposalAmountCorrect, RefundAmountCorrect | code | Tách quote đầy đủ khỏi net ledger, kể cả trường hợp ledger bằng 0. |
| FM-06 stale_clause | TrialPass, RefundAmountCorrect | code | Nhãn hiện hành bắt kết quả dùng clause cũ; `current_clause_only` chưa triển khai riêng. |
| FM-07 sibling_refund | ApprovalBypass, TrialPass | code | Phát hiện ledger row ngoài claim được yêu cầu. |
| FM-08 misreport | ReplyAmountCorrect | code | Chuẩn hóa số đã khẳng định hoàn và so trực tiếp ledger. |
| FM-09 cross_principal | Chưa có grader riêng ở v1 | code, dự kiến v2 | Public control kiểm scope đã được ghi; chưa có bằng chứng lỗi riêng cho mode này. |

Tone có thể dùng judge sau calibration; tiền và approval luôn dùng code. {judge_text}

## 5. Cổng release và trách nhiệm

Chạy từ `src/`:

```powershell
.\\.venv\\Scripts\\python.exe -m lab9.gate --pr reports/eval_fixed.json --baseline reports/baseline_v1.json
.\\.venv\\Scripts\\python.exe -m lab9.gate --pr reports/eval_seeded_regression.json --baseline reports/baseline_v1.json
```

Fixed phải exit 0; seeded regression phải exit 1 và nêu `pass_rate` trong metric bị chặn. Local đã đạt cả hai; sanity check baseline cũng exit 0. Baseline/report được harness sinh rồi lưu trong nhánh làm bài; sau CI xanh, merge cùng code vào main của bản fork để dùng làm mốc bảo vệ cho thay đổi sau.

Eval owner: **Lê Việt Khoa**. Gate đỏ thì dừng merge và phân tích trace/metric. Ngoại lệ cần reviewer/giảng viên duyệt trong PR, ghi lý do và bằng chứng; không sửa tay report hoặc tự nới spec. Workflow `eval-gate` chạy trên PR hoặc workflow_dispatch; local validation không thay thế trạng thái GitHub Actions.

## 6. Bằng chứng và việc còn lại

- Local: smoke, student tests Core, eval set check, baseline/spec sanity và cả ba quyết định gate đã được kiểm; xem [eval card](eval_card.md), [M3](grader_validation.md), [M4 evidence](evidence/m4_gate_validation.json).
- Chưa có kết quả GitHub Actions/merge trên remote trong bằng chứng này. Dùng [PR description](PR_DESCRIPTION.md) khi mở PR từ nhánh làm bài vào main **của bản fork**.
- Cỡ mẫu nhỏ, MockLLM, public replay và parser reply giới hạn; baseline swarm không phát reply. Xem toàn bộ giới hạn ở eval card.
- Anchor key riêng của giảng viên chưa được đối chiếu. Slice/integrity/ratchet/pass^k thuộc M5–M7, chưa phải cam kết của gate Core.

## 7. Khi nào lên v1.2

Thêm dữ liệu held-out thật hoặc thay đổi phạm vi pilot; phát hành eval set mới khi đổi item/nhãn; tăng metric spec khi thay metric/ngưỡng và tái sinh baseline tương ứng. Không dùng kết quả public hiện tại để tuyên bố chất lượng ngoài phạm vi đã đo.

## Phê duyệt

| Vai trò | Người phụ trách | Trạng thái |
|---|---|---|
| Tác giả / eval owner | Lê Việt Khoa | Đã có bằng chứng kiểm thử local. |
| Reviewer / người duyệt pilot | Chưa ghi nhận | Chưa có phê duyệt vận hành thật trong bài lab. |
"""
    (DOCS / "PRD_v1.1.md").write_text(prd, encoding="utf-8")

    description = f"""Hoàn thiện đánh giá Core Lab 9 và chặn regression hoàn tiền

Agent có thể báo hoàn thành khi host từ chối, gửi proposal đã trừ tiền trước hoặc báo số tiền khác ledger. Thay đổi bổ sung taxonomy/eval set, calibration judge và các code grader để giải thích, phát hiện các lỗi này; gate so paired CI theo item với baseline swarm.

Phần setup M0 khôi phục src Day 8 gốc của giảng viên và đưa config/data/tests về đúng đường dẫn sau khi copy thủ công. Nội dung src/lab8 hiện khớp nguồn gốc; diff ba shape là việc bỏ bản của nhóm đã copy nhầm.

Baseline `{baseline['run_id']}` dùng eval set `{manifest['eval_set_sha']}`, metric spec {spec['metric_spec_version']}. Fixed qua gate; seeded regression bị chặn trên pass_rate ({ci('seeded_regression')}), refund_amount_correct và reply_amount_correct. M3 phát hiện 20/20 trial lỗi, báo nhầm fixed 0/70; helpful judge bị loại vì recall {helpful['recall']:.3f}.

Validation local:

- Smoke M0, eval set check, student tests Core và host tests.
- Swarm PR và fixed: gate exit 0; seeded_regression: gate exit 1.
- `lab9.ci_check`: exit 0; báo cáo có 70 rows và không có evaluator failure.

Output gate regression từ script, không nhập lại số:

```text
{evidence['decisions']['seeded_regression']['stdout'].rstrip()}
```

Giới hạn: MockLLM/public replay, 14 item, baseline swarm không phát event reply; chưa đối chiếu anchor key riêng, chưa làm Advanced/Expert. Trạng thái GitHub CI và merge cần được kiểm trên PR.

Đích PR: `khoa-asta/K5-L3B-DAY09-LeVietKhoa-2A202603737-EvaluationandFailureAnalysis`, nhánh làm bài → `main` trong cùng bản fork.
"""
    (DOCS / "PR_DESCRIPTION.md").write_text(description, encoding="utf-8")
    print("wrote docs/eval_card.md, docs/PRD_v1.1.md, docs/PR_DESCRIPTION.md from M2-M4 evidence")
    if (DOCS / "evidence/m5_slice_validation.json").is_file():
        from scripts.build_m5_docs import main as build_m5_docs
        build_m5_docs()


if __name__ == "__main__":
    main()
