# Thread Automate Life v3.2

Hệ thống vận hành kênh Threads tiếng Việt tự động hoàn toàn về Tâm lý học hành vi, Bộ não, Triết học đời sống và Nghịch lý lựa chọn. Chạy thuần Python 3.11+ standard library, không cần `pip install`.

## Thay đổi cốt lõi ở v3.2

- **Loại bỏ hoàn toàn GitHub `schedule:` cron** trong `.github/workflows/threads-bot.yml` để tránh delay rạng sáng; kích hoạt chuẩn giờ qua **cron-job.org** bằng `workflow_dispatch` hoặc `repository_dispatch`.
- **4 định dạng bám đúng tín hiệu thuật toán Threads** (`format_weights` 30 / 30 / 25 / 15):
  - `repost_manifesto` (30%): Tuyên ngôn tâm lý sắc gọn (55-220 ký tự), không tên học giả, không câu hỏi ép buộc, tối ưu lượt Repost.
  - `micro_dilemma` (30%): Tình huống đạo đức/lựa chọn 2-3 câu không thuật ngữ hàn lâm, hỏi 1 câu trả lời trong 3 giây.
  - `decode_chain` (25%): Chuỗi giải mã 3-4 tầng (`1/3..3/3` hoặc `1/4..4/4`), tự đăng nối tiếp từng reply (`reply_to_id` nối chuỗi) để kéo dwell time và follower.
  - `dilemma_poll` (15%): Native Poll API đã vá triệt để lỗi `HTTP400:100/4279063` bằng kiểm tra **<= 25 byte UTF-8** trên toàn bộ 200 seed, `gate()` và `Threads.publish_text`.
- **Phân vai 2 tầng mô hình tối ưu quota 20 req/ngày:**
  - `gemini-4-hydrogen` đảm nhận `post_writer`; tự động hạ cấp ngay lập tức sang `gemini-3.5-flash-lite` khi gặp `HTTP 429/400/403/404` (không ngủ chờ 4 lần vô ích), chỉ retry tối đa 2 lần cho lỗi tạm thời `500/503`.
  - `gemini-3.5-flash-lite` đảm nhận `post_writer_repair`, `post_screener`, `post_chief_editor`, `reply_writer`, `reply_editor`.
  - Thêm lượt **1-shot Repair (`post_writer_repair`)** bằng `flash-lite` nếu cả 6 bài nháp đầu bị `gate()` loại, giảm mạnh tỷ lệ rơi về `curated_reserve`.
- **Viết lại `REPLY_WRITER_RULES`:** 1 câu ngắn 15-130 ký tự, cấm văn phỏng vấn AI (`quả thực`, `lăng kính`, `tâm bão`, `tự vấn`).
- **Sửa lỗi mù `metrics.json`:** `collect_insights()` duyệt ngược từ bài mới nhất, không `break` khi 1 bài cũ lỗi 400/404 (chỉ dừng khi 401/403), hỗ trợ cả `total_value`, mở rộng cửa sổ `h24` (20-60h) và `h72` (60-144h).

## Cấu hình cron-job.org (5 khung giờ chuẩn VN)

Tạo các job trên `cron-job.org` (múi giờ `Asia/Ho_Chi_Minh`) theo các khung giờ đăng bài (ví dụ 07:30, 11:30, 14:30, 18:30, 21:30):

- **Method:** `POST`
- **URL (`workflow_dispatch`):** `https://api.github.com/repos/<OWNER>/<REPO>/actions/workflows/threads-bot.yml/dispatches`
- **Headers:**
  - `Authorization: Bearer <GITHUB_PAT_CO_QUYEN_ACTIONS_WRITE>`
  - `Accept: application/vnd.github+json`
  - `Content-Type: application/json`
- **Body (đăng bài + quét reply + insights):**
  ```json
  {"ref":"main","inputs":{"mode":"auto","live":true}}
  ```
- **Body (chỉ quét reply + thu insights sau 40 phút):**
  ```json
  {"ref":"main","inputs":{"mode":"reply","live":true}}
  ```

## Chạy kiểm thử cục bộ

```bash
python -m unittest -v
python thread_life_bot.py --offline
python thread_life_bot.py --dry-run
```
