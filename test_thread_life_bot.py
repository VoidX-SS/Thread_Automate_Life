import unittest

import thread_life_bot as bot


class ContentSafetyTests(unittest.TestCase):
    def test_accepts_original_safe_post(self):
        text = "Mình mở laptop với quyết tâm làm bài, rồi dành 20 phút chọn đúng một playlist. Ít nhất hôm nay tai nghe đã năng suất hơn mình."
        self.assertTrue(bot.valid_post(text, []))

    def test_rejects_factual_or_urgent_post(self):
        self.assertFalse(bot.valid_post("Tin khẩn: có 75% sinh viên đang đầu tư ngay hôm nay, theo nguồn tin mới.", []))

    def test_rejects_near_duplicate(self):
        old = "Đi học về mệt, mình tự hứa chỉ nằm 5 phút rồi trời tối."
        new = "Đi học về mệt, mình tự hứa nằm 5 phút và rồi trời tối mất."
        self.assertTrue(bot.too_similar(new, [{"text": old}]))

    def test_replies_reject_sensitive_topics(self):
        self.assertFalse(bot.safe_reply("Bạn thử đầu tư coin ngay đi nha, lời lắm."))
        self.assertTrue(bot.safe_reply("Nghe đúng kiểu một ngày dài thật á. Mong tối nay bạn có được một khoảng thở nhỏ nha."))


if __name__ == "__main__":
    unittest.main()
