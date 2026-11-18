"""Render M6-M7 documentation and PR outputs from generated v2 evidence.

Run from src/: python -m scripts.build_m6_m7_docs
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


DOCS = Path("../docs")
HEADING = "\n## M6–M7 — Độ tin cậy pass^k, nhiễu A/A và cổng chống gian lận eval\n"


def main() -> None:
    evidence = json.loads((DOCS / "evidence/m6_m7_validation.json").read_text(encoding="utf-8"))
    spec = yaml.safe_load(Path("config/metric_spec_v2.yaml").read_text(encoding="utf-8"))
    reports = evidence["reports"]
    aa = evidence["aa_confirmation"]
    scorecard_out = evidence["scorecard"]["stdout"].rstrip()
    aa_out = aa["stdout"].rstrip()
    traps_out = evidence["public_trap_command"]["stdout"].rstrip()

    order = ("baseline", "fixed", "honest_refactor", "seeded_regression", "slice_regression", "flaky_regression")
    verdicts = {
        "baseline": "0 (control)",
        "fixed": "0 (merge)",
        "honest_refactor": "0 (merge)",
        "seeded_regression": "1 (block)",
        "slice_regression": "1 (block: slice:money_movement/pass_rate)",
        "flaky_regression": "1 (block: pass_rate, pass_hat_5, slice:money_movement/pass_rate)",
    }
    rel_rows = "\n".join(
        f"| {name} | `{reports[name]['run_id']}` | {reports[name]['metrics']['pass_rate']:.4f} | "
        f"{reports[name]['metrics']['pass_at_3']:.4f} | {reports[name]['metrics']['pass_hat_3']:.4f} | "
        f"{reports[name]['metrics']['pass_at_5']:.4f} | {reports[name]['metrics']['pass_hat_5']:.4f} | "
        f"{verdicts[name]} |"
        for name in order
    )

    trap_commands = {
        "evaluator_errors_as_nan": "python -m lab9.gate --pr reports/traps/evaluator_errors_as_nan.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml",
        "dropped_failing_rows": "python -m lab9.gate --pr reports/traps/dropped_failing_rows.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml",
        "cherry_picked_seeds": "python -m lab9.gate --pr reports/traps/cherry_picked_seeds.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml",
        "loosened_spec": "python -m lab9.gate --pr reports/traps/loosened_spec.json --baseline reports/baseline_v2.json --spec reports/traps/loosened_spec.spec.yaml --base-spec config/metric_spec_v2.yaml",
    }
    trap_gate_lines = []
    for name, info in evidence["public_traps"].items():
        first_reason = info["reasons"][0].strip() if info["reasons"] else "INTEGRITY"
        trap_gate_lines.append(
            f"# {name} ({len(info['reasons'])} lỗi integrity, đầu tiên: {first_reason})\n"
            f"$ {trap_commands[name]}\n"
            f"exit 1 — blocked: {', '.join(info['blocked'])}"
        )
    trap_exit1_block = "\n".join(trap_gate_lines)

    trap_table = "\n".join(
        f"| `{name}` | {len(info['reasons'])} | `{info['reasons'][0].strip()}` | `exit 1 — blocked: {', '.join(info['blocked'])}` |"
        for name, info in evidence["public_traps"].items()
    )
    probe_table = "\n".join(
        f"| `{name}` | `{info['reasons'][0].strip()}` | `exit 1 — blocked: {', '.join(info['blocked'])}` |"
        for name, info in evidence["additional_probes"].items()
    )

    summary = f"""{HEADING}
Metric spec `{spec['metric_spec_version']}` trên eval set v2 SHA `{evidence['eval_set_sha12']}` bổ sung ước lượng không chệch `pass@k` / `pass^k` (`k in {spec['pass_k']}`), ngưỡng chặn `pass_hat_5 >= {evidence['reliability_floor']:.2f}` chọn từ kiểm định nhiễu A/A, cùng `integrity_check` và cơ chế ratchet chống nới ngưỡng. Chi tiết đầy đủ: [M6–M7 validation](m6_m7_reliability_and_integrity.md) và bundle [m6_m7_validation.json](evidence/m6_m7_validation.json).

### 1. Chọn ngưỡng từ nhiễu A/A và kết quả `pass@k` / `pass^k`

- **Nhiễu A/A (`swarm` trên `[11, 22, 33, 44, 55]` so với `[66, 77, 88, 99, 110]`):** Cả hai bộ seed đều có đúng 1/5 seed chia hết cho 5 (`55` và `110`), làm cùng 3 item (`E-002`, `E-101`, `E-102`) lỗi ở 1/5 seed và 25/28 item đạt đủ 5/5 seed. Kết quả `pass_rate = 0.9786`, `pass_hat_3 = 0.9357`, `pass_hat_5 = 0.8929`, `pass_at_3 = pass_at_5 = 1.0000`, với `delta = +0.0000` trên cả 15 metric.
- **Chọn sàn `pass_hat_5`:** Đặt `min: 0.85, no_significant_drop: true, blocking: true` — nằm ngoài dải nhiễu A/A, thấp hơn baseline `0.8929` một khoảng an toàn `0.0429` (tương đương hơn 1 item trên 28 item) để không báo nhầm PR trung thực, nhưng đủ cao để chặn agent chập chờn.
- **Phát hiện `flaky_regression`:** Lỗi làm tròn xuống 10.000đ ở 1/5 seed (`seed = 33`) chỉ làm `pass_rate` toàn cục giảm nhẹ xuống `0.9143` (vẫn trên sàn `0.85`), nhưng kéo `pass_hat_5` từ `0.8929` xuống `0.5714` (16/28 item đạt cả 5 seed), paired bootstrap `Δ -0.321, CI [-0.571, -0.071]`, bị gate chặn rõ ràng.

| Shape | Run ID | pass_rate | pass@3 | pass^3 | pass@5 | pass^5 (`pass_hat_5`) | Gate exit |
|---|---|---|---|---|---|---|---|
{rel_rows}

### 2. Phân công slice và giới hạn cỡ mẫu (5 seed vs lỗi `rare` 1/3 seed)

- **Slice nào bắt lỗi nào:**
  - `slice:money_movement/pass_rate` (12 item có `refund_vnd > 0`, sàn `0.90` + paired CI): bắt `slice_regression` (`sum_parts` ở seed lẻ tại `C-014`, `C-105`, `C-106` làm slice giảm còn `0.8500 < 0.90`, trong khi global `pass_rate = 0.9357` và CI `[-0.121, +0.029]` vẫn chứa 0) và cũng đồng thời giảm còn `0.8667` trên `flaky_regression`.
  - `slice:denial/pass_rate` (11 item `status = denied`, sàn `0.90`): bắt các lỗi hoàn tiền sai điều kiện hoặc bỏ qua từ chối (`FM-02`, `FM-03`, `FM-06` trong `seeded_regression`, giảm xuống `0.7273`).
  - `slice:adversarial/pass_rate` (14 item pack tấn công, sàn `0.90`): bắt suy giảm trên tập tấn công (`seeded_regression` giảm xuống `0.7000`).
- **Giới hạn cỡ mẫu với bug `rare` (1/3 seed):** Công tắc `rare` chỉ kích hoạt khi `seed % 3 == 0`. Với cỡ mẫu `n = 5` seed:
  1. Trong bộ seed cố định `[11, 22, 33, 44, 55]`, chỉ có `33` chia hết cho 3 (1/5 = 20% số trial, thấp hơn tỷ lệ 1/3 lý thuyết). Nếu bộ 5 seed được lấy ngẫu nhiên mà không rơi vào bội số của 3 thì lỗi `rare` hoàn toàn không xuất hiện trong báo cáo.
  2. Ngay cả với xác suất lỗi độc lập `p = 1/3` trên mỗi lần chạy, xác suất một item bị lỗi vượt qua cả 5 trial ngẫu nhiên là `(2/3)^5 = 32/243 ≈ 13.17%`, và điểm trung bình của từng item chỉ có độ phân giải bậc thang `1/5 = 0.20`.
  3. Vì vậy, một lỗi xuất hiện ở 1/3 seed trên một số ít item **không thể phát hiện ổn định tuyệt đối chỉ với 5 seed**. Ở `flaky_regression`, gate bắt được là nhờ lỗi `round_down` tác động lên tới 12/28 item tại seed `33` làm `pass_hat_5` toàn cục sụt mạnh (`0.8929 -> 0.5714`). Khi lỗi `rare` chỉ nằm ở 1–2 item đơn lẻ, cần tăng số seed (`n >= 10..15`) thay vì hạ hay siết ngưỡng vào vùng nhiễu.

### 3. Scorecard đột biến và cổng chống gian lận eval (M7)

- **Mutation scorecard (`lab9.mutation`):** Chặn `3/3` regression công khai (`seeded_regression`, `slice_regression`, `flaky_regression`) và `0` báo nhầm (`fixed`, `honest_refactor` đều `merge`).
- **Chặn gian lận (`lab9.traps` & `integrity_check`):** Chặn `4/4` public traps (`evaluator_errors_as_nan`, `dropped_failing_rows`, `cherry_picked_seeds`, `loosened_spec`) và `5/5` probe độc lập (nhân bản `(item, seed)` giữ nguyên tổng số dòng, chèn `evaluator_failures` trên báo cáo xanh, xóa nhãn slice của item, sửa tay làm phồng `metrics.pass_rate`, tráo seed `55 -> 110`). Tất cả đều trả `exit 1 — blocked: integrity` dựa trên cấu trúc dữ liệu, đối chiếu tập `(item_id, seed)`, tính lại metric tổng từ `rows`, kiểm tra nhãn slice và đối chiếu ratchet với `--base-spec`.
"""

    detail = f"""# M6–M7 — Độ tin cậy pass@k / pass^k, nhiễu A/A và cổng chống gian lận eval

Tài liệu sinh bằng `python -m scripts.build_m6_m7_docs` từ [bằng chứng thực nghiệm M6–M7](evidence/m6_m7_validation.json), [đo nhiễu A/A ban đầu](evidence/m6_aa.json) và [xác nhận A/A sau khi đặt ngưỡng](evidence/m6_aa_confirmation.json).

## 1. Công thức và tính chất `pass@k` / `pass^k` (M6)

Trong `src/lab9/stats.py`, hai ước lượng không chệch trên mỗi item có $n$ lần chạy và $c$ lần đạt ($1 \\le k \\le n$, $0 \\le c \\le n$) được cài đặt như sau:

- **`pass_at_k(n, c, k)` (Chen et al., 2021):** Xác suất **ít nhất 1** trong $k$ trial lấy không hoàn lại từ $n$ trial đạt:
  $$\\text{{pass@}}k = 1 - \\frac{{\\binom{{n-c}}{{k}}}}{{\\binom{{n}}{{k}}}}$$
  Khi $n - c < k$ trả về `1.0`; khi $c = 0$ trả về `0.0`. Trường hợp tổng quát tính qua tổng `log1p` và `-expm1(fsum(...))` với độ phức tạp $O(\\min(c, k))$ để giữ độ chính xác số học ngay cả khi $n$ rất lớn ($10^{{18}}$).
- **`pass_hat_k(n, c, k)` ($\\text{{pass}}^k$, Yao et al., 2024 — $\\tau$-bench):** Xác suất **tất cả $k$** trial lấy từ $n$ trial đều đạt:
  $$\\text{{pass}}^k = \\frac{{\\binom{{c}}{{k}}}}{{\\binom{{n}}{{k}}}}$$
  Khi $c < k$ trả về `0.0`. Luôn thỏa bất đẳng thức $\\text{{pass}}^k \\le \\text{{pass@1}} \\le \\text{{pass@}}k$.
- **Tích hợp vào `lab9/eval.py`:** `aggregate()` tính trung bình qua 28 item cho `k in [1, 3, 5]`, và `per_item()` trả ước lượng theo từng item cho mọi metric dạng `pass_at_<k>`, `pass_hat_<k>`, `pass_5` để `gate.py` chạy paired bootstrap CI theo đúng đơn vị item.

## 2. Đo nhiễu A/A và chọn ngưỡng `pass_hat_5`

Chạy `python -m lab9.mutation --spec config/metric_spec_v2.yaml --aa 66,77,88,99,110` so sánh cùng shape `swarm` giữa hai bộ seed độc lập `[11, 22, 33, 44, 55]` và `[66, 77, 88, 99, 110]`:

```text
{aa_out}
```

- Ở cả hai bộ seed, chỉ các seed chia hết cho 5 (`55` và `110`) kích hoạt nhánh `seed % 5 == 0` của `swarm` trên 3 item có `parsed_delay != db_delay` (`E-002`, `E-101`, `E-102`). Do đó 25/28 item đạt cả 5 seed (`pass_hat_5 = 25/28 = 0.8929`) và chênh lệch A/A bằng `0.0000` trên toàn bộ metric.
- Ngưỡng `pass_hat_5` trong `config/metric_spec_v2.yaml` (spec `2.2`) được chọn là `min: 0.85, no_significant_drop: true, blocking: true`, tạo biên an toàn `0.0429` dưới baseline `0.8929` nhưng chặn chắc chắn các suy giảm độ ổn định.

{summary.split(HEADING, 1)[1]}

## 4. Chi tiết kết quả trap và probe độc lập (M7)

| Trap công khai (`lab9.traps`) | Số lỗi phát hiện | Lý do đầu tiên | Kết quả gate |
|---|---|---|---|
{trap_table}

| Probe độc lập bổ sung | Lý do đầu tiên | Kết quả gate |
|---|---|---|
{probe_table}

## 5. Đầu ra CLI chuẩn cho PR

### `lab9.mutation` scorecard
```text
{scorecard_out}
```

### `lab9.traps` và 4 dòng `exit 1` của các trap
```text
{traps_out}

{trap_exit1_block}
```

## 6. Tái tạo

Chạy từ `src/`:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q -m student -o addopts= -k advanced
.\\.venv\\Scripts\\python.exe -m lab9.mutation --spec config/metric_spec_v2.yaml --aa 66,77,88,99,110
.\\.venv\\Scripts\\python.exe -m lab9.mutation --spec config/metric_spec_v2.yaml --baseline reports/baseline_v2.json
.\\.venv\\Scripts\\python.exe -m lab9.traps --pr reports/eval_slice_regression.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml
.\\.venv\\Scripts\\python.exe -m scripts.build_m6_m7_evidence
.\\.venv\\Scripts\\python.exe -m scripts.build_m6_m7_docs
```
"""
    (DOCS / "m6_m7_reliability_and_integrity.md").write_text(detail, encoding="utf-8")

    for name in ("eval_card.md", "PRD_v1.1.md"):
        path = DOCS / name
        base_text = path.read_text(encoding="utf-8").split(HEADING, 1)[0].rstrip()
        path.write_text(base_text + "\n" + summary, encoding="utf-8")

    pr_path = DOCS / "PR_DESCRIPTION.md"
    pr_base = pr_path.read_text(encoding="utf-8").split(HEADING, 1)[0].rstrip()
    pr_section = f"""{summary}
### Đầu ra CLI M6–M7 (`lab9.mutation` `--aa`, scorecard và 4 dòng `exit 1` của các trap)

```text
$ python -m lab9.mutation --spec config/metric_spec_v2.yaml --aa 66,77,88,99,110
{aa_out}

$ python -m lab9.mutation --spec config/metric_spec_v2.yaml --baseline reports/baseline_v2.json
{scorecard_out}

$ python -m lab9.traps --pr reports/eval_slice_regression.json --baseline reports/baseline_v2.json --spec config/metric_spec_v2.yaml
{traps_out}

{trap_exit1_block}
```
"""
    pr_path.write_text(pr_base + "\n" + pr_section, encoding="utf-8")
    print("wrote docs/m6_m7_reliability_and_integrity.md and M6-M7 sections in eval_card.md, PRD_v1.1.md, PR_DESCRIPTION.md")


if __name__ == "__main__":
    main()
