# Thread Automate Life v2

Bot Threads tiếng Việt cho một sinh viên hư cấu 20 tuổi. Bản v2 chuyển từ sinh một đoạn nhật ký sang **6 phương án → lọc → biên tập riêng → chọn một bài**, có lịch sử để tránh lặp cảnh và câu chốt.

Nghiên cứu, lý do thay đổi và kế hoạch đo: [RESEARCH_VI.md](docs/RESEARCH_VI.md). Những câu dự phòng tự viết để kiểm tra giọng: [VOICE_SAMPLES.md](docs/VOICE_SAMPLES.md). Điểm biên tập không phải xác suất viral.

## Cách chạy

Python 3.11+; chỉ dùng standard library, không cần pip install.

```bash
python -m unittest -v
python thread_life_bot.py --offline
python thread_life_bot.py --dry-run
```

- `--offline`: không gọi mạng; xem một câu dự phòng đã biên soạn, không giả vờ đó là đầu ra Gemini.
- `--dry-run`: có thể gọi Gemini/nguồn trend để xem kết quả, luôn không đăng kể cả khi biến `DRY_RUN=false`.
- `--live`: đăng thật; giữ hành vi này cho workflow đã cấu hình của bạn.
- `--mode reply`: quét reply của các bài chính của tài khoản, kèm thu insights nếu đã bật.
- `--mode insights`: chỉ đọc số liệu; tuyệt đối không đăng bài.

Workflow chính giữ lịch **11:45 và 20:00 giờ Việt Nam**, cùng quét reply lúc **20:30**. Đây là giờ dự kiến: GitHub có thể trì hoãn cron. Không tự tăng tần suất; tối đa 2 bài chính/ngày theo giờ Việt Nam và một bài cho mỗi slot sáng/chiều. Chạy thủ công `live=false` luôn là preview.

## Nội dung v2

- Ưu tiên 60–180 ký tự, cho phép 35–360 khi ý cần thêm chỗ. Không ép mọi câu ngắn bằng nhau.
- Sáu dạng: one-liner, chuyện nhỏ có cú chốt, ý kiến nhẹ, đoạn thoại, xếp hạng vui, câu hỏi cụ thể.
- Giọng tui/t, có thể ê, cmay, hong, =)), :)) đúng lúc; tối đa 2 dấu biểu cảm; không bắt buộc slang.
- Bộ viết nhận 20 bài chính gần nhất, đổi chủ đề so với 2 bài gần nhất, tránh mô-típ lặp trong 5 bài. So trùng câu với 60 bản ghi gần đây.
- Biên tập viên gọi riêng đánh giá hook, giọng, điểm rơi và khả năng gợi trò chuyện; có quyền từ chối vì lặp ý hoặc rủi ro ngữ nghĩa. Bộ lọc xác định kiểm tra độ dài, nội dung nhạy cảm, sao chép, bait và giọng văn mẫu trước đó.
- Cho phép drama đời thường nhỏ và bất đồng về sở thích. Nội dung đụng cá nhân thật, cáo buộc, chuyện người chưa thành niên, tin giả hoặc chủ đề rủi ro bị loại.
- Hết phương án duyệt: chọn một trong 14 câu dự phòng mới, có nhãn `curated_reserve`. Đã dùng hết thì bỏ lượt, không lặp vô hạn.
- Lỗi Gemini 429/500/503: tối đa một lần thử lại ngắn. Lỗi hoặc model output hỏng luôn hiện trong audit, không bị che bằng một fallback vô danh.

Tất cả đánh giá tự động đều có giới hạn. Bio nên nói rõ đây là nhân vật hư cấu có hỗ trợ AI. Không dùng tài khoản này để giả mạo người thật hoặc bịa sự kiện về người khác.

## Secrets và variables

Tại **Settings → Secrets and variables → Actions**. Giữ Gemini key/Threads token hiện tại; không cần tạo lại để dùng bộ viết v2.

| Loại | Tên | Mặc định / vai trò |
|---|---|---|
| Secret | `GEMINI_API_KEY` | Key Google AI Studio; dùng cho tác giả + biên tập viên |
| Secret | `THREADS_ACCESS_TOKEN` | Threads user token, dùng cho đăng và quyền đã cấp |
| Variable | `GEMINI_MODEL` | `gemini-3.5-flash-lite`; giữ biến đang có |
| Variable | `DRY_RUN` | `true` nếu chưa đặt; giữ lựa chọn live đang có |
| Variable | `ENABLE_REPLIES` | `false` nếu chưa đặt; không tự bật lại |
| Variable | `REPLY_DAILY_CAP` | `3`, giới hạn cứng 0–5 cho cả ngày, kể cả chạy lại |
| Variable | `ENABLE_TREND_FEED` | `true` khi chưa đặt; một biến `false` có sẵn vẫn được giữ |
| Variable | `TREND_RSS_URL` | `https://trends.google.com/trending/rss?geo=VN`; chỉ HTTPS Google Trends |
| Variable | `TREND_HINT` | Gợi ý văn hoá tùy chọn; xem là dữ liệu, không phải mệnh lệnh |
| Variable | `TOPIC_SEED` | Gợi ý thêm; không ép lặp chủ đề ở mọi bài |
| Variable | `ENABLE_THREADS_TRENDS` | `false`; chỉ bật sau khi có quyền keyword search |
| Variable | `ENABLE_INSIGHTS` | `false`; chỉ bật sau khi token có quyền insights |

Sửa nhân vật, giới hạn chữ, chủ đề, dạng bài và sáo ngữ trong [config/persona.json](config/persona.json).

## Trend: nguồn nào, làm được gì?

1. Google Trends Vietnam RSS: chỉ giữ mục trong 48 giờ có dấu hiệu liên quan game, phim/nhạc, meme, đồ ăn, sinh viên; có thể không có tín hiệu phù hợp. Đây là xu hướng tìm kiếm, không phải bảng trend Gen Z trên Threads.
2. Nếu đã cấp `threads_keyword_search`, đặt `ENABLE_THREADS_TRENDS=true` để đọc một truy vấn đời thường luân phiên qua endpoint chính thức. Dữ liệu dùng làm quan sát, không được sao chép hoặc giả vờ là trải nghiệm của nhân vật.
3. Cả hai nguồn có thể thất bại độc lập. Bộ viết vẫn làm nội dung đời thường. Không tự bịa tên trend hoặc dữ kiện.
4. Không gọi Google Search Grounding trả phí; thường 2 request Gemini/lượt (writer + editor), tối đa 4 khi cả hai cần retry. Mỗi reply được xét có thể cần thêm 2 request; quét tối đa 8 comment/lượt. Quota thực tế xem trong AI Studio.

Đoạn nguồn bên ngoài chỉ dùng trong bộ nhớ, không commit nội dung/handle người khác vào repository. Audit chỉ lưu số nguồn và nguyên nhân loại phương án, không công khai văn bản comment người đọc.

## Đo để học từ bài thật

Cấp thêm `threads_manage_insights` cho token rồi đặt `ENABLE_INSIGHTS=true`. Token thiếu quyền không được tự nâng quyền: lượt thu số liệu sẽ báo thiếu quyền và không cản đăng bài.

Lúc 20:30, thu `views, likes, replies, reposts, quotes` cho bài nằm trong cửa sổ 24–48 giờ hoặc 72–96 giờ kể từ lúc đăng. Lưu một checkpoint mỗi cửa sổ vào `data/metrics.json`, có tuổi bài chính xác. Không điền số thiếu thành 0, không coi snapshot muộn là 24 giờ.

Bộ viết được thấy thống kê theo dạng bài (chỉ tính đầu ra Gemini đã biên tập, không trộn reserve), nhưng vẫn duy trì khám phá nhiều dạng. Chưa có tối ưu trọng số tự động hay kết luận nhân quả từ vài bài. Dùng 14 ngày đầu làm thử nghiệm chất lượng; xem thêm cách so trong báo cáo.

## Tìm hoặc tiếp tục Meta App cũ

1. Mở [My Apps](https://developers.facebook.com/apps/) bằng tài khoản Facebook developer đã dùng. Threads profile là tài khoản cần cấp quyền; nó không thay thế tài khoản quản trị Developer App.
2. Trong app nghi là app cũ, tìm use case **Access the Threads API**, xem Threads App ID/settings và roles. Nếu token đang đăng được thì không cần tạo app khác chỉ để nâng v2.
3. Nếu cần tạo app mới, chọn use case Threads, thêm đúng Threads profile làm tester khi dùng development mode, và chấp nhận lời mời tester trên Threads.
4. Với OAuth, redirect URI phải khớp chính xác URI đã đăng ký và bạn kiểm soát. Script `get_threads_token.py` đang có trong repo là tiện ích của setup trước; không commit key/token hay log toàn bộ token.
5. Kiểm tra profile, scopes, hạn dùng trong công cụ debug token của Meta. Muốn thêm scopes, phải thực hiện lại bước consent/token tương ứng.
6. Sau khi đổi token, chạy preview, rồi kiểm chứng một bài thật qua luồng đã được cấu hình. Theo dõi hạn token và làm mới theo tài liệu Meta; bản này chưa tự duy trì token vĩnh viễn.

| Chức năng | Quyền cần xem |
|---|---|
| Đọc profile và đăng | `threads_basic`, `threads_content_publish` |
| Đọc và quản lý/trả lời reply | `threads_read_replies`, `threads_manage_replies`, cùng quyền đăng |
| Số liệu bài đăng | `threads_manage_insights` |
| Tìm bài qua từ khoá | `threads_keyword_search` |

Tùy trạng thái app và tài khoản sử dụng, Meta có thể yêu cầu review/quyền truy cập phù hợp. Không cần triển khai dịch vụ OAuth đa người dùng để tiếp tục thử nghiệm tài khoản đang đăng được.

## Kiểm chứng trên GitHub

- Workflow **Test and preview content** chạy unit tests, preview offline, rồi gọi Gemini ở main bằng key đã có. Job này không nhận Threads token và không đăng.
- Workflow chính chạy tests trước mỗi lượt; preview/audit ở artifact `threads-run-...` trong 14 ngày.
- `source=gemini_editor` nghĩa là đã qua writer + editor; `curated_reserve` nghĩa là câu dự phòng. Đừng coi CI xanh mà reserve xuất hiện là đã xác nhận Gemini hoạt động.
- `data/history.json` chỉ lưu hành động đã đăng; không bị sửa bởi preview. Cấu trúc cũ vẫn đọc được.
- Nếu API publish thành công nhưng push lịch sử thất bại, cần đối chiếu log/tài khoản trước khi chạy lại. Bản này không hứa exactly-once khi cả API và git gặp lỗi; không tự retry lệnh publish mơ hồ.

## Tham khảo

- [Tài liệu Meta Threads chính thức](https://www.postman.com/meta/threads/overview)
- [Meta: dữ liệu về cách nội dung được xem trên Threads](https://about.fb.com/news/2024/10/find-your-community-with-new-threads-educational-insights/)
- [Gemini model](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) và [pricing/quota](https://ai.google.dev/gemini-api/docs/pricing)
- [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

