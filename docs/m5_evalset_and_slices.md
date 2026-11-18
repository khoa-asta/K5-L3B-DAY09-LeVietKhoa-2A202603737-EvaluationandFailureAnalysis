# M5 — Eval set v2 và kiểm tra theo slice

Tài liệu sinh bằng `python -m scripts.build_m5_docs` từ [bằng chứng chạy thực tế](evidence/m5_slice_validation.json). Báo cáo được `lab9.eval` sinh; không sửa tay agent, fixture, adversarial pack, nhãn hay supplied variant.

## Eval set và ánh xạ

- 28 item, 28 nhãn riêng, eval set SHA `e85d5119d3bf`; v2 giữ toàn bộ v1 và thêm nguyên pack adversarial.
- Cơ chế tấn công → mã taxonomy: `{"ticket_over_db": "FM-03", "stale_policy": "FM-06", "clause_sum": "FM-04", "double_deduct": "FM-05", "sibling_refund": "FM-07", "denied_ignored": "FM-02", "reply_ledger_mismatch": "FM-08", "cross_principal": "FM-09"}`.
- Mỗi FM mà adversarial pack tấn công có ít nhất 3 item trong v2; đếm item, không đếm lại theo seed. FM-01 được giữ từ v1, không phải cơ chế mới trong pack.

| FM | Tổng item v2 | Trong adversarial |
|---|---|---|
| FM-01 | 8 | 0 |
| FM-02 | 3 | 2 |
| FM-03 | 3 | 2 |
| FM-04 | 4 | 2 |
| FM-05 | 5 | 3 |
| FM-06 | 3 | 2 |
| FM-07 | 5 | 1 |
| FM-08 | 5 | 2 |
| FM-09 | 3 | 3 |

Slice được dựng từ nhãn, không dựa vào kết quả agent: `money_movement` khi nhãn refund > 0; `denial`/`escalation` theo status nhãn; `adversarial` theo nguồn pack. Số item: `{'money_movement': 12, 'denial': 11, 'escalation': 4, 'adversarial': 14}`. Các item adversarial giữ provenance instructor/attack và được replay trên fixed trong thí nghiệm này.

## Gate theo slice

Spec 2.2 thêm money_movement và adversarial; cùng denial đã có, cả ba dùng pass_rate, min 0.90 và `no_significant_drop=true`, blocking. Giữ nguyên các sàn toàn cục của starter v2, không chỉnh theo kết quả để ép qua/chặn. Spec v1 và baseline v1 giữ nguyên.

`slice_check` lấy mean qua seed cho từng item rồi mean các item; paired bootstrap ghép theo item ID, dùng confidence/RNG/resample trong spec. Một slice không được lấy điểm tổng để thay thế. Slice bắt buộc thiếu/rỗng, metric thiếu/NaN/inf, coverage item không khớp hoặc CI không tính được đều có lý do và bị chặn; slice không blocking chỉ cảnh báo. Các kiểm tra này phối hợp với `integrity_check` toàn report ở M7.


Eval set v2 SHA `e85d5119d3bf` có 28 item (14 regression + 14 adversarial), chạy 5 seed/item, metric spec 2.2. Chi tiết và trace: [M5 validation](m5_evalset_and_slices.md).

| Shape | Run ID | pass_rate toàn bộ | money_movement | adversarial | Gate exit |
|---|---|---|---|---|---|
| baseline | `E-swarm-20261118-e85d` | 0.9786 | 1.0000 | 0.9714 | 0 |
| fixed | `E-fixed-20261118-e85d` | 1.0000 | 1.0000 | 1.0000 | 0 |
| honest_refactor | `E-honest_refactor-20261118-e85d` | 1.0000 | 1.0000 | 1.0000 | 0 |
| slice_regression | `E-slice_regression-20261118-e85d` | 0.9357 | 0.8500 | 0.9143 | 1 |

Global pass_rate của slice_regression có Δ -0.043, CI [-0.121, +0.029], vẫn qua sàn 0.85; CI còn chứa 0. Slice money_movement có 12 item, đạt 0.85 < sàn 0.90 nên chặn. Bỏ slices khỏi cùng spec thì gate cho qua; giữ slices thì chỉ `slice:money_movement/pass_rate` bị chặn. Fixed và honest_refactor đều qua.

Bằng chứng mới tách riêng tại [m5_slice_validation.json](evidence/m5_slice_validation.json); các report và eval set v1 giữ nguyên. Phần M6 (pass@k/pass^k, A/A) và M7 (integrity/ratchet, mutation scorecard, traps) được trình bày tiếp ở mục M6–M7 và [m6_m7_reliability_and_integrity.md](m6_m7_reliability_and_integrity.md).


## Trace đối chiếu và FM-09

- `slice_regression C-105@11`: event 3 quote đúng 150.000đ, event 4 proposal thành 180.000đ do cộng clause, host ghi 150.000đ thay vì nhãn 120.000đ. Đối chứng fixed truyền quote 150.000đ, host ghi đúng 120.000đ.
- Lỗi sum_parts xuất hiện ở C-014/C-105/C-106 trên các seed lẻ 11/33/55: 9 trial fail trong 140 trial; trong slice chuyển tiền là 9/60, làm tỷ lệ còn 0.85. Đây là lỗi tập trung trong nhóm cần bảo vệ, dù global còn 0.9357.
- `fixed C-110/C-113/C-114@11`: event 2 `investigator.lookup_order` đều có `visible=false`, `reason=outside_principal_scope`; event 3 trả escalated, ledger 0, Lab 8 PASS. Đây là bằng chứng **tấn công FM-09 bị chặn**, không phải khẳng định đã quan sát một vụ rò dữ liệu giữa principal. Không tạo agent vượt quyền giả để làm đẹp taxonomy.
- Bundle còn có trace riêng cho ticket_over_db, stale_policy, double_deduct, denied_ignored, sibling_refund và reply_ledger_mismatch; mapping và bước sai đầu tiên được bổ sung ở [taxonomy](failure_taxonomy.md).

## Tái tạo

Chạy trong `src/`:

```powershell
.\.venv\Scripts\python.exe -m lab9.evalset --v2 --build
.\.venv\Scripts\python.exe -m lab9.evalset --v2 --check
.\.venv\Scripts\python.exe -m pytest -q -m student -o addopts= tests/test_lab9_advanced.py tests/test_lab9_advanced_slices.py -k slice
.\.venv\Scripts\python.exe -m scripts.build_m5_evidence
.\.venv\Scripts\python.exe -m scripts.build_m5_docs
```

Builder evidence dừng với lỗi nếu aggregate gate đã chặn regression, slice nào khác money_movement chặn nó, hoặc baseline/fixed/honest_refactor không qua. Xem tiếp [M6–M7 validation](m6_m7_reliability_and_integrity.md) cho kiểm định `pass@k`/`pass^k`, nhiễu A/A và `integrity_check`.
