import datetime as dt
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

import content_engine as e
import thread_life_bot as b

NOW = dt.datetime(2026, 11, 21, 13, 30, tzinfo=dt.timezone.utc)


def review(cid, **changes):
    base = {
        "id": cid,
        "approve": True,
        "fact_grounded": True,
        "format_matched": True,
        "risks": [],
        "scores": {"hook": 4, "clarity_depth": 4, "voice": 4, "conversation": 4},
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
    def test_seed_bank_has_200_valid_unique_seeds(self):
        seeds = e.seed_bank()
        self.assertEqual(len(seeds), 200)
        self.assertEqual(len({s["id"] for s in seeds}), 200)
        pillars = {s["pillar"] for s in seeds}
        self.assertEqual(pillars, {"dilemma", "brain_glitch", "philosophy", "human_paradox"})
        for s in seeds:
            if s["preferred_format"] == "dilemma_poll":
                self.assertGreaterEqual(len(s["poll_hint"]), 2, s["id"])
                for opt in s["poll_hint"]:
                    self.assertLessEqual(len(opt), 25, f"{s['id']}: {opt}")

    def test_all_curated_reserves_pass_gate(self):
        cfg = e.config()
        for row in e.RESERVES:
            reasons = e.gate(
                row["text"],
                [],
                cfg,
                fmt=row["format"],
                followup_reply=row.get("followup_reply", ""),
                poll_options=row.get("poll_options", []),
                seed_id=row["seed_id"],
            )
            self.assertEqual(reasons, [], f"Reserve failed: {row['seed_id']} -> {reasons}")

    def test_gate_allows_psychology_facts_and_blocks_risk_bait_cliche(self):
        cfg = e.config()
        good = (
            "Nghiên cứu tâm lý học cho thấy hơn 50% người tham gia không nhìn thấy con khỉ đột đi ngang màn hình "
            "khi đang tập trung đếm số lần chuyền bóng. Bạn từng bỏ lỡ điều hiển nhiên trước mắt bao giờ chưa?"
        )
        self.assertEqual(e.gate(good, [], cfg, fmt="paradox_opener"), [])
        self.assertIn(
            "tone_or_emote_violation",
            e.gate(good + " =))", [], cfg, fmt="paradox_opener"),
        )
        self.assertIn(
            "cliche_or_template_voice",
            e.gate(good + " Thật là một khoảng thở chữa lành.", [], cfg, fmt="paradox_opener"),
        )
        self.assertIn(
            "engagement_bait",
            e.gate("Chấm để nhận tài liệu tâm lý học hành vi siêu hay mà không ai chỉ cho bạn biết đâu nhé các bạn ơi.", [], cfg),
        )
        self.assertIn(
            "sensitive_or_legal_risk",
            e.gate("Hôm nay mình sẽ bóc phốt chuyện ngoại tình của một người nổi tiếng lớp 10 để cả mạng xã hội phân xử.", [], cfg),
        )
        self.assertIn(
            "em_dash_forbidden",
            e.gate(good + " — chi tiết bổ sung.", [], cfg, fmt="paradox_opener"),
        )
        self.assertIn(
            "em_dash_forbidden",
            e.gate(good + " – chi tiết bổ sung.", [], cfg, fmt="paradox_opener"),
        )
        self.assertIn(
            "excessive_quotes",
            e.gate(good + ' Đừng để "áp lực", "lo âu" hay "sợ hãi" lấn át.', [], cfg, fmt="paradox_opener"),
        )

    def test_gate_enforces_poll_and_chain_schemas(self):
        cfg = e.config()
        sample = (
            "Nếu có một cỗ máy giúp bạn sống trọn đời hạnh phúc như thật nhưng bạn sẽ quên mình đang trong máy, "
            "bạn chọn ở lại đời thật hay bước vào cỗ máy này?"
        )
        self.assertIn("invalid_poll_count", e.gate(sample, [], cfg, fmt="dilemma_poll", poll_options=["Chỉ 1 lựa chọn"]))
        self.assertIn(
            "poll_option_too_long",
            e.gate(sample, [], cfg, fmt="dilemma_poll", poll_options=["Lựa chọn này dài quá hai mươi lăm ký tự", "Lựa chọn 2"]),
        )
        self.assertEqual(
            e.gate(sample, [], cfg, fmt="dilemma_poll", poll_options=["Vào máy sống êm", "Ở lại đời thật"]),
            [],
        )
        self.assertIn("invalid_followup_length", e.gate(sample, [], cfg, fmt="brain_hook_chain", followup_reply="quá ngắn"))

    def test_three_stage_pipeline_writer_screener_chief_editor(self):
        briefs = e.make_briefs([], e.config(), "test-seed")
        candidates = []
        for idx, br in enumerate(briefs):
            if br["format"] == "dilemma_poll":
                candidates.append({
                    "id": br["id"],
                    "seed_id": br["seed_id"],
                    "text": f"Bài toán lựa chọn số {idx}: {br['seed']['everyday_angle']} Bạn nghiêng về lựa chọn nào trong hai phương án dưới đây?",
                    "followup_reply": "",
                    "poll_options": br["seed"]["poll_hint"][:2] or ["Phương án A", "Phương án B"],
                })
            elif br["format"] == "brain_hook_chain":
                candidates.append({
                    "id": br["id"],
                    "seed_id": br["seed_id"],
                    "text": f"Cơ chế bộ não số {idx}: {br['seed']['everyday_angle']} Hiện tượng này mang tên {br['seed']['concept']}.",
                    "followup_reply": f"Giải thích ngắn gọn: {br['seed']['verified_fact'][:200]} Bạn đã từng gặp tình huống này lần nào chưa?",
                    "poll_options": [],
                })
            else:
                candidates.append({
                    "id": br["id"],
                    "seed_id": br["seed_id"],
                    "text": f"Góc nhìn số {idx}: {br['seed']['everyday_angle']} Khái niệm {br['seed']['concept']} đặt ra câu hỏi rất đáng suy ngẫm cho đời sống hiện đại.",
                    "followup_reply": "",
                    "poll_options": [],
                })

        roles_called = []

        def fake_model(prompt, *, role="post_writer", temperature=0.7):
            roles_called.append((role, temperature))
            if role == "post_writer":
                return {"candidates": candidates}
            if role == "post_screener":
                return {"screened": [screened("c1", keep=True), screened("c2", keep=True), screened("c3", keep=False, note="nhạt")]}
            if role == "post_chief_editor":
                return {"reviews": [review("c1", scores={"hook": 3, "clarity_depth": 4, "voice": 4, "conversation": 4}),
                                    review("c2", scores={"hook": 5, "clarity_depth": 4, "voice": 4, "conversation": 5})]}
            raise AssertionError(f"Unexpected role: {role}")

        out = e.compose([], fake_model, seed="test-seed")
        self.assertEqual([r[0] for r in roles_called], ["post_writer", "post_screener", "post_chief_editor"])
        self.assertEqual(roles_called[1][1], 0.15)
        self.assertEqual(roles_called[2][1], 0.15)
        self.assertEqual(out["source"], "gemini_editor")
        self.assertEqual(out["id"], "c2")
        self.assertEqual(out["editor_score"], 91.0)

    def test_ungrounded_or_format_mismatch_editor_reviews_rejected(self):
        self.assertIsNone(e.review_score(review("c1", fact_grounded=False)))
        self.assertIsNone(e.review_score(review("c1", format_matched=False)))
        self.assertIsNone(e.review_score(review("c1", risks=["hallucination"])))
        bad = review("c1")
        bad["scores"]["conversation"] = 2
        self.assertIsNone(e.review_score(bad))

    def test_seed_cooldown_prevents_recent_seed_reuse(self):
        seeds = e.seed_bank()
        recent = [{"mode": "post", "seed_id": s["id"], "pillar": s["pillar"], "text": f"old {i}"} for i, s in enumerate(seeds[:100])]
        briefs = e.make_briefs(recent, e.config(), "cooldown-test")
        recent_ids = {s["id"] for s in seeds[:100]}
        self.assertFalse(recent_ids & {b["seed_id"] for b in briefs})

    def test_reply_uses_workhorse_roles_and_requires_approval(self):
        roles = []

        def fake_model(prompt, *, role="reply_writer", temperature=0.7):
            roles.append(role)
            if role == "reply_writer":
                return {"text": "Góc nhìn đó rất thú vị, bạn thấy yếu tố nào khiến mình khó chọn nhất trong hai phương án này?"}
            return {"reviews": [review("reply", approve=True)]}

        rep = e.reply_text("Mình nghĩ chọn giữ ký ức vẫn tốt hơn", "Bài viết gốc về ký ức", fake_model)
        self.assertEqual(roles, ["reply_writer", "reply_editor"])
        self.assertTrue(len(rep) > 20)


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
                "FOLLOWUP_DELAY_SECONDS": "0",
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


class DualModelRouterAndRuntimeTests(FileTestBase):
    def test_router_splits_flagship_and_workhorse_and_respects_20_cap(self):
        # Pre-fill 19 flagship calls today -> only 1 flagship call left before cap=20
        day_vn = NOW.astimezone(b.VIETNAM).date().isoformat()
        b.save_json(b.QUOTA_PATH, {"version": 1, "days": {day_vn: {"gemini-4-hydrogen": 19}}})

        router = b.ModelRouter(dry_run=False, now=NOW)
        called_models = []

        def fake_gemini(prompt, *, model, temperature=0.7):
            called_models.append(model)
            return json.dumps({"ok": True})

        with patch.object(b, "gemini_call", side_effect=fake_gemini):
            router.call_json("p1", role="post_writer")       # 20th flagship call -> gemini-4-hydrogen
            router.call_json("p2", role="post_screener")     # workhorse -> gemini-3.5-flash-lite
            router.call_json("p3", role="post_writer")       # cap reached (20/20) -> auto fallback flash-lite
            router.call_json("p4", role="post_chief_editor") # workhorse -> gemini-3.5-flash-lite
        router.persist()

        self.assertEqual(
            called_models,
            ["gemini-4-hydrogen", "gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.5-flash-lite"],
        )
        saved_quota = b.load_json(b.QUOTA_PATH, {})
        self.assertEqual(saved_quota["days"][day_vn]["gemini-4-hydrogen"], 20)
        self.assertEqual(saved_quota["days"][day_vn]["gemini-3.5-flash-lite"], 3)
        self.assertEqual(router.trace[2]["fallback"], "flagship_daily_cap_reached")

    def test_router_auto_fallbacks_on_flagship_429(self):
        router = b.ModelRouter(dry_run=False, now=NOW)
        calls = []

        def fake_gemini(prompt, *, model, temperature=0.7):
            calls.append(model)
            if model == "gemini-4-hydrogen":
                raise b.APIError(429)
            return json.dumps({"ok": "from_workhorse"})

        with patch.dict(os.environ, {"FLAGSHIP_MAX_RETRIES": "2"}), \
             patch("time.sleep") as mock_sleep, \
             patch.object(b, "gemini_call", side_effect=fake_gemini):
            out = router.call_json("prompt", role="post_writer")

        self.assertEqual(out, {"ok": "from_workhorse"})
        self.assertEqual(calls, ["gemini-4-hydrogen", "gemini-4-hydrogen", "gemini-3.5-flash-lite"])
        self.assertEqual(router.trace[0]["status"], "ok_after_fallback")
        self.assertEqual(mock_sleep.call_count, 1)
        # Flagship failed all attempts -> no quota deducted for flagship, 1 for workhorse
        self.assertEqual(router.flagship_used_today(), 0)
        self.assertEqual(router.summary()["workhorse_used_today"], 1)

    def test_router_flagship_retries_and_succeeds_without_fallback(self):
        router = b.ModelRouter(dry_run=False, now=NOW)
        attempts = 0

        def fake_gemini(prompt, *, model, temperature=0.7):
            nonlocal attempts
            attempts += 1
            if model == "gemini-4-hydrogen" and attempts == 1:
                raise b.APIError(503)
            return json.dumps({"ok": "from_flagship"})

        with patch.dict(os.environ, {"FLAGSHIP_MAX_RETRIES": "3"}), \
             patch("time.sleep") as mock_sleep, \
             patch.object(b, "gemini_call", side_effect=fake_gemini):
            out = router.call_json("prompt", role="post_writer")

        self.assertEqual(out, {"ok": "from_flagship"})
        self.assertEqual(attempts, 2)
        self.assertEqual(mock_sleep.call_count, 1)
        # Verify delay is in 10s - 60s
        sleep_delay = mock_sleep.call_args[0][0]
        self.assertTrue(10.0 <= sleep_delay <= 60.0)
        self.assertEqual(router.trace[0]["status"], "ok_attempt_2")
        self.assertEqual(router.trace[0]["attempts"], 2)
        # Flagship succeeded on attempt 2 -> 1 quota for flagship, 0 for workhorse
        self.assertEqual(router.flagship_used_today(), 1)
        self.assertEqual(router.summary()["workhorse_used_today"], 0)

    def test_ci_dry_run_skips_flagship_when_disabled(self):
        with patch.dict(os.environ, {"ALLOW_FLAGSHIP_IN_DRY_RUN": "false"}):
            router = b.ModelRouter(dry_run=True, now=NOW)
            with patch.object(b, "gemini_call", return_value='{"ok":true}') as g:
                router.call_json("p", role="post_writer")
            self.assertEqual(g.call_args.kwargs["model"], "gemini-3.5-flash-lite")
            self.assertEqual(router.trace[0]["fallback"], "dry_run_flagship_disabled")

    def test_publish_poll_and_topic_tag_with_400_fallback(self):
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "secret-tok"}):
            # First container call with poll_attachment fails HTTP 400; retry without poll succeeds
            with patch.object(
                b,
                "http_json",
                side_effect=[b.APIError(400), {"id": "container-2"}, {"id": "post-99"}],
            ) as api:
                downgrades = []
                pid = b.Threads().publish_text(
                    "Câu hỏi dilemma",
                    topic_tag="Tâm lý học",
                    poll_options=["Chọn A", "Chọn B"],
                    downgrades_out=downgrades,
                )
        self.assertEqual(pid, "post-99")
        self.assertTrue(downgrades[0].startswith("dropped_topic_tag_kept_poll"))
        self.assertIn("poll_attachment", api.call_args_list[0].kwargs["form"])
        self.assertIn("poll_attachment", api.call_args_list[1].kwargs["form"])
        self.assertNotIn("topic_tag", api.call_args_list[1].kwargs["form"])

    def test_publish_text_retries_on_readiness_error(self):
        with patch.dict(os.environ, {"THREADS_ACCESS_TOKEN": "secret-tok"}), patch("time.sleep"):
            with patch.object(
                b,
                "http_json",
                side_effect=[
                    {"id": "container-1"},
                    b.APIError(400, message="The media is not ready for publishing", subcode=2207027),
                    {"id": "post-ready"},
                ],
            ):
                pid = b.Threads().publish_text("Nội dung thử nghiệm", topic_tag="Tâm lý học")
                self.assertEqual(pid, "post-ready")

    def test_run_post_live_publishes_self_reply_chain_and_persists_quota(self):
        reserve_chain = e.RESERVES[0]  # brain_hook_chain with followup_reply
        with patch.object(e, "compose", return_value={
            **reserve_chain, "topic": reserve_chain["pillar"], "source": "gemini_editor",
            "editor_score": 88.0, "engine_version": "3.0", "audit": {"errors": []},
        }), patch.object(b, "Threads") as api:
            api.return_value.publish_text.side_effect = ["main-post-1", "followup-post-2"]
            out = b.run_post(False, now=NOW)

        self.assertEqual(out["post_id"], "main-post-1")
        self.assertEqual(out["followup_post_id"], "followup-post-2")
        self.assertEqual(api.return_value.publish_text.call_count, 2)
        second_call = api.return_value.publish_text.call_args_list[1]
        self.assertEqual(second_call.kwargs["reply_to_id"], "main-post-1")
        saved = b.load_json(b.HISTORY_PATH, [])
        self.assertEqual(saved[-1]["followup_post_id"], "followup-post-2")

    def test_offline_has_zero_network_and_does_not_mutate_history(self):
        with patch.dict(os.environ, {"DRY_RUN": "false"}), patch.object(b, "http_json") as api, patch(
            "sys.argv", ["bot", "--offline"]
        ), patch("sys.stdout", new=io.StringIO()):
            self.assertEqual(b.main(), 0)
        api.assert_not_called()
        self.assertFalse(b.HISTORY_PATH.exists())
        self.assertTrue(b.load_json(b.RUN_LOG_PATH, {})["dry_run"])

    def test_insights_collects_pillar_and_format(self):
        b.save_json(b.HISTORY_PATH, [{
            "id": "p1", "mode": "post", "at": (NOW - dt.timedelta(hours=26)).isoformat(),
            "source": "gemini_editor", "format": "dilemma_poll", "pillar": "dilemma", "text": "x",
        }])
        resp = {"data": [{"name": k, "values": [{"value": v}]} for k, v in
                         {"views": 250, "likes": 12, "replies": 9, "reposts": 3, "quotes": 1}.items()]}
        with patch.dict(os.environ, {"ENABLE_INSIGHTS": "true"}), patch.object(b, "Threads") as api:
            api.return_value.insights.return_value = resp
            out = b.collect_insights(False, now=NOW)
        self.assertEqual(out["fetched"], 1)
        self.assertIn("dilemma", out["performance"]["pillars"])
        self.assertIn("dilemma_poll", out["performance"]["formats"])

    def test_http_error_redacts_provider_body(self):
        error = urllib.error.HTTPError("https://x", 403, "denied", {}, io.BytesIO(b"secret-test-token"))
        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(b.APIError) as result:
                b.http_json("https://example.com")
        self.assertNotIn("secret-test-token", str(result.exception))

    def test_run_post_respects_post_daily_cap_and_min_interval(self):
        # 1. Test slot already published
        slot = b.post_slot(NOW)
        b.save_json(b.HISTORY_PATH, [{
            "id": "p0", "mode": "post", "at": (NOW - dt.timedelta(hours=5)).isoformat(),
            "slot": slot, "text": "sample",
        }])
        out = b.run_post(False, now=NOW)
        self.assertEqual(out.get("skipped"), "slot_already_published")

        # 2. Test min interval not elapsed
        b.save_json(b.HISTORY_PATH, [{
            "id": "p0", "mode": "post", "at": (NOW - dt.timedelta(minutes=30)).isoformat(),
            "slot": "other-slot", "text": "sample",
        }])
        with patch.dict(os.environ, {"POST_MIN_INTERVAL_MINUTES": "60"}):
            out = b.run_post(False, now=NOW)
            self.assertEqual(out.get("skipped"), "min_interval_not_elapsed")

        # 3. Test daily cap reached
        today_posts = [
            {"id": f"p{i}", "mode": "post", "at": (NOW - dt.timedelta(hours=i + 1)).isoformat(), "slot": f"s{i}"}
            for i in range(5)
        ]
        b.save_json(b.HISTORY_PATH, today_posts)
        with patch.dict(os.environ, {"POST_DAILY_CAP": "5", "POST_MIN_INTERVAL_MINUTES": "0"}):
            out = b.run_post(False, now=NOW)
            self.assertEqual(out.get("skipped"), "daily_cap_reached")

    def test_run_replies_handles_api_error_gracefully(self):
        b.save_json(b.HISTORY_PATH, [{"id": "post-123", "mode": "post", "at": NOW.isoformat(), "text": "test"}])
        with patch.dict(os.environ, {"ENABLE_REPLIES": "true"}), patch.object(b, "Threads") as api:
            api.return_value.profile.return_value = {"username": "bot"}
            api.return_value.replies.side_effect = b.APIError(400)
            out = b.run_replies(False, now=NOW)
        self.assertEqual(out.get("sent"), [])

    def test_sanitize_text_normalizes_em_dash_and_spaces(self):
        raw = "Vế một — vế hai – vế ba  --  vế bốn   kết thúc."
        cleaned = e.sanitize_text(raw)
        self.assertNotIn("—", cleaned)
        self.assertNotIn("–", cleaned)
        self.assertNotIn("--", cleaned)
        self.assertEqual(cleaned, "Vế một, vế hai, vế ba, vế bốn kết thúc.")

    def test_gate_allows_concept_single_quotes(self):
        cfg = e.config()
        text_with_single_quotes = (
            "Thí nghiệm 'Mạng che Vô minh': bạn không biết mình sẽ sinh ra 'giàu' hay 'nghèo', 'khỏe' hay 'yếu'. "
            "Nếu được thiết kế lại luật chơi từ đầu, bạn dám bấm nút thử không?"
        )
        self.assertEqual(e.gate(text_with_single_quotes, [], cfg, fmt="thought_experiment"), [])

    def test_gemini_call_raises_on_non_stop_finish_reason(self):
        resp = {
            "candidates": [
                {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "truncated"}]}}
            ]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}), patch.object(b, "http_json", return_value=resp):
            with self.assertRaises(RuntimeError) as ctx:
                b.gemini_call("prompt", model="gemini-4-hydrogen")
            self.assertIn("finishReason=MAX_TOKENS", str(ctx.exception))



if __name__ == "__main__":
    unittest.main()
