# Nghiên cứu và thiết kế nội dung v2
Ngày đối chiếu nguồn: 11/11/2026. Đối tượng thử nghiệm: sinh viên/người mới đi làm 18–24 nói tiếng Việt trên Threads. Đây là hướng định vị để thử, chưa phải kết luận nhân khẩu học của tài khoản.

## 1. Số liệu thực sự nói gì?

Báo cáo tài khoản do chủ kênh cung cấp (12/10–10/11/2026) có 664 views, 603 viewers, 3 interactions, net followers 0; tất cả 603 viewers được ghi là non-followers. Tỷ số 3/664 xấp xỉ 0,45%, nhưng đó là tỷ số tổng tương tác/lượt xem, không phải tỷ lệ người tương tác độc nhất. Báo cáo không cho biết views/replies từng bài hoặc tuổi, giới tính. Không suy ra được tỉ lệ giữ chân hay CTR từ dữ liệu này.

Repository ghi 5 bài chính từ 8–10/11 UTC, độ dài 127–313 ký tự, trung bình 233. Ba bài cùng bối cảnh quán trà đá. Bài mới nhất 127 ký tự là fallback viết sẵn. Log GitHub của run 42893501263 xác nhận Gemini HTTP 503, sau đó chọn fallback. Quan sát “bài mới nhất có giọng tốt hơn” hợp lý ở góc biên tập; chưa có đủ số liệu để nói nó hiệu quả nhất.

Các khung giờ nổi bật trong PDF là thứ Hai 19–22h, Chủ nhật 16–19h, thứ Ba 4–7h, nhưng chỉ dựa trên vài ngày. Giờ đăng thực tế trong history cũng lệch giờ cron dự kiến. Không chọn “giờ vàng” từ mẫu này; giữ lịch 11:45/20:00 để thử nhất quán và ghi thời gian thực tế.

## 2. Thị trường và giới hạn của nghiên cứu

Decision Lab [Connected Consumer Q4/2024](https://www.decisionlab.co/connected_consumer_q4_2024) ghi nhận Threads tăng sức hút ở Gen Z. Trang tổng quan [Q4/2025](https://www.decisionlab.co/decision-lab-connected-consumer-q4-2025) công bố tỷ lệ sử dụng Threads 23% trong khảo sát của họ. Đây là mức dùng trong mẫu khảo sát, không phải số MAU hoặc phần trăm mọi người Việt. Không dùng kết quả đó để đoán mọi Gen Z đều thích cùng một giọng.

Meta công bố [insights cho creator ngày 1/10/2024](https://about.fb.com/news/2024/10/find-your-community-with-new-threads-educational-insights/): nội dung hài có xu hướng được xem nhiều hơn; bài tạo hội thoại có khả năng được đề xuất; reply chiếm gần nửa views trên nền tảng. Đây là dữ liệu nền tảng toàn cầu, không phải thí nghiệm riêng với Gen Z Việt, và không có nghĩa mỗi comment tự cộng một lượng reach cố định. Meta cũng khuyến khích nội dung nguyên bản làm riêng cho Threads.

Nguồn công khai + 4 ví dụ thành công chủ kênh chọn + 5 bài của kênh là nghiên cứu bàn giấy và phân tích định tính. Chưa phải khảo sát đại diện, nghiên cứu social listening quy mô lớn hay phân tích toàn bộ feed. Các ví dụ đã được chọn vì thành công nên có thiên lệch sống sót. Không có mẫu bài tương tự nhưng thất bại để ước lượng xác suất viral.

## 3. Giải mã ví dụ

| Ví dụ chủ kênh cung cấp | Cơ chế đọc có thể hoạt động | Rút ra cho kênh |
|---|---|---|
| Xếp hạng kiểu em theo game | Người đọc tìm mình/người quen trong nhóm; mỗi mục có chi tiết riêng và đánh giá để bất đồng | Mượn cấu trúc phân loại vui, không chép câu hay miệt thị nhóm người |
| “Bé thích laptop, lớn không muốn mở” | Hai vế đảo kỳ vọng, trải nghiệm dễ nhận ra, kết thúc ngay sau cú chốt | Câu ngắn có thể đủ nếu ý đã trọn; không cần thêm một đoạn triết lý |
| Mẹ khen sửa wifi, thực tế bật/tắt | Khoảng cách giữa hình ảnh của bố mẹ và hành động đơn giản; ảnh là phần trả lời | Dùng tương phản/đoạn thoại; bản text phải có cú chốt riêng khi chưa có ảnh |
| Câu chuyện tình cảm có người chưa thành niên | Dễ kích tò mò và tranh luận, nhưng chứa yếu tố tuổi tác/đời tư không phù hợp để bot bắt chước | Không dùng làm mẫu sinh nội dung; giới hạn nhân vật hẹn hò là người lớn |

Không phải ví dụ nào cũng ngắn. Bài xếp hạng dài nhưng mỗi dòng đem lại một chi tiết mới. Vấn đề chính của kênh cũ là mật độ ý thấp, cảnh và kết luận lặp, không phải vượt một ngưỡng chữ thần kỳ.

## 4. Tâm lý → lựa chọn biên tập

[Berger & Milkman, What Makes Online Content Viral?, JMR 2012](https://jonahberger.com/wp-content/uploads/2013/02/ViralityB.pdf) phân tích bài New York Times và thí nghiệm về cảm xúc: mức kích hoạt cảm xúc có liên hệ với chia sẻ, không chỉ chiều tích cực/tiêu cực. Không thể lấy hệ số từ bài báo đó làm mô hình dự báo Threads Việt. Ứng dụng ở đây là tăng ngạc nhiên vui, nhận ra chính mình, và nhầm kỳ vọng; không lấy giận dữ làm mục tiêu.

[Loewenstein, The Psychology of Curiosity, 1994](https://www.cmu.edu/dietrich/sds/docs/loewenstein/PsychofCuriosity.pdf) mô tả tò mò khi nhận ra khoảng thiếu trong hiểu biết. Ứng dụng là đặt tình huống cụ thể rồi trả lời bằng cú chốt ngay trong bài. Không giấu lời giải để ép người đọc vào comment.

Các giả thuyết biên tập sau cần kiểm chứng ở tài khoản này:

- Nhận diện bản thân: “đây là mình/đứa bạn mình” dễ tạo lý do chia sẻ hơn một cảnh không có mâu thuẫn.
- Chi phí đọc: câu đầu rõ tình huống giúp người lướt hiểu ngay. 60–180 ký tự là vùng ưu tiên để thử, không phải quy tắc nền tảng.
- Điểm chen vào: một ý kiến nhỏ về cách sống/khẩu vị cho người đọc chỗ bổ sung trải nghiệm. Không nhất thiết đặt câu hỏi.
- Giọng ngang hàng: slang là nhịp nói và quan hệ với người đọc. Thêm =)) vào văn mẫu không biến nó thành giọng Gen Z.
- Drama nhẹ: tranh phần đồ ăn, chọn quán, seen tin nhắn, mẹ nhắc việc nhà. Mâu thuẫn rõ mà không cần bịa người có lỗi hoặc tai nạn.

## 5. Thay đổi đã áp dụng

| Điểm yếu v1 | Cơ chế v2 |
|---|---|
| Một output là đăng | Một batch tối đa 6 phương án; gọi biên tập riêng trước khi chọn |
| Không nhìn bài cũ | Truyền 20 bài gần nhất; đổi topic; chặn mô-típ/câu trùng |
| Mặc định văn nhật ký 80–450 ký tự | Ưu tiên 60–180 ký tự, biên 35–360; nhiều dạng có điểm rơi |
| Trà đá, mưa, deadline quay lại liên tục | Chủ đề gia đình, digital, bạn bè, đồ ăn, adulting, hẹn hò người lớn, campus |
| Lỗi model bị fallback che khuất | Audit nguồn bài, lỗi; retry ngắn; hết reserve thì bỏ lượt |
| Trend là 2 tiêu đề đầu RSS | Lọc thời gian/liên quan, Threads keyword search tùy quyền; không coi đó là chân lý |
| Không có đo từng bài | Collector checkpoint 24–48h và 72–96h khi cấp quyền insights |
| Reply lịch sự máy móc, cap tính theo lượt | Trả lời vào chi tiết cụ thể, biên tập riêng, cap theo ngày, bỏ reply của chính bot |

Điểm nội bộ 68/100 là ngưỡng biên tập khởi đầu (hook 30%, voice 30%, payoff 30%, conversation 10%), không phải kết quả học từ 5 bài và không phải “68% cơ hội viral”. Model không tự viết điểm cho chính output trong lượt writer; editor là một lượt gọi khác cùng model. Hai lượt vẫn có thể có lỗi tương quan.

## 6. Trend có thể biết đến đâu?

Google Trends VN đo quan tâm tìm kiếm; không đại diện slang hoặc toàn bộ feed Threads Gen Z. Filter có thể bỏ sót trend hay. Không có tín hiệu phù hợp thì viết evergreen.

API [keyword search của Meta](https://www.postman.com/meta/threads/request/34203612-b3b2c12a-7ce6-4d86-a3c6-6d31e3b66ea1) cho phép quan sát bài tìm theo từ khóa với quyền phù hợp, không cung cấp một bản sao For You cá nhân. Bot chỉ lấy tín hiệu, không đi copy bài viral hay tự bình luận vào tài khoản lạ. Muốn bật cần kiểm tra scope threads_keyword_search và yêu cầu quyền theo trạng thái app.

Gemini 3.5 Flash-Lite có free tier trong [pricing hiện hành](https://ai.google.dev/gemini-api/docs/pricing); [model catalog](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) ghi hỗ trợ structured output. Hạn mức thực xem theo project trong AI Studio. Bản này không dựa vào Google Search Grounding có phí/quyền khác; không hứa quota vô hạn.

## 7. Kế hoạch 14 ngày: tăng giá trị trò chuyện, không tối ưu số comment bằng mọi giá

Giữ 2 bài/ngày. Xoay vòng 6 dạng, không tăng dồn bài sau một lần có reach cao. Ghi source, topic, format, thời gian thực và tuổi bài khi thu số liệu.

Khi token có threads_manage_insights, collector đọc [post insights chính thức](https://www.postman.com/meta/threads/request/34203612-385abc7d-b3cc-4e5d-9937-ebbe7174e041). So riêng các snapshot trong cùng cửa sổ tuổi bài; không lấy bài 3 ngày so bài 2 giờ. Dùng median views/bài, replies/1.000 views và (reposts+quotes)/1.000 views. Xem cả số tuyệt đối để tránh rate cao từ vài views. Net followers hiện là số cấp tài khoản, không tự quy công cho từng bài.

Trong 28 bài dự kiến, mỗi format chỉ có vài lần lặp nên kết quả vẫn là thăm dò. Không tự tuyên bố thắng hay chuyển hết sang một dạng chỉ vì một outlier. Tách reserve khỏi output Gemini khi đánh giá. Sau khoảng 5–10 bài trưởng thành mỗi dạng và nhiều ngày, mới cân nhắc thay tỷ trọng; vẫn phải giữ khám phá. Đây không phải ngưỡng đảm bảo ý nghĩa thống kê.

Lượt author/editor đầu tiên trên main sẽ được CI chạy preview bằng key Gemini có sẵn, không nhận Threads token. Tests cục bộ kiểm tra cấu trúc, lỗi và đường đăng giả lập; chất lượng ngoài thực tế chỉ được xác nhận sau khi xem output thật và dữ liệu tiếp theo.

## 8. Giới hạn pháp lý và vận hành

Cơ chế từ chối tin bịa, vu khống/xúc phạm, công khai đời tư, sao chép nguồn và nội dung liên quan trẻ chưa thành niên. [Báo Chính phủ ngày 21/5/2026](https://baochinhphu.vn/cung-cap-chia-se-thong-tin-gia-mao-sai-su-that-tren-mang-xa-hoi-bi-phat-den-50-trieu-dong-102260521112648563.htm) tóm tắt quy định mới về trách nhiệm dùng mạng xã hội, bao gồm thông tin giả, danh dự và bí mật đời tư; xem [Nghị định 147/2024](https://vanban.chinhphu.vn/?classid=1&docid=211654&orggroupid=2&pageid=27160) để tham khảo khung quản lý dịch vụ. Báo cáo này không diễn giải đủ mọi văn bản hoặc chứng nhận tuân thủ pháp luật.

Bộ lọc keyword không thể hiểu mọi tiếng lóng/ẩn ý; editor cũng có thể sai. Chọn vùng nội dung ít rủi ro thay vì gắn nhãn “hư cấu” rồi coi mọi drama đều được phép. Nếu có sự cố, đặt DRY_RUN=true qua repository variables, gỡ hoặc sửa bài cụ thể và kiểm tra nguyên nhân.

Giữ nguyên history, cron người dùng đã đặt, helper lấy token và secrets. Không đăng bài mới chỉ để demo trong lượt nâng cấp này.
