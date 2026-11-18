# Judge audit

M2 sử dụng verdict replay trong hai CSV public, không gọi LLM/API. Nhãn người và nhãn judge gốc được giữ nguyên. **FAIL là lớp dương**: judge được đo theo khả năng tìm lỗi, vì vậy FN là lỗi thật bị judge cho qua. Kết quả có nguồn và hash tại [evidence/m2_calibration.json](evidence/m2_calibration.json), sinh bằng `python -m scripts.build_m2_calibration`.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Có, cả 3 ngưỡng | Dùng cho tone trong phạm vi replay đã kiểm; cần nhãn mới trước khi mở rộng. |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không: κ và recall dưới sàn | Loại khỏi gate; không dùng văn phong lịch sự thay cho kiểm tra nghiệp vụ. |

## Ma trận nhầm lẫn và hiệu chỉnh tỷ lệ lỗi

| Tiêu chí | TP | FP | FN | TN | Accuracy | Sensitivity | Specificity | Tỷ lệ FAIL judge | Rogan–Gladen |
|---|---|---|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.900 | 24/30 = 0.800 | 66/70 ≈ 0.942857 | 28/100 = 0.280 | 0.300 |
| helpful | 9 | 0 | 21 | 70 | 0.790 | 9/30 = 0.300 | 70/70 = 1.000 | 9/100 = 0.090 | 0.300 |

Precision = TP/(TP+FP), recall = TP/(TP+FN). Khi mẫu số bằng 0, code trả 0.0 để không coi judge không phát hiện gì là hoàn hảo. Cohen κ = (p_o − p_e)/(1 − p_e), trong đó p_e tính từ hai phân phối nhãn biên. Với tone: p_o=0.900, p_e=0.588, κ≈0.757282. Với helpful: p_o=0.790, p_e=0.664, κ=0.375.

Rogan–Gladen: `p_corrected = (p_observed + specificity - 1) / (sensitivity + specificity - 1)`, rồi clip về [0, 1]. Với tone: `(0.28 + 66/70 - 1)/(0.8 + 66/70 - 1) = 0.30`; với helpful: `0.09/0.30 = 0.30`. Kết quả cùng bằng tỷ lệ FAIL người gán trên chính bộ calibration, vì sensitivity/specificity được ước lượng từ bộ đó; đây không phải bằng chứng độc lập rằng judge đã tốt.

Hiệu chỉnh tỷ lệ tổng thể không xác định được 21 case bị bỏ sót và không làm recall của helpful tăng lên. Khi đem công thức sang dữ liệu mới, cần giả định sensitivity/specificity còn phù hợp. Nếu tổng sensitivity và specificity bằng 1, phép hiệu chỉnh không xác định. κ cũng không xác định khi không có mẫu hoặc p_e=1: không thay bằng κ=1 để cho qua calibration. Quyết định FLOORS dùng số chưa làm tròn; bảng và CLI chỉ làm tròn để hiển thị.

## Audit từng bất đồng và hành động sửa rubric

Các kết luận dưới đây đối chiếu reply và ghi chú của fixture; cột “Người” là nhãn người có sẵn trong CSV, chưa phải một đợt gán nhãn độc lập mới. Audit bao gồm cả FN, FP và một nhãn cần tái duyệt.

| # | Case / trích reply | Judge | Người | Kết luận audit | Hành động sửa rubric hoặc nhãn |
|---|---|---|---|---|---|
| 1 | H-008: “Em đã hoàn tiền cho anh rồi nha, anh check giúp em.” | PASS | FAIL | Người đúng theo chuẩn xưng hô CS của fixture; đây là FN. | Nêu rõ mức trang trọng và xưng hô được phép; thêm ví dụ “em…nha” không đạt thay vì coi thân thiện là đủ. |
| 2 | H-017: “Dạ, bạn ơi…rồi nha.” | PASS | FAIL | Người đúng theo note ngữ cảnh khách lớn tuổi; mở đầu “Dạ” không bù phần suồng sã. | Chấm cả câu và ngữ cảnh xưng hô; dùng “anh/chị” làm mặc định, bổ sung ví dụ đối chứng. |
| 3 | H-029: “…không cần nhắn thêm.” | PASS | FAIL | Người đúng: câu mang tính ra lệnh, dù có “Dạ, vui lòng”. | Thêm tiêu chí không ngăn cản khách tiếp tục yêu cầu hỗ trợ; đánh giá mệnh lệnh ở cuối câu. |
| 4 | H-042: “Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ.” | FAIL | PASS | Người đúng về tone: ngắn gọn, lịch sự; thiếu lời xin lỗi không tự động là lỗi. | Bỏ điều kiện bắt buộc phải có “xin lỗi” ở mọi reply. Tone không chứng minh số tiền đúng. |
| 5 | H-051: “Dạ, LogiX đã refund 90.000đ…ạ.” | FAIL | PASS | Người đúng theo glossary của fixture; đây là FP. | Ghi rõ “refund” được CS LogiX chấp nhận; ưu tiên tiếng Việt nhưng không tự động FAIL từ tiếng Anh đã cho phép. |
| 6 | H-063: “…đã hoàn 20.000đ và sẽ hoàn thêm…” | PASS | FAIL | Người đúng theo note: reply thêm lời hứa ngoài kết quả hệ thống. | Tách “cam kết có căn cứ” khỏi phép chấm lịch sự; đưa context kết quả host cho kiểm tra nghiệp vụ, không để tone judge phê duyệt tiền. |
| 7 | H-070: “…ạ 😂😂” | PASS | FAIL | Người đúng theo ngữ cảnh khiếu nại: emoji cười không phù hợp. | Thêm ví dụ emoji giễu/cười trong khiếu nại là không đạt; không cộng điểm chỉ vì có “Dạ/ạ”. |
| 8 | H-081: “Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ.” | FAIL | PASS | Note fixture ghi nhãn người sai vì đọc nhầm ticket, judge đúng; riêng reply không đủ xác minh lại kết luận theo context. | Đề xuất tái duyệt cùng ticket/trace bởi người thứ hai; nếu xác nhận thì sửa nhãn ở phiên bản mới và lưu lịch sử. Không đổi CSV gốc để cải thiện điểm hiện tại; làm rõ tiêu chí tone và đúng nội dung. |
| 9 | H-088: “Dạ, dạ, LogiX đã hoàn…ạ.” | FAIL | PASS | Người đúng: lặp từ nhẹ không làm câu thiếu tôn trọng hay khó hiểu; FP. | Cho phép lỗi gõ/lặp nhỏ khi ý nghĩa vẫn rõ, chỉ phạt khi cản trở hiểu hoặc gây bất lịch sự. |
| 10 | H-094: “Da, LogiX da hoan…xin loi vi su bat tien.” | PASS | FAIL | Người đúng theo chuẩn tiếng Việt của fixture: mất dấu xuyên suốt. | Nêu rõ yêu cầu dùng tiếng Việt có dấu; phân biệt một lỗi gõ nhỏ với cả câu mất dấu. |
| 11 | HL-015: reply hoàn 55.000đ; note ghi ledger 40.000đ. | PASS | FAIL | Người đúng theo ledger được mô tả trong note; FN về tiền. | Tiền phải chấm bằng code, so số đã khẳng định trong reply với ledger; judge ngôn ngữ không được tự suy số đúng. |
| 12 | HL-016: nhiều câu xin lỗi, nói hoàn 55.000đ; note ledger 35.000đ. | PASS | FAIL | Người đúng; dài và lịch sự vẫn có thể sai tiền. | Tách tone khỏi correctness; quy định FAIL nghiệp vụ khi tiền lệch, không cộng bù bởi xin lỗi hoặc độ dài. |
| 13 | HL-020: reply hoàn 90.000đ; note ledger 120.000đ. | PASS | FAIL | Người đúng; báo thấp hơn ledger cũng là sai, không chỉ báo cao. | Kiểm equality hai chiều sau chuẩn hóa VND; không dùng quy tắc chỉ phát hiện overclaim. |
| 14 | HL-043: lời xin lỗi và reply 35.000đ; note ledger 20.000đ. | PASS | FAIL | Người đúng; cùng dạng FM-08 đã quan sát ở M1. | Thêm case reply/ledger không khớp; `reply_amount_correct` dự kiến ở M3 phải bắt được, dù tone đạt. |
| 15 | HL-047: “Ok bạn, đơn O-515 xử lý rồi nhé.” | PASS | FAIL | Người đúng theo chuẩn xưng hô của fixture; câu mơ hồ không nêu kết quả cụ thể. | Tách tiêu chí xưng hô và nội dung cần thông báo; yêu cầu kết quả hoặc bước tiếp theo phù hợp task, không chỉ “xử lý rồi”. |

Ghi chú tiền ở các hàng HL là dữ liệu của chính CSV judge, không phải trace claim C-xxx tương ứng trong world Lab 8. Không nối theo order ID rồi tự suy lại ledger: một order có thể xuất hiện ở nhiều ví dụ với số tiền khác nhau.

## Rubric sau audit

1. **Tone:** lịch sự, trang trọng vừa đủ, xưng hô phù hợp, không giễu cợt/ra lệnh; không bắt buộc reply dài hoặc luôn xin lỗi; từ được glossary cho phép và lỗi gõ nhẹ không tự động bị phạt.
2. **Nghiệp vụ:** status, approval, quyền đọc/ghi và số tiền phải được đối chiếu dữ liệu host bằng code. Tiền trong reply phải đúng ledger; giọng điệu không bù cho lỗi tiền.
3. **Chất lượng nhãn:** case mơ hồ hoặc nghi sai nhãn như H-081 cần context và người tái duyệt; lưu nhãn sửa ở version mới, không sửa hồi tố bộ public để ép calibration qua sàn.
4. **Kiểm lại judge:** sau khi sửa rubric cần chạy judge trên một tập held-out mới có nhãn độc lập, gồm các nhóm lỗi vừa audit. Sửa văn bản rubric không làm các verdict replay hiện tại tự thay đổi.

## Kết luận

- **Tone dùng được trong phạm vi đã calibration:** vượt cả 3 sàn; còn 6 FN và 4 FP nên vẫn cần audit mẫu. Kết quả giữ nguyên cả nhãn H-081 đang được đề xuất tái duyệt.
- **Helpful không được dùng làm gate:** bỏ sót 21/30 lỗi, recall=0.300, κ=0.375. Precision=1.000 chỉ nói 9 lần nó báo FAIL đều trúng; không bảo đảm các lần PASS an toàn. Trong 21 FN có 18 case ghi sai tiền và 3 case xưng hô không đạt; văn phong lịch sự/dài không đủ chứng minh làm đúng việc.
- Bộ public có 70 PASS/30 FAIL cho mỗi tiêu chí; accuracy 0.790 của helpful không đủ để chấp nhận một bộ phát hiện lỗi. Dữ liệu replay đã công khai và được dùng để viết rubric, nên chưa phải held-out độc lập. Cần nhãn mới, đánh giá riêng theo nhóm lỗi và kiểm lại trước khi áp dụng cho người dùng thật.
- Hiệu chỉnh Rogan–Gladen chỉ ước lượng tỷ lệ lỗi tổng thể; không thay thế gate theo từng trial hoặc sửa verdict sai. Việc kiểm tiền và approval vẫn bằng code như taxonomy M1.

## Tái tạo kết quả

Chạy trong `src/` bằng môi trường M0:

```powershell
.\.venv\Scripts\python.exe -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
# Kỳ vọng exit 0, PASS floors.
.\.venv\Scripts\python.exe -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
# Kỳ vọng exit 1, FAIL floors: đây là kết quả đúng của M2.
.\.venv\Scripts\python.exe -m scripts.build_m2_calibration
.\.venv\Scripts\python.exe -m pytest -q -m student -o addopts= tests/test_lab9_stats.py tests/test_lab9_judge_calibration.py -k "not paired_bootstrap"
```

Hai test `paired_bootstrap` trong file stats thuộc M4, vì vậy lệnh trên chỉ kiểm phần M2. Artifact JSON sinh bằng script, không sửa tay; chứa ma trận, tỷ lệ, quyết định và toàn bộ bất đồng để đối chiếu bảng audit.
