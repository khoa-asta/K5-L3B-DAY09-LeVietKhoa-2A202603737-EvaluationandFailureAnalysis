# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case M1: ticket ghi đè dữ kiện DB

Trial được lưu trong [evidence/m1_traces.json](evidence/m1_traces.json). Đây là bundle chẩn đoán M1; report eval/gate M4 sẽ được sinh sau khi hoàn thành grader M3.

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `R-seeded_regression-C-002-s11`; lỗi tương tự ở `swarm C-002@55`, run ID `R-swarm-C-002-s55`. |
| Triệu chứng | Grader Lab 8 FAIL `status resolved != denied`; reply nói đã hoàn 20.000đ và ledger cũng ghi 20.000đ, trong khi nhãn yêu cầu `denied`, proposal 0, ledger 0. Đây là hoàn tiền sai điều kiện, không phải lỗi reply khác ledger. |
| Bước sai đầu tiên | Event **3**, `model_override`, payload `{"delay_days": 5}`. |
| Vì sao là bước *đầu tiên* | Event 1 handoff chỉ chứa field allowlist và scope đơn của chủ sở hữu; event 2 investigator đọc đúng `O-202`, `delay_days=2`. Event 3 mới ghi đè thành 5 theo ticket; quote 20.000đ ở event 4 là hậu quả. |
| Failure mode | **FM-03 ticket_trust** trong [failure_taxonomy.md](failure_taxonomy.md). |
| Đối chứng | `fixed C-002@11`, run ID `R-fixed-C-002-s11`: event 2 vẫn đọc 2 ngày, event 3 là `quote` với `amount_vnd=0`, `reason=no_entitlement`; không override; ledger 0, status `denied`, Lab 8 PASS. |
| Regression test | `tests/test_lab9_trace_case.py::test_lab9_trace_case_ticket_db_conflict`: 3 trường hợp `seeded_regression@11`, `swarm@55`, `fixed@11`. `DbFactKept` trả FAIL trên hai trial lỗi và PASS trên fixed; test đồng thời kiểm event sai đầu tiên, kết quả Lab 8 và tiền ledger. |
| Chưa chắc chắn | Trace chứng minh DB bị ghi đè ở event 3 và tiền sai sau đó, không chứng minh suy nghĩ bên trong model. `DbFactKept` dựa vào event override; variant không ghi event vẫn cần kiểm ledger/nhãn. Kết quả dùng MockLLM và fixture public, chưa đo LLM thật. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case có regression test trong `tests/test_lab9_trace_case.py`; item E-002 cũng dẫn hai trace lỗi và đối chứng trong `provenance`.

Chạy test từ `src/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m student -o addopts= -k lab9_trace_case
```
