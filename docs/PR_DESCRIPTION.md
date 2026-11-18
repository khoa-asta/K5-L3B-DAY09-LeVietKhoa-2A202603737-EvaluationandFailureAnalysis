Hoàn thiện đánh giá Core Lab 9 và chặn regression hoàn tiền

Agent có thể báo hoàn thành khi host từ chối, gửi proposal đã trừ tiền trước hoặc báo số tiền khác ledger. Thay đổi bổ sung taxonomy/eval set, calibration judge và các code grader để giải thích, phát hiện các lỗi này; gate so paired CI theo item với baseline swarm.

Phần setup M0 khôi phục src Day 8 gốc của giảng viên và đưa config/data/tests về đúng đường dẫn sau khi copy thủ công. Nội dung src/lab8 hiện khớp nguồn gốc; diff ba shape là việc bỏ bản của nhóm đã copy nhầm.

Baseline `E-swarm-20261118-fc7f` dùng eval set `fc7f989588fd`, metric spec 1.1. Fixed qua gate; seeded regression bị chặn trên pass_rate (Δ -0.271, CI [-0.500, -0.057]), refund_amount_correct và reply_amount_correct. M3 phát hiện 20/20 trial lỗi, báo nhầm fixed 0/70; helpful judge bị loại vì recall 0.300.

Validation local:

- Smoke M0, eval set check, student tests Core và host tests.
- Swarm PR và fixed: gate exit 0; seeded_regression: gate exit 1.
- `lab9.ci_check`: exit 0; báo cáo có 70 rows và không có evaluator failure.

Output gate regression từ script, không nhập lại số:

```text
gate: PR E-seeded_regression-20261118-fc7f vs main E-swarm-20261118-fc7f · eval set fc7f989588fd
  approval_bypass        0        {"max": 0}                                                            ok
  secret_leak            0        {"max": 0}                                                            ok
  db_fact_kept           0.9286   {"min": 0.95}                                                         warn
  refund_amount_correct  0.8571   {"min": 0.95, "no_significant_drop": true} Δ -0.129 CI [-0.315, +0.000] BLOCK
  proposal_amount_correct 0.7857   {"min": 0.95}                                                         warn
  reply_amount_correct   0.7857   {"min": 0.95, "no_significant_drop": true} Δ -0.214 CI [-0.429, +0.000] BLOCK
  pass_rate              0.7143   {"min": 0.85, "no_significant_drop": true} Δ -0.271 CI [-0.500, -0.057] BLOCK
  pass_5                 0.7143   {"min": 0.8}                                                          warn
  cost_per_success       81.202   {"max_increase": 0.1}                                                 warn
exit 1 — blocked: refund_amount_correct, reply_amount_correct, pass_rate
```

Giới hạn: MockLLM/public replay, 14 item, baseline swarm không phát event reply; chưa đối chiếu anchor key riêng, M5 đã hoàn thành local, M6–M7 còn chờ. Trạng thái GitHub CI và merge cần được kiểm trên PR.

Đích PR: `khoa-asta/K5-L3B-DAY09-LeVietKhoa-2A202603737-EvaluationandFailureAnalysis`, nhánh làm bài → `main` trong cùng bản fork.

## M5 — Eval set v2 và slice gate

Eval set v2 SHA `03a8cc19dece` có 28 item (14 regression + 14 adversarial), chạy 5 seed/item, metric spec 2.1. Chi tiết và trace: [M5 validation](m5_evalset_and_slices.md).

| Shape | Run ID | pass_rate toàn bộ | money_movement | adversarial | Gate exit |
|---|---|---|---|---|---|
| baseline | `E-swarm-20261118-03a8` | 0.9786 | 1.0000 | 0.9714 | 0 |
| fixed | `E-fixed-20261118-03a8` | 1.0000 | 1.0000 | 1.0000 | 0 |
| honest_refactor | `E-honest_refactor-20261118-03a8` | 1.0000 | 1.0000 | 1.0000 | 0 |
| slice_regression | `E-slice_regression-20261118-03a8` | 0.9357 | 0.8500 | 0.9143 | 1 |

Global pass_rate của slice_regression có Δ -0.043, CI [-0.121, +0.029], vẫn qua sàn 0.85; CI còn chứa 0. Slice money_movement có 12 item, đạt 0.85 < sàn 0.90 nên chặn. Bỏ slices khỏi cùng spec thì gate cho qua; giữ slices thì chỉ `slice:money_movement/pass_rate` bị chặn. Fixed và honest_refactor đều qua.

Bằng chứng mới tách riêng tại [m5_slice_validation.json](evidence/m5_slice_validation.json); các report và eval set v1 giữ nguyên. M6 (pass@k/pass^k, A/A) và M7 (integrity/ratchet) chưa hoàn thành; giá trị pass@k/pass^k trong report v2 hiện là null. Việc có baseline_v2 sẽ bật job advanced khi đẩy lên GitHub; chưa có kết quả CI advanced xanh trong bằng chứng M5 này.
