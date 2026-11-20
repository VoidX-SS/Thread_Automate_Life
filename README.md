# Thread Automate Life v3 — Tâm lý học, Bộ não, Triết học & Nghịch lý lựa chọn

Hệ thống vận hành kênh Threads tiếng Việt tự động hoàn toàn dựa trên **kho 200 seed đã xác thực (`data/seed_bank.json`)**, **kiến trúc 2 tầng mô hình (`gemini-4-hydrogen` + `gemini-3.5-flash-lite`)** và **đa định dạng gốc trên Threads API** (Native Poll, Self-Reply Chain, Topic Tag).

Chạy thuần Python 3.11+ standard library, không cần `pip install`.

## Kiến trúc 2 tầng mô hình (Quản trị quota 20 req/ngày)

| Vai trò | Mô hình đảm nhận | Tải ước tính (2 bài + 2 lượt reply/ngày) | Vai trò cụ thể |
|---|---|---|---|
| `post_writer` | **`gemini-4-hydrogen`** (Flagship) | 2 req/ngày | Viết 6 bài nháp sắc gọn, tự nhiên, bám sát 6 seed được cấp |
| `post_screener` | **`gemini-3.5-flash-lite`** (Workhorse) | 2 req/ngày | Sơ loại nhanh: kiểm tra bám sát seed, đúng format, chống trùng ý với 30 bài gần nhất, lọc top 3 |
| `post_chief_editor` | **`gemini-4-hydrogen`** (Flagship) | 2 req/ngày | Tổng biên tập chấm điểm độc lập (`temperature=0.15`), kiểm soát chất lượng cuối cùng |
| `reply_writer` | **`gemini-3.5-flash-lite`** (Workhorse) | 0–20 req/ngày | Soạn phản hồi đối thoại thông minh theo từng bình luận người đọc |
| `reply_editor` | **`gemini-3.5-flash-lite`** (Workhorse) | 0–20 req/ngày | Duyệt an toàn & giọng điệu cho từng câu trả lời |
| CI Preview (`test.yml`) | **`gemini-3.5-flash-lite`** | 100% Workhorse | Đặt `ALLOW_FLAGSHIP_IN_DRY_RUN=false` để push code không đốt quota 20/ngày |

- **Tổng mức dùng `gemini-4-hydrogen` bình thường:** ~4 req/ngày (tối đa 8 req/ngày nếu có retry) — luôn nằm an toàn trong ngưỡng **20 req/ngày**.
- **Bảo vệ chống tràn quota:** `data/quota.json` đếm số request theo ngày giờ Việt Nam. Khi chạm `FLAGSHIP_DAILY_CAP` (mặc định 20) hoặc gặp lỗi 429/500/503, hệ thống tự động hạ cấp mượt sang `gemini-3.5-flash-lite` và ghi vết rõ ràng vào `audit`.

## 4 Trụ cột nội dung & 200 Seed (`data/seed_bank.json`)

- **50 `dilemma`:** Tình huống đạo đức, lý thuyết trò chơi, kinh tế học hành vi → đăng dạng **Native Poll** (`poll_attachment` 2–3 lựa chọn ≤ 25 ký tự).
- **50 `brain_glitch`:** Lỗi nhận thức, ảo giác thần kinh, trí nhớ → đăng dạng **Chuỗi 2 tầng** (Bài chính + tự động đăng `followup_reply` sau 10 giây).
- **50 `philosophy`:** Thí nghiệm tư duy & khái niệm triết học ứng dụng ít phổ biến.
- **50 `human_paradox`:** Thiên kiến nhận thức & nghịch lý hành vi xã hội.
- **Cooldown 120 bài:** Một seed đã đăng sẽ không lặp lại trong ít nhất 120 bài (~60 ngày với tần suất 2 bài/ngày).

## Lệnh chạy kiểm thử

```bash
python -m unittest -v
python thread_life_bot.py --offline
python thread_life_bot.py --dry-run
```

## Thiết lập GitHub Secrets & Variables

1. **Cấp lại Threads Token đủ 5 quyền** (để chạy cả Reply và Insights):
   ```bash
   python get_threads_token.py
   ```
   (Để gia hạn token trước khi hết 60 ngày: `python get_threads_token.py --refresh`.)
2. Tại **Settings → Secrets and variables → Actions**:
   - Secrets: `GEMINI_API_KEY`, `THREADS_ACCESS_TOKEN`
   - Variables gợi ý:
     - `GEMINI_FLAGSHIP_MODEL` = `gemini-4-hydrogen`
     - `GEMINI_WORKHORSE_MODEL` = `gemini-3.5-flash-lite`
     - `FLAGSHIP_DAILY_CAP` = `20`
     - `DRY_RUN` = `false` (sau khi đã preview `--dry-run` đạt yêu cầu)
     - `ENABLE_REPLIES` = `true` (sau khi cập nhật token 5 quyền)
     - `ENABLE_INSIGHTS` = `true` (sau khi cập nhật token 5 quyền)
     - `ENABLE_TREND_FEED` = `false`

## Lịch chạy tự động (giờ Việt Nam)

- **11:45:** Đăng bài chính slot sáng (`post`)
- **12:30:** Quét & trả lời bình luận trưa (`reply` + `insights`)
- **20:00:** Đăng bài chính slot tối (`post`)
- **20:30:** Quét & trả lời bình luận tối (`reply` + `insights`)
