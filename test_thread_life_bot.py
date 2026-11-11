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

NOW = dt.datetime(2026, 11, 11, 13, 30, tzinfo=dt.UTC)

def review(cid, **changes):
    return {"id": cid, "approve": True, "risks": [],
            "scores": {"hook": 4, "voice": 4, "payoff": 4, "conversation": 3}, **changes}

class EditorialTests(unittest.TestCase):
    def test_short_casual_voice_and_all_reserves(self):
        c = e.config()
        self.assertEqual(e.gate("ê tui đang đợi bạn. bạn đang đợi tui nhắn là đã tới.", [], c), [])
        for row in e.RESERVES:
            self.assertEqual(e.gate(row["text"], [], c), [], row["text"])

    def test_same_scene_and_copied_external_text(self):
        h = [{"text": "Ngồi quán trà đá ngắm lá rơi, bài tập còn ở nhà."}]
        self.assertIn("recent_motif", e.gate("quán trà chiều nay bình yên quá, tui sắp quên luôn mấy bài chưa làm", h, e.config()))
        source = "đây là một câu ví dụ khá dài để kiểm tra sao chép từ nguồn bên ngoài"
        self.assertIn("copied_source", e.gate(source + " =))", [], e.config(), [source]))

    def test_risk_without_accents_and_minor_romance(self):
        for text in ("tui sap boc phot mot nguoi noi tieng cho cmay biet day ne",
                     "em lớp 10 còn anh 22 tuổi, cả hai quen qua mạng rồi gặp nhau"):
            self.assertIn("sensitive_or_legal_risk", e.gate(text, [], e.config()))

    def test_bait_rejected(self):
        self.assertIn("claim_or_engagement_bait", e.gate("chấm để tui kể câu chuyện chỉ ai từng trải qua mới hiểu nha", [], e.config()))

    def test_writer_receives_history_and_editor_selects_unchanged_text(self):
        rows = [{"id": f"c{i+1}", "text": r["text"]} for i,r in enumerate(e.RESERVES[:6])]
        model = Mock(side_effect=[{"candidates": rows}, {"reviews": [review("c2")]}])
        h = [{"text": "một bài cũ riêng để kiểm tra lịch sử được truyền vào"}]
        out = e.compose(h, model, seed="test")
        self.assertIn(h[0]["text"], model.call_args_list[0].args[0])
        self.assertTrue(model.call_args_list[1].args[0].startswith(e.EDITOR_RULES))
        self.assertEqual((out["source"],out["text"]), ("gemini_editor",rows[1]["text"]))

    def test_missing_rejected_duplicate_or_wrongly_typed_editor_results(self):
        for reviews in ([], [review("c1",approve="false")], [review("c1",risks=["defamation"])],
                        [review("c1"),review("c1")]):
            model = Mock(side_effect=[{"candidates":[{"id":"c1","text":e.RESERVES[0]["text"]}]},{"reviews":reviews}])
            self.assertEqual(e.compose([],model,seed="test")["source"],"curated_reserve")

    def test_bad_scores_fail_closed(self):
        for value in (True,float("nan"),6,-1,"5",None):
            row=review("c1"); row["scores"]["hook"]=value
            self.assertIsNone(e.review_score(row))

    def test_failure_provenance_redacts_error_and_exhaustion_skips(self):
        out=e.compose([],Mock(side_effect=RuntimeError("secret-token")),seed="outage")
        self.assertEqual(out["source"],"curated_reserve")
        self.assertNotIn("secret-token",json.dumps(out))
        self.assertTrue(out["audit"]["errors"])
        out=e.compose([{"text":r["text"]} for r in e.RESERVES],Mock(),seed="x",offline=True)
        self.assertEqual(out["skipped"],"no_fresh_approved_content")

    def test_briefs_avoid_recent_topics_and_explore_formats(self):
        briefs=e.make_briefs([{"topic":"food"},{"topic":"digital"}],e.config(),"seed")
        self.assertFalse({"food","digital"} & {x["topic"] for x in briefs})
        self.assertEqual(len({x["format"] for x in briefs}),6)

    def test_malformed_candidate_does_not_crash_or_publish(self):
        model=Mock(return_value={"candidates":[{"id":[],"text":"bad"}]})
        self.assertEqual(e.compose([],model,seed="x")["source"],"curated_reserve")

    def test_reply_requires_editor_approval(self):
        model=Mock(side_effect=[{"text":"ê tui cũng hay quên đúng lúc cần nhớ nhất =))"},
                                {"reviews":[review("reply",approve=False,risks=["tone"])]}])
        self.assertEqual(e.reply_text("công nhận luôn","một bài cũ",model),"")

class FileTestBase(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        p=patch.dict(os.environ,{"ENABLE_INSIGHTS":"false","ENABLE_REPLIES":"false",
                                "ENABLE_TREND_FEED":"false","ENABLE_THREADS_TRENDS":"false"},clear=True)
        p.start(); self.addCleanup(p.stop)
        for key,name in (("HISTORY_PATH","history.json"),("METRICS_PATH","metrics.json"),("RUN_LOG_PATH","last_run.json")):
            p=patch.object(b,key,root/name); p.start(); self.addCleanup(p.stop)

class RuntimeTests(FileTestBase):
    def test_dry_run_does_not_publish_or_modify_history(self):
        with patch.object(b,"model_json",side_effect=RuntimeError("offline")),patch.object(b,"Threads") as client:
            out=b.run_post(True,now=NOW)
        client.assert_not_called(); self.assertFalse(b.HISTORY_PATH.exists())
        self.assertEqual(out["source"],"curated_reserve")

    def test_offline_has_zero_network_even_in_live_environment(self):
        with patch.dict(os.environ,{"DRY_RUN":"false"}),patch.object(b,"http_json") as api,patch.object(b,"http_text") as feed,patch("sys.argv",["bot","--offline"]),patch("sys.stdout",new=io.StringIO()):
            self.assertEqual(b.main(),0)
        api.assert_not_called(); feed.assert_not_called()
        self.assertTrue(b.load_json(b.RUN_LOG_PATH,{})["dry_run"])

    def test_explicit_preview_overrides_live_variable(self):
        with patch.dict(os.environ,{"DRY_RUN":"false"}),patch("sys.argv",["bot","--dry-run"]),patch.object(b,"run_post",return_value={}) as run,patch("sys.stdout",new=io.StringIO()):
            b.main()
        run.assert_called_once_with(True,offline=False)

    def test_post_slot_and_daily_cap_checked_before_generation(self):
        for history in ([{"mode":"post","at":NOW.isoformat(),"slot":b.post_slot(NOW),"text":"x"}],
                        [{"mode":"post","at":(NOW-dt.timedelta(hours=i)).isoformat(),"text":str(i)} for i in (1,2)]):
            b.save_json(b.HISTORY_PATH,history)
            with patch.object(b.engine,"compose") as compose,patch.object(b,"Threads") as api:
                self.assertIn("skipped",b.run_post(False,now=NOW))
            compose.assert_not_called(); api.assert_not_called()

    def test_corrupt_history_not_silently_reset(self):
        b.HISTORY_PATH.write_text("{bad",encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError): b.run_post(False,now=NOW)

    def test_publish_contract_and_bearer_header(self):
        with patch.dict(os.environ,{"THREADS_ACCESS_TOKEN":"testsecret"}),patch.object(b,"http_json",side_effect=[{"id":"container"},{"id":"post"}]) as api:
            self.assertEqual(b.Threads().publish_text("test"),"post")
        first,second=api.call_args_list
        self.assertTrue(first.args[0].endswith("/me/threads"))
        self.assertTrue(second.args[0].endswith("/me/threads_publish"))
        self.assertNotIn("access_token",first.kwargs["form"])
        self.assertEqual(first.kwargs["headers"]["Authorization"],"Bearer testsecret")

    def test_ambiguous_publish_failure_not_retried(self):
        with patch.dict(os.environ,{"THREADS_ACCESS_TOKEN":"secret"}),patch.object(b,"http_json",side_effect=[{"id":"container"},RuntimeError("timeout")]) as api:
            with self.assertRaises(RuntimeError): b.Threads().publish_text("test")
        self.assertEqual(api.call_count,2)

    def test_http_error_redacts_provider_body(self):
        error=urllib.error.HTTPError("https://x",403,"denied",{},io.BytesIO(b"secret-test-token"))
        with patch("urllib.request.urlopen",side_effect=error):
            with self.assertRaises(b.APIError) as result: b.http_json("https://example.com")
        self.assertNotIn("secret-test-token",str(result.exception))

    def test_reply_cap_is_daily_across_reruns(self):
        now=dt.datetime.now(dt.UTC)
        b.save_json(b.HISTORY_PATH,[{"mode":"reply","reply_to_id":str(i),"at":now.isoformat()} for i in range(3)])
        with patch.dict(os.environ,{"ENABLE_REPLIES":"true"}),patch.object(b,"Threads") as api:
            self.assertEqual(b.run_replies(False)["sent"],[])
        api.return_value.profile.assert_not_called()

class EvidenceTests(FileTestBase):
    def test_fixed_age_insights_no_duplicate_fetches_no_writes_to_threads(self):
        b.save_json(b.HISTORY_PATH,[{"id":"p1","mode":"post","at":(NOW-dt.timedelta(hours=25)).isoformat(),
                                   "source":"gemini_editor","format":"one_liner","text":"x"}])
        response={"data":[{"name":k,"values":[{"value":v}]} for k,v in
                         {"views":100,"likes":2,"replies":1,"reposts":0,"quotes":0}.items()]}
        with patch.dict(os.environ,{"ENABLE_INSIGHTS":"true"}),patch.object(b,"Threads") as api:
            api.return_value.insights.return_value=response
            out=b.collect_insights(False,now=NOW); b.collect_insights(False,now=NOW)
        self.assertEqual(out["fetched"],1); self.assertEqual(api.return_value.insights.call_count,1)
        api.return_value.publish_text.assert_not_called()
        self.assertEqual(b.load_json(b.METRICS_PATH,{})["snapshots"]["p1"]["h24"]["age_hours"],25)
        self.assertEqual(out["performance"]["status"],"observational_only_no_causal_winner")

    def test_missing_permission_and_missing_metric_do_not_fabricate_data(self):
        self.assertEqual(b.metrics_values({"data":[]}),{})
        b.save_json(b.HISTORY_PATH,[{"id":"p","at":(NOW-dt.timedelta(hours=25)).isoformat(),"text":"x"}])
        with patch.dict(os.environ,{"ENABLE_INSIGHTS":"true"}),patch.object(b,"Threads") as api:
            api.return_value.insights.side_effect=b.APIError(403)
            out=b.collect_insights(False,now=NOW)
        self.assertEqual(out["fetched"],0); self.assertTrue(out["errors"])

    def test_rss_filters_stale_and_irrelevant_signals(self):
        fresh=(NOW-dt.timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        stale=(NOW-dt.timedelta(days=5)).strftime("%a, %d %b %Y %H:%M:%S +0000")
        xml=f"<rss><channel><item><title>game mới</title><pubDate>{fresh}</pubDate></item><item><title>game cũ</title><pubDate>{stale}</pubDate></item><item><title>chứng khoán</title><pubDate>{fresh}</pubDate></item></channel></rss>"
        self.assertEqual([x["text"] for x in b.rss_signals(xml,NOW)],["game mới"])

if __name__ == "__main__":
    unittest.main()

