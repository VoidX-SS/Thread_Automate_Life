import datetime as dt
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import content_engine as e
import thread_life_bot as b

NOW = dt.datetime(2026, 11, 23, 8, 0, tzinfo=dt.timezone.utc)


def review(cid, **changes):
    base = {
        "id": cid,
        "approve": True,
        "fact_grounded": True,
        "format_matched": True,
        "risks": [],
        "scores": {"hook": 4, "clarity_depth": 4, "voice": 4, "share_or_talk": 4},
        "reason": "tốt",
    }
    base.update(changes)
    return base


def screened(cid, **changes):
    base = {
        "id": cid,
        "fact_grounded": True,
        "format_matched": True,
        "not_repetitive": True,
        "keep": True,
        "note": "đạt",
    }
    base.update(changes)
    return base


class SeedBankAndEditorialTests(unittest.TestCase):
    def test_seed_bank_has_200_seeds_with_utf8_25_byte_polls_and_no_em_dash(self):
        seeds = e.seed_bank()
        self.assertEqual(len(seeds), 200)
        self.assertEqual(len({s["id"] for s in seeds}), 200)
        self.assertEqual({s["pillar"] for s in seeds}, {"dilemma", "brain_glitch", "philosophy", "human_paradox"})
        for s in seeds:
            raw = json.dumps(s, ensure_ascii=False)
            self.assertNotIn("—", raw)
            self.assertNotIn("–", raw)
            for opt in s.get("poll_hint", []):
                self.assertLessEqual(e.utf8_len(opt), 25, f"{s['id']} -> {opt} ({e.utf8_len(opt)} bytes)")

    def test_all_reserves_pass_gate(self):
        cfg = e.config()
        for row in e.RESERVES:
            reasons = e.gate(
                row["text"],
                [],
                cfg,
                fmt=row["format"],
                thread_replies=row.get("thread_replies", []),
                poll_options=row.get("poll_options", []),
                seed_id=row["seed_id"],
            )
            self.assertEqual(reasons, [], f"Reserve failed: {row['seed_id']} -> {reasons}")

    def test_gate_enforces_utf8_poll_bytes_and_chain_and_reply_cliche(self):
        cfg = e.config()
        poll_text = "Giả sử có cỗ máy tạo ra cuộc sống hạnh phúc y như thật nhưng bạn quên mình ở trong máy, bạn chọn bên nào?"
        self.assertIn(
            "poll_option_too_long_utf8",
            e.gate(poll_text, [], cfg, fmt="dilemma_poll", poll_options=["Sẵn sàng sống lại y hệt", "Ở lại đời thật"]),
        )
        self.assertEqual(
            e.gate(poll_text, [], cfg, fmt="dilemma_poll", poll_options=["Sống lại y hệt", "Ở lại đời thật"]),
            [],
        )
        self.assertIn(
            "invalid_chain_count",
            e.gate("Vì sao người càng nhạy cảm lại hay tỏ ra lạnh nhạt nhất trong mối quan hệ?", [], cfg, fmt="decode_chain", thread_replies=["Chỉ có một đoạn trả lời đủ sáu mươi ký tự để kiểm tra luật hai đến ba đoạn."]),
        )
        self.assertIn(
            "ai_reply_cliche",
            e.gate("Khoảng cách tâm lý quả thực là lăng kính tốt ngay trong tâm bão.", [], cfg, reply=True),
        )
        self.assertEqual(
            e.gate("Đúng kiểu đứng ngoài thì sáng mắt, tới chuyện mình lại rối bời.", [], cfg, reply=True),
            [],
        )

    def test_compose_uses_repair_pass_before_falling_back_to_reserve(self):
        briefs = e.make_briefs([], e.config(), "repair-seed")
        roles = []

        def build_valid(br):
            fmt = br["format"]
            if fmt == "dilemma_poll":
                return {
                    "id": br["id"],
                    "seed_id": br["seed_id"],
                    "text": f"Tình huống lựa chọn {br['id']}: {br['seed']['everyday_angle']} Bạn chọn hướng nào?",
                    "thread_replies": [],
                    "poll_options": br["seed"]["poll_hint"][:2] or ["Chọn A", "Chọn B"],
                }
            if fmt == "decode_chain":
                return {
                    "id": br["id"],
                    "seed_id": br["seed_id"],
                    "text": f"Có bao giờ bạn tự hỏi vì sao {br['seed']['everyday_angle'][:120]}?",
                    "thread_replies": [
                        f"Cơ chế đằng sau nằm ở {br['seed']['concept']}: {br['seed']['verified_fact'][:160]}",
                        "Hiểu được nhịp vận hành này giúp ta bớt tự trách mình mỗi khi gặp lại. Bạn đã gặp tình huống này chưa?",
                    ],
                    "poll_options": [],
                }
            return {
                "id": br["id"],
                "seed_id": br["seed_id"],
                "text": f"Một sự thật thú vị về con người: {br['seed']['everyday_angle']}",
                "thread_replies": [],
                "poll_options": [],
            }

        def fake_model(prompt, *, role="post_writer", temperature=0.7):
            roles.append(role)
            if role == "post_writer":
                return {"candidates": [{"id": "c1", "seed_id": briefs[0]["seed_id"], "text": "ngắn"}]}
            if role == "post_writer_repair":
                return {"candidates": [build_valid(briefs[0]), build_valid(briefs[1])]}
            if role == "post_screener":
                return {"screened": [screened("c1"), screened("c2")]}
            if role == "post_chief_editor":
                return {"reviews": [review("c1"), review("c2", scores={"hook": 5, "clarity_depth": 4, "voice": 4, "share_or_talk": 5})]}
            raise AssertionError(role)

        out = e.compose([], fake_model, seed="repair-seed")
        self.assertEqual(roles, ["post_writer", "post_writer_repair", "post_screener", "post_chief_editor"])
        self.assertEqual(out["source"], "gemini_editor")
        self.assertTrue(out["audit"]["repair_used"])
        self.assertEqual(out["id"], "c2")

    def test_vietnamese_diacritic_homographs_not_false_positived(self):
        cfg = e.config()
        safe = "Phần lớn các quyết định khó khăn đều khiến bộ não muốn trì hoãn sang ngày mai để trốn cảm giác mất mát."
        self.assertEqual(e.gate(safe, [], cfg, fmt="repost_manifesto"), [])
        self.assertIn("sensitive_or_legal_risk", e.gate(safe + " cặc", [], cfg, fmt="repost_manifesto"))
        self.assertIn("sensitive_or_legal_risk", e.gate(safe + " lồn", [], cfg, fmt="repost_manifesto"))

    def test_reply_blocks_pretentious_text_and_accepts_natural_reply(self):
        def fake_model(prompt, *, role="reply_writer", temperature=0.7):
            if role == "reply_writer":
                return {"text": "Nghe quen ghê, lúc khuyên bạn thì rõ ràng vậy mà tới chuyện mình lại rối."}
            return {"reviews": [review("reply", approve=True)]}

        out = e.reply_text("Mình cũng hay khuyên bạn tốt mà chuyện mình toàn sai", "Bài về Solomon", fake_model)
        self.assertTrue(15 <= len(out) <= 130)


class FileTestBase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        p = patch.dict(
            os.environ,
            {
                "GEMINI_API_KEY": "fake-key",
                "ENABLE_INSIGHTS": "false",
                "ENABLE_REPLIES": "false",
                "ENABLE_TREND_FEED": "false",
                "ENABLE_THREADS_TRENDS": "false",
                "CHAIN_DELAY_SECONDS": "0",
            },
            clear=True,
        )
        p.start()
        self.addCleanup(p.stop)
        for key, name in (
            ("HISTORY_PATH", "history.json"),
            ("METRICS_PATH", "metrics.json"),
            ("QUOTA_PATH", "quota.json"),
            ("RUN_LOG_PATH", "last_run.json"),
        ):
            p = patch.object(b, key, root / name)
            p.start()
            self.addCleanup(p.stop)


class RouterPublishAndInsightsTests(FileTestBase):
    def test_flagship_429_falls_back_immediately_without_sleeping(self):
        router = b.ModelRouter(dry_run=False, now=NOW)
        calls = []

        def fake_gemini(prompt, *, model, temperature=0.7):
            calls.append(model)
            if model == "gemini-4-hydrogen":
                raise b.APIError(429)
            return json.dumps({"ok": True})

        with patch("time.sleep") as mock_sleep, patch.object(b, "gemini_call", side_effect=fake_gemini):
            out = router.call_json("prompt", role="post_writer")

        self.assertEqual(out, {"ok": True})
        self.assertEqual(calls, ["gemini-4-hydrogen", "gemini-3.5-flash-lite"])
        mock_sleep.assert_not_called()
        self.assertEqual(router.trace[0]["attempts"], 1)
        self.assertEqual(router.trace[0]["fallback"], "flagship_error_HTTP429")

    def test_flagship_503_retries_twice_then_succeeds(self):
        router = b.ModelRouter(dry_run=False, now=NOW)
        count = 0

        def fake_gemini(prompt, *, model, temperature=0.7):
            nonlocal count
            count += 1
            if count == 1:
                raise b.APIError(503)
            return json.dumps({"ok": "flagship"})

        with patch("time.sleep") as mock_sleep, patch.object(b, "gemini_call", side_effect=fake_gemini):
            out = router.call_json("prompt", role="post_writer")

        self.assertEqual(out, {"ok": "flagship"})
        self.assertEqual(count, 2)
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertEqual(router.flagship_used_today(), 1)

    def test_publish_trims_poll_options_to_25_utf8_bytes(self):
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "tok"}), patch.object(
            b, "http_json", side_effect=[{"id": "c1"}, {"id": "p1"}]
        ) as api:
            pid = b.Threads().publish_text(
                "Câu hỏi",
                topic_tag="Tâm lý học",
                poll_options=["Sẵn sàng sống lại y hệt luôn", "Muốn đổi cách sống ngay lập tức"],
            )
        self.assertEqual(pid, "p1")
        poll_json = json.loads(api.call_args_list[0].kwargs["form"]["poll_attachment"])
        for val in poll_json.values():
            self.assertLessEqual(e.utf8_len(val), 25)

    def test_run_post_publishes_multi_part_decode_chain_sequentially(self):
        chain_reserve = next(r for r in e.RESERVES if r["format"] == "decode_chain")
        with patch.object(e, "compose", return_value={
            **chain_reserve,
            "topic": chain_reserve["pillar"],
            "source": "gemini_editor",
            "editor_score": 88.0,
            "engine_version": "3.2",
            "audit": {"errors": []},
        }), patch.object(b, "Threads") as api:
            api.return_value.publish_text.side_effect = ["root-1", "reply-2", "reply-3"]
            out = b.run_post(False, now=NOW)

        self.assertEqual(out["post_id"], "root-1")
        self.assertEqual(out["followup_post_ids"], ["reply-2", "reply-3"])
        calls = api.return_value.publish_text.call_args_list
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1].kwargs["reply_to_id"], "root-1")
        self.assertEqual(calls[2].kwargs["reply_to_id"], "reply-2")

    def test_run_post_respects_5_posts_daily_cap(self):
        today_posts = [
            {"id": f"p{i}", "mode": "post", "at": (NOW - dt.timedelta(hours=i * 2 + 1)).isoformat(), "slot": f"s{i}"}
            for i in range(5)
        ]
        b.save_json(b.HISTORY_PATH, today_posts)
        with patch.object(b, "Threads"):
            out = b.run_post(False, now=NOW)
            self.assertEqual(out.get("skipped"), "daily_cap_reached")

    def test_collect_insights_newest_first_continues_past_deleted_post_and_reads_total_value(self):
        b.save_json(b.HISTORY_PATH, [
            {"id": "old-deleted", "mode": "post", "at": (NOW - dt.timedelta(hours=30)).isoformat(), "format": "legacy", "pillar": "legacy", "text": "a"},
            {"id": "new-v32", "mode": "post", "at": (NOW - dt.timedelta(hours=22)).isoformat(), "source": "gemini_editor", "format": "repost_manifesto", "pillar": "human_paradox", "text": "b"},
        ])

        def fake_insights(pid):
            if pid == "old-deleted":
                raise b.APIError(400, message="deleted")
            return {
                "data": [
                    {"name": "views", "values": [{"value": 1200}]},
                    {"name": "likes", "total_value": {"value": 15}},
                    {"name": "replies", "values": [{"value": 4}]},
                    {"name": "reposts", "values": [{"value": 9}]},
                ]
            }

        with patch.dict(os.environ, {"ENABLE_INSIGHTS": "true"}), patch.object(b, "Threads") as api:
            api.return_value.insights.side_effect = fake_insights
            out = b.collect_insights(False, now=NOW)

        self.assertEqual(out["fetched"], 1)
        snaps = b.load_json(b.METRICS_PATH, {})["snapshots"]
        self.assertIn("new-v32", snaps)
        self.assertEqual(snaps["new-v32"]["h24"]["views"], 1200)
        self.assertEqual(snaps["new-v32"]["h24"]["reposts"], 9)
        self.assertEqual(snaps["new-v32"]["h24"]["likes"], 15)
        self.assertTrue(any("old-deleted" in err for err in out["errors"]))

    def test_offline_smoke_zero_network(self):
        with patch.dict(os.environ, {"DRY_RUN": "false"}), patch.object(b, "http_json") as api, patch(
            "sys.argv", ["bot", "--offline"]
        ), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(b.main(), 0)
        api.assert_not_called()
        self.assertFalse(b.HISTORY_PATH.exists())

    def test_workflow_has_no_github_schedule_cron(self):
        yml = (Path(__file__).resolve().parent / ".github" / "workflows" / "threads-bot.yml").read_text(encoding="utf-8")
        self.assertNotIn("schedule:", yml)
        self.assertNotIn("cron:", yml)
        self.assertIn("workflow_dispatch:", yml)
        self.assertIn("repository_dispatch:", yml)


if __name__ == "__main__":
    unittest.main()
