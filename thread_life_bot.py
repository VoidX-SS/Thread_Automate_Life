#!/usr/bin/env python3
"""Dependency-free Threads publisher with an editorial content engine."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import email.utils
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import content_engine as engine

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
HISTORY_PATH = DATA / "history.json"
METRICS_PATH = DATA / "metrics.json"
RUN_LOG_PATH = DATA / "last_run.json"
VIETNAM = dt.timezone(dt.timedelta(hours=7))  # Vietnam has no daylight saving time.

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def bounded_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(int(os.getenv(name, str(default))), hi))
    except ValueError:
        return default


def load_json(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return fallback
    # Corrupt persisted history must fail visibly, not erase deduplication state.


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class APIError(RuntimeError):
    def __init__(self, status: int, retry_after: float = 0):
        super().__init__(f"API HTTP {status}")
        self.status = status
        self.retry_after = retry_after


def http_json(url: str, *, method: str = "GET", headers: dict[str, str] | None = None,
              form: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = dict(headers or {})
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("API returned a non-object response")
            return value
    except urllib.error.HTTPError as exc:
        try:
            retry_after = float(exc.headers.get("Retry-After", "0"))
        except (TypeError, ValueError):
            retry_after = 0
        raise APIError(exc.code, retry_after) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("API connection failed; credentials and URL omitted") from None


def http_text(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "trends.google.com":
        raise RuntimeError("Only the documented Google Trends HTTPS feed is enabled")
    request = urllib.request.Request(url, headers={"User-Agent": "ThreadAutomateLife/2.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if urllib.parse.urlparse(response.url).hostname != "trends.google.com":
                raise RuntimeError("Unexpected trend feed redirect")
            return response.read(256_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Trend feed unavailable") from None


def parse_model_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("Model output is not an object")
    return value


def gemini(prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("Invalid model identifier")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.5 if prompt.startswith(engine.EDITOR_RULES) else 1.0,
            "responseMimeType": "application/json",
            "maxOutputTokens": 4096,
        },
    }
    for attempt in range(2):
        try:
            response = http_json(url, method="POST", headers={"x-goog-api-key": api_key}, body=payload)
            break
        except APIError as exc:
            if attempt or exc.status not in {429, 500, 503} or exc.retry_after > 10:
                raise
            time.sleep(max(2, exc.retry_after))
    try:
        candidate = response["candidates"][0]
        if candidate.get("finishReason") not in {None, "STOP"}:
            raise RuntimeError("Gemini output incomplete or blocked")
        # Ignore optional thought parts; only parse the actual final JSON.
        return "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini returned no complete text") from None


def model_json(prompt: str) -> dict[str, Any]:
    return parse_model_json(gemini(prompt))


class Threads:
    def __init__(self) -> None:
        self.token = os.getenv("THREADS_ACCESS_TOKEN", "")
        self.base = os.getenv("THREADS_API_BASE", "https://graph.threads.net/v1.0").rstrip("/")
        parsed = urllib.parse.urlparse(self.base)
        if parsed.scheme != "https" or parsed.hostname != "graph.threads.net":
            raise ValueError("THREADS_API_BASE must be the official HTTPS Threads API")

    def _form(self, path: str, form: dict[str, str]) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("THREADS_ACCESS_TOKEN missing")
        return http_json(f"{self.base}{path}", method="POST",
                         headers={"Authorization": f"Bearer {self.token}"}, form=form)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("THREADS_ACCESS_TOKEN missing")
        query = urllib.parse.urlencode(params)
        return http_json(f"{self.base}{path}?{query}",
                         headers={"Authorization": f"Bearer {self.token}"})

    def publish_text(self, text: str, reply_to_id: str | None = None) -> str:
        form = {"media_type": "TEXT", "text": text}
        if reply_to_id:
            form["reply_to_id"] = reply_to_id
        container = self._form("/me/threads", form)
        creation_id = str(container.get("id", ""))
        if not creation_id:
            raise RuntimeError("Threads returned no container id")
        # Never automatically retry a publish write after an ambiguous network failure.
        published = self._form("/me/threads_publish", {"creation_id": creation_id})
        post_id = str(published.get("id", ""))
        if not post_id:
            raise RuntimeError("Threads returned no post id")
        return post_id

    def replies(self, post_id: str) -> list[dict[str, Any]]:
        return list(self._get(f"/{post_id}/replies",
                    {"fields": "id,text,username,timestamp", "limit": "50"}).get("data", []))

    def profile(self) -> dict[str, Any]:
        return self._get("/me", {"fields": "id,username"})

    def insights(self, post_id: str) -> dict[str, Any]:
        return self._get(f"/{post_id}/insights", {"metric": "views,likes,replies,reposts,quotes"})

    def keyword_search(self, query: str) -> list[dict[str, Any]]:
        return list(self._get("/keyword_search", {
            "q": query, "search_type": "RECENT", "fields": "id,text,timestamp", "limit": "20"
        }).get("data", []))


def iso_time(raw: str) -> dt.datetime | None:
    try:
        value = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=dt.UTC)
    except (ValueError, AttributeError):
        return None


def rss_signals(xml: str, now: dt.datetime) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    results = []
    # Broad Vietnam search interest is NOT equivalent to Vietnamese Gen Z usage.
    relevance = engine.phrase_pattern([
        "game", "gaming", "roblox", "minecraft", "anime", "phim", "nhạc", "concert",
        "meme", "sinh viên", "đi học", "trà sữa", "đồ ăn", "playlist"
    ])
    for item in root.findall(".//item")[:40]:
        title = (item.findtext("title") or "").strip()[:140]
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.UTC)
        except (ValueError, TypeError):
            continue
        if not 0 <= (now - published).total_seconds() <= 48 * 3600:
            continue
        if title and relevance.search(engine.folded(title)) and not engine.RISK.search(engine.folded(title)):
            results.append({"text": title, "source": "google_trends_vn",
                            "observed_at": now.isoformat(), "published_at": published.isoformat()})
    return results[:6]


def trend_signals(now: dt.datetime, seed: str, *, offline: bool = False) -> tuple[list[dict[str, str]], list[str]]:
    if offline:
        return [], []
    signals, errors = [], []
    manual = os.getenv("TREND_HINT", "").strip()[:200]
    if manual:
        signals.append({"text": manual, "source": "operator_hint", "observed_at": now.isoformat()})
    if env_bool("ENABLE_TREND_FEED", True):
        try:
            url = os.getenv("TREND_RSS_URL", "https://trends.google.com/trending/rss?geo=VN")
            signals.extend(rss_signals(http_text(url), now))
        except (RuntimeError, ET.ParseError):
            errors.append("google_trends_unavailable_or_invalid")
    if env_bool("ENABLE_THREADS_TRENDS"):
        queries = ["đi học", "đồ ăn", "game", "tin nhắn", "đi chơi", "đi làm"]
        index = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(queries)
        try:
            for item in Threads().keyword_search(queries[index]):
                published = iso_time(item.get("timestamp", ""))
                text = str(item.get("text", ""))[:240]
                if (published and 0 <= (now - published).total_seconds() <= 48 * 3600
                        and not engine.RISK.search(engine.folded(text))):
                    # Do not persist handles, IDs, full text, or third-party replies publicly.
                    signals.append({"text": text, "source": "threads_keyword_search",
                                    "observed_at": now.isoformat(), "published_at": published.isoformat()})
                if len(signals) >= 10:
                    break
        except RuntimeError:
            errors.append("threads_keyword_search_unavailable_check_permission")
    return signals[:10], errors


def append_history(history: list[dict[str, Any]], item: dict[str, Any]) -> None:
    history.append(item)
    save_json(HISTORY_PATH, history[-200:])


def post_slot(now: dt.datetime) -> str:
    local = now.astimezone(VIETNAM)
    return f"{local.date().isoformat()}:{'am' if local.hour < 16 else 'pm'}"


def run_post(dry_run: bool, *, offline: bool = False, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.UTC)
    history = load_json(HISTORY_PATH, [])
    slot = post_slot(now)
    posts = engine.post_history(history)
    run: dict[str, Any] = {"mode": "post", "dry_run": dry_run, "at": now.isoformat(), "slot": slot}
    if not dry_run:
        today = now.astimezone(VIETNAM).date()
        timestamps = [iso_time(p.get("at", "")) for p in posts]
        count = sum(bool(t and t.astimezone(VIETNAM).date() == today) for t in timestamps)
        if any(p.get("slot") == slot for p in posts) or count >= 2:
            run["skipped"] = "slot_already_published_or_daily_cap"
            save_json(RUN_LOG_PATH, run)
            return run
    signals, errors = trend_signals(now, slot, offline=offline)
    chosen = engine.compose(history, model_json, trends=signals,
                            metrics=load_json(METRICS_PATH, {}), seed=slot, offline=offline,
                            topic_seed=os.getenv("TOPIC_SEED", ""))
    run.update(chosen)
    run["trend_source_counts"] = dict(Counter(x["source"] for x in signals))
    run.setdefault("audit", {}).setdefault("errors", []).extend(errors)
    if not dry_run and not run.get("skipped"):
        post_id = Threads().publish_text(run["text"])
        run["post_id"] = post_id
        append_history(history, {k: v for k, v in {**run, "id": post_id}.items() if k != "audit"})
    save_json(RUN_LOG_PATH, run)
    return run


def metrics_values(response: dict[str, Any]) -> dict[str, int]:
    out = {}
    for row in response.get("data", []):
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        values = row.get("values", [])
        value = values[0].get("value") if values and isinstance(values[0], dict) else None
        if name in {"views", "likes", "replies", "reposts", "quotes"} and type(value) is int and value >= 0:
            out[name] = value
    return out


def collect_insights(dry_run: bool, *, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.UTC)
    if not env_bool("ENABLE_INSIGHTS"):
        return {"mode": "insights", "skipped": "ENABLE_INSIGHTS is false"}
    history = load_json(HISTORY_PATH, [])
    metrics = load_json(METRICS_PATH, {"version": 1, "snapshots": {}})
    snapshots = metrics.setdefault("snapshots", {})
    fetched, errors = 0, []
    client = Threads()
    for post in engine.post_history(history)[-40:]:
        created = iso_time(post.get("at", ""))
        pid = str(post.get("id", post.get("post_id", "")))
        if not created or not pid:
            continue
        age = (now - created).total_seconds() / 3600
        checkpoint = "h24" if 24 <= age < 48 else "h72" if 72 <= age < 96 else None
        if not checkpoint or checkpoint in snapshots.get(pid, {}):
            continue
        try:
            values = metrics_values(client.insights(pid))
            if set(values) != {"views", "likes", "replies", "reposts", "quotes"}:
                errors.append("incomplete_metrics_for_" + pid)
                continue
            snapshots.setdefault(pid, {})[checkpoint] = {
                **values, "collected_at": now.isoformat(), "age_hours": round(age, 2),
                "source": "threads_api", "format": post.get("format", "legacy")
            }
            fetched += 1
        except RuntimeError:
            errors.append("insights_unavailable_check_threads_manage_insights")
            break
    if not dry_run:
        save_json(METRICS_PATH, metrics)
    return {"mode": "insights", "dry_run": dry_run, "fetched": fetched, "errors": errors,
            "performance": engine.performance_context(history, metrics)}


def run_replies(dry_run: bool) -> dict[str, Any]:
    insights = collect_insights(dry_run)
    if not env_bool("ENABLE_REPLIES"):
        run = {"mode": "reply", "dry_run": dry_run, "skipped": "ENABLE_REPLIES is false", "insights": insights}
        save_json(RUN_LOG_PATH, run)
        return run
    history = load_json(HISTORY_PATH, [])
    now = dt.datetime.now(dt.UTC)
    today = now.astimezone(VIETNAM).date()
    already = {str(x.get("reply_to_id")) for x in history if x.get("reply_to_id")}
    today_sent = sum(bool(x.get("reply_to_id") and iso_time(x.get("at", ""))
                         and iso_time(x["at"]).astimezone(VIETNAM).date() == today) for x in history)
    cap = max(0, bounded_int("REPLY_DAILY_CAP", 3, 0, 5) - today_sent)
    sent, inspected = [], 0
    client = Threads()
    if cap:
        own_username = str(client.profile().get("username", "")).casefold()
        own_ids = {str(x.get("id")) for x in history}
        for post in reversed(engine.post_history(history)[-10:]):
            if len(sent) >= cap or inspected >= 8:
                break
            for comment in client.replies(str(post["id"])):
                rid = str(comment.get("id", ""))
                if (not rid or rid in already or rid in own_ids or
                        str(comment.get("username", "")).casefold() == own_username):
                    continue
                inspected += 1
                text = engine.reply_text(str(comment.get("text", "")), str(post.get("text", "")), model_json)
                if text and not engine.too_similar(text, [x for x in history if x.get("reply_to_id")]):
                    item = {"mode": "reply", "at": now.isoformat(), "reply_to_id": rid, "text": text,
                            "dry_run": dry_run, "source": "gemini_editor", "engine_version": "2.0"}
                    if not dry_run:
                        item["id"] = client.publish_text(text, reply_to_id=rid)
                        append_history(history, item)
                    sent.append(item)
                already.add(rid)
                if len(sent) >= cap or inspected >= 8:
                    break
    run = {"mode": "reply", "dry_run": dry_run, "at": now.isoformat(), "sent": sent, "insights": insights}
    save_json(RUN_LOG_PATH, run)
    return run


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("post", "reply", "insights"), default="post")
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument("--live", action="store_true")
    switch.add_argument("--dry-run", action="store_true", help="Force preview even if DRY_RUN=false")
    parser.add_argument("--offline", action="store_true", help="Preview reserves with zero network calls")
    args = parser.parse_args()
    if args.offline and (args.live or args.mode != "post"):
        parser.error("--offline is only valid for post previews")
    dry_run = True if args.dry_run or args.offline else False if args.live else env_bool("DRY_RUN", True)
    if args.mode == "post":
        run = run_post(dry_run, offline=args.offline)
    elif args.mode == "reply":
        run = run_replies(dry_run)
    else:
        run = collect_insights(dry_run)
        save_json(RUN_LOG_PATH, run)
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

