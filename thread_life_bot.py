#!/usr/bin/env python3
"""Dependency-free Threads publisher (v3.0) with Seed-Grounded Engine and Dual-Model Routing.

Model routing:
- Flagship (`gemini-4-hydrogen`, daily cap 20 req/day): post_writer.
- Workhorse (`gemini-3.5-flash-lite`, high quota): post_screener, post_chief_editor, reply_writer, reply_editor,
  CI dry-runs, and automatic fallback whenever flagship hits daily cap or transient errors.
"""
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
QUOTA_PATH = DATA / "quota.json"
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


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class APIError(RuntimeError):
    def __init__(
        self,
        status: int,
        retry_after: float = 0,
        message: str = "",
        code: int | None = None,
        subcode: int | None = None,
    ):
        detail = f": {message}" if message else ""
        if code or subcode:
            detail += f" (code: {code}, subcode: {subcode})"
        super().__init__(f"API HTTP {status}{detail}")
        self.status = status
        self.retry_after = retry_after
        self.message = message
        self.code = code
        self.subcode = subcode


def http_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    form: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 90,
) -> dict[str, Any]:
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
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
            if not isinstance(value, dict):
                raise RuntimeError("API returned a non-object response")
            return value
    except urllib.error.HTTPError as exc:
        msg, err_code, subcode = "", None, None
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "error" in parsed:
                err_obj = parsed["error"]
                if isinstance(err_obj, dict):
                    raw_msg = str(err_obj.get("message", ""))
                    msg = re.sub(r"(token|key|secret)=[^\s&]+", r"\1=[REDACTED]", raw_msg, flags=re.IGNORECASE)
                    err_code = err_obj.get("code")
                    subcode = err_obj.get("error_subcode")
        except Exception:
            pass
        try:
            retry_after = float(exc.headers.get("Retry-After", "0"))
        except (TypeError, ValueError):
            retry_after = 0
        raise APIError(exc.code, retry_after, message=msg, code=err_code, subcode=subcode) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("API connection failed; credentials and URL omitted") from None


def http_text(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "trends.google.com":
        raise RuntimeError("Only the documented Google Trends HTTPS feed is enabled")
    request = urllib.request.Request(url, headers={"User-Agent": "ThreadAutomateLife/3.0"})
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


def gemini_call(prompt: str, *, model: str, temperature: float = 0.7) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", model):
        raise ValueError("Invalid model identifier")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
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
        finish_reason = candidate.get("finishReason")
        if finish_reason not in {None, "STOP"}:
            raise RuntimeError(f"Gemini finishReason={finish_reason}")
        return "".join(p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought"))
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("Gemini returned no complete text") from None


class ModelRouter:
    """Routes roles between Flagship (20 req/day cap) and Workhorse with automatic fallback."""

    def __init__(self, *, dry_run: bool, now: dt.datetime | None = None) -> None:
        cfg = engine.config()
        model_cfg = cfg.get("models", {})
        self.flagship = os.getenv(
            "GEMINI_FLAGSHIP_MODEL",
            model_cfg.get("flagship_default", "gemini-4-hydrogen"),
        ).strip()
        self.workhorse = os.getenv(
            "GEMINI_WORKHORSE_MODEL",
            os.getenv("GEMINI_MODEL", model_cfg.get("workhorse_default", "gemini-3.5-flash-lite")),
        ).strip()
        self.flagship_cap = bounded_int(
            "FLAGSHIP_DAILY_CAP",
            int(model_cfg.get("flagship_daily_cap", 20)),
            0,
            100,
        )
        self.live_reserve = bounded_int(
            "FLAGSHIP_LIVE_RESERVE",
            int(model_cfg.get("flagship_live_reserve", 6)),
            0,
            self.flagship_cap,
        )
        self.roles = dict(model_cfg.get("roles", {
            "post_writer": "flagship",
            "post_screener": "workhorse",
            "post_chief_editor": "workhorse",
            "reply_writer": "workhorse",
            "reply_editor": "workhorse",
        }))
        self.dry_run = dry_run
        self.allow_flagship_dry_run = env_bool("ALLOW_FLAGSHIP_IN_DRY_RUN", True)
        self.now = now or dt.datetime.now(dt.timezone.utc)
        self.day_key = self.now.astimezone(VIETNAM).date().isoformat()
        self.quota = load_json(QUOTA_PATH, {"version": 1, "days": {}})
        self.trace: list[dict[str, Any]] = []

    def _day_bucket(self) -> dict[str, int]:
        days = self.quota.setdefault("days", {})
        return days.setdefault(self.day_key, {})

    def flagship_used_today(self) -> int:
        return int(self._day_bucket().get(self.flagship, 0))

    def _record_usage(self, model: str) -> None:
        bucket = self._day_bucket()
        bucket[model] = int(bucket.get(model, 0)) + 1
        # Keep only the most recent 30 days
        days = self.quota.get("days", {})
        for old_key in sorted(days.keys())[:-30]:
            days.pop(old_key, None)

    def persist(self) -> None:
        if not self.dry_run:
            save_json(QUOTA_PATH, self.quota)

    def _pick_tier(self, role: str) -> tuple[str, str | None]:
        preferred = self.roles.get(role, "workhorse")
        if preferred != "flagship":
            return self.workhorse, None
        used = self.flagship_used_today()
        if self.dry_run and not self.allow_flagship_dry_run:
            return self.workhorse, "dry_run_flagship_disabled"
        effective_cap = max(0, self.flagship_cap - self.live_reserve) if self.dry_run else self.flagship_cap
        if used >= effective_cap:
            reason = "flagship_dry_run_reserve_reached" if self.dry_run else "flagship_daily_cap_reached"
            return self.workhorse, reason
        return self.flagship, None

    def call_json(self, prompt: str, *, role: str = "post_writer", temperature: float = 0.7) -> dict[str, Any]:
        chosen_model, downgrade_reason = self._pick_tier(role)
        try:
            self._record_usage(chosen_model)
            raw = gemini_call(prompt, model=chosen_model, temperature=temperature)
            parsed = parse_model_json(raw)
            self.trace.append({
                "role": role,
                "model": chosen_model,
                "fallback": downgrade_reason,
                "status": "ok",
            })
            return parsed
        except (APIError, RuntimeError, ValueError) as exc:
            # If flagship fails (quota 429, transient 503, or bad JSON), degrade seamlessly to workhorse
            if chosen_model == self.flagship and self.workhorse != self.flagship:
                status = getattr(exc, "status", None)
                err_tag = f"flagship_error_HTTP{status}" if isinstance(status, int) else f"flagship_error_{type(exc).__name__}"
                self._record_usage(self.workhorse)
                raw = gemini_call(prompt, model=self.workhorse, temperature=temperature)
                parsed = parse_model_json(raw)
                self.trace.append({
                    "role": role,
                    "model": self.workhorse,
                    "fallback": err_tag,
                    "status": "ok_after_fallback",
                })
                return parsed
            self.trace.append({
                "role": role,
                "model": chosen_model,
                "fallback": downgrade_reason,
                "status": f"failed:{type(exc).__name__}",
            })
            raise

    def summary(self) -> dict[str, Any]:
        return {
            "day_vn": self.day_key,
            "flagship_model": self.flagship,
            "workhorse_model": self.workhorse,
            "flagship_used_today": self.flagship_used_today(),
            "flagship_daily_cap": self.flagship_cap,
            "workhorse_used_today": int(self._day_bucket().get(self.workhorse, 0)),
            "trace": self.trace,
        }


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
        return http_json(
            f"{self.base}{path}",
            method="POST",
            headers={"Authorization": f"Bearer {self.token}"},
            form=form,
        )

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("THREADS_ACCESS_TOKEN missing")
        query = urllib.parse.urlencode(params)
        return http_json(
            f"{self.base}{path}?{query}",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def _create_container_with_fallback(
        self,
        text: str,
        reply_to_id: str | None = None,
        *,
        topic_tag: str | None = None,
        poll_options: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        downgrades: list[str] = []
        base_form: dict[str, str] = {"media_type": "TEXT", "text": text}
        if reply_to_id:
            base_form["reply_to_id"] = reply_to_id

        clean_tag = ""
        if topic_tag and not reply_to_id:
            clean_tag = re.sub(r"[.&]", "", topic_tag).strip()[:50]

        poll_payload = ""
        if poll_options and not reply_to_id:
            valid = [opt.strip()[:25] for opt in poll_options if opt.strip()][:4]
            if len(valid) >= 2:
                keys = ("option_a", "option_b", "option_c", "option_d")
                poll_payload = json.dumps({keys[i]: valid[i] for i in range(len(valid))}, ensure_ascii=False)

        # Ordered attempts: full -> poll without topic_tag -> topic_tag without poll -> plain TEXT
        attempts: list[tuple[dict[str, str], str]] = []
        full_form = dict(base_form)
        if clean_tag:
            full_form["topic_tag"] = clean_tag
        if poll_payload:
            full_form["poll_attachment"] = poll_payload
        attempts.append((full_form, "full"))

        if poll_payload and clean_tag:
            poll_only = dict(base_form)
            poll_only["poll_attachment"] = poll_payload
            attempts.append((poll_only, "dropped_topic_tag_kept_poll"))

        if poll_payload:
            no_poll = dict(base_form)
            if clean_tag:
                no_poll["topic_tag"] = clean_tag
            attempts.append((no_poll, "dropped_poll_attachment"))
        if clean_tag:
            attempts.append((dict(base_form), "dropped_topic_tag_and_poll"))

        last_exc: Exception | None = None
        errors_seen: list[str] = []
        for idx, (form, label) in enumerate(attempts):
            try:
                container = self._form("/me/threads", form)
                creation_id = str(container.get("id", ""))
                if not creation_id:
                    raise RuntimeError("Threads returned no container id")
                if idx > 0:
                    downgrades.append(f"{label} ({'; '.join(errors_seen)})" if errors_seen else label)
                return creation_id, downgrades
            except APIError as exc:
                last_exc = exc
                errors_seen.append(f"{label}:HTTP{exc.status}:{exc.code}/{exc.subcode}:{exc.message[:80]}")
                if exc.status != 400 or idx == len(attempts) - 1:
                    raise
        raise last_exc or RuntimeError("Container creation failed")

    def publish_text(
        self,
        text: str,
        reply_to_id: str | None = None,
        *,
        topic_tag: str | None = None,
        poll_options: list[str] | None = None,
        downgrades_out: list[str] | None = None,
    ) -> str:
        creation_id, downgrades = self._create_container_with_fallback(
            text, reply_to_id, topic_tag=topic_tag, poll_options=poll_options
        )
        if downgrades_out is not None:
            downgrades_out.extend(downgrades)
        # Never automatically retry /me/threads_publish after an ambiguous network failure.
        published = None
        for attempt in range(3):
            try:
                published = self._form("/me/threads_publish", {"creation_id": creation_id})
                break
            except APIError as exc:
                # Meta returns 400 with subcode 2207027 if media container processing is still IN_PROGRESS
                is_readiness = exc.status == 400 and (exc.subcode == 2207027 or "ready" in exc.message.lower() or attempt < 2)
                if is_readiness and attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
                    continue
                # If enriched container publish failed (e.g. poll rejected by Meta), fall back to plain text
                if (topic_tag or poll_options) and not reply_to_id:
                    if downgrades_out is not None:
                        downgrades_out.append("publish_failed_fallback_to_plain_text")
                    plain_id, _ = self._create_container_with_fallback(text, reply_to_id=None)
                    time.sleep(1.0)
                    published = self._form("/me/threads_publish", {"creation_id": plain_id})
                    break
                raise

        if not published:
            raise RuntimeError("Threads publishing failed")
        post_id = str(published.get("id", ""))
        if not post_id:
            raise RuntimeError("Threads returned no post id")
        return post_id

    def replies(self, post_id: str) -> list[dict[str, Any]]:
        return list(self._get(
            f"/{post_id}/replies",
            {"fields": "id,text,username,timestamp", "limit": "50"},
        ).get("data", []))

    def profile(self) -> dict[str, Any]:
        return self._get("/me", {"fields": "id,username"})

    def insights(self, post_id: str) -> dict[str, Any]:
        return self._get(f"/{post_id}/insights", {"metric": "views,likes,replies,reposts,quotes"})

    def keyword_search(self, query: str) -> list[dict[str, Any]]:
        return list(self._get("/keyword_search", {
            "q": query, "search_type": "RECENT", "fields": "id,text,timestamp", "limit": "20",
        }).get("data", []))

    def refresh_long_lived_token(self) -> dict[str, Any]:
        if not self.token:
            raise RuntimeError("THREADS_ACCESS_TOKEN missing")
        query = urllib.parse.urlencode({"grant_type": "th_refresh_token", "access_token": self.token})
        return http_json(f"https://graph.threads.net/refresh_access_token?{query}")


def iso_time(raw: str) -> dt.datetime | None:
    try:
        value = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    except (ValueError, AttributeError):
        return None


def rss_signals(xml: str, now: dt.datetime) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    results = []
    relevance = engine.phrase_pattern([
        "tâm lý", "não bộ", "triết học", "trí tuệ nhân tạo", "ai", "công nghệ",
        "giáo dục", "hạnh phúc", "cô đơn", "áp lực", "sách", "khoa học"
    ])
    for item in root.findall(".//item")[:40]:
        title = (item.findtext("title") or "").strip()[:140]
        try:
            published = email.utils.parsedate_to_datetime(item.findtext("pubDate") or "")
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
        except (ValueError, TypeError):
            continue
        if not 0 <= (now - published).total_seconds() <= 48 * 3600:
            continue
        if title and relevance.search(engine.folded(title)) and not engine.RISK.search(engine.folded(title)):
            results.append({
                "text": title, "source": "google_trends_vn",
                "observed_at": now.isoformat(), "published_at": published.isoformat(),
            })
    return results[:6]


def trend_signals(now: dt.datetime, seed: str, *, offline: bool = False) -> tuple[list[dict[str, str]], list[str]]:
    if offline:
        return [], []
    signals, errors = [], []
    manual = os.getenv("TREND_HINT", "").strip()[:200]
    if manual:
        signals.append({"text": manual, "source": "operator_hint", "observed_at": now.isoformat()})
    if env_bool("ENABLE_TREND_FEED", False):
        try:
            url = os.getenv("TREND_RSS_URL", "https://trends.google.com/trending/rss?geo=VN")
            signals.extend(rss_signals(http_text(url), now))
        except (RuntimeError, ET.ParseError):
            errors.append("google_trends_unavailable_or_invalid")
    if env_bool("ENABLE_THREADS_TRENDS", False):
        queries = ["tâm lý học", "triết học", "overthinking", "lựa chọn", "não bộ"]
        index = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16) % len(queries)
        try:
            for item in Threads().keyword_search(queries[index]):
                published = iso_time(item.get("timestamp", ""))
                text = str(item.get("text", ""))[:240]
                if (published and 0 <= (now - published).total_seconds() <= 48 * 3600
                        and not engine.RISK.search(engine.folded(text))):
                    signals.append({
                        "text": text, "source": "threads_keyword_search",
                        "observed_at": now.isoformat(), "published_at": published.isoformat(),
                    })
                if len(signals) >= 10:
                    break
        except RuntimeError:
            errors.append("threads_keyword_search_unavailable_check_permission")
    return signals[:10], errors


def append_history(history: list[dict[str, Any]], item: dict[str, Any]) -> None:
    history.append(item)
    save_json(HISTORY_PATH, history[-300:])


def post_slot(now: dt.datetime) -> str:
    local = now.astimezone(VIETNAM)
    return f"{local.date().isoformat()}:h{local.hour:02d}"


def run_post(dry_run: bool, *, offline: bool = False, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    history = load_json(HISTORY_PATH, [])
    slot = post_slot(now)
    posts = engine.post_history(history)
    run: dict[str, Any] = {"mode": "post", "dry_run": dry_run, "at": now.isoformat(), "slot": slot}
    if not dry_run:
        today = now.astimezone(VIETNAM).date()
        valid_timestamps = [t for t in (iso_time(p.get("at", "")) for p in posts) if t is not None]
        today_posts = [t for t in valid_timestamps if t.astimezone(VIETNAM).date() == today]
        post_cap = bounded_int("POST_DAILY_CAP", 5, 1, 20)
        min_interval_minutes = bounded_int("POST_MIN_INTERVAL_MINUTES", 60, 0, 720)

        if len(today_posts) >= post_cap:
            run["skipped"] = "daily_cap_reached"
            save_json(RUN_LOG_PATH, run)
            return run

        if any(p.get("slot") == slot for p in posts):
            run["skipped"] = "slot_already_published"
            save_json(RUN_LOG_PATH, run)
            return run

        if valid_timestamps and min_interval_minutes > 0:
            last_post_at = valid_timestamps[-1]
            elapsed_seconds = (now - last_post_at).total_seconds()
            if elapsed_seconds < min_interval_minutes * 60:
                run["skipped"] = "min_interval_not_elapsed"
                save_json(RUN_LOG_PATH, run)
                return run

    signals, errors = trend_signals(now, slot, offline=offline)
    router = ModelRouter(dry_run=dry_run, now=now)
    chosen = engine.compose(
        history,
        router.call_json,
        trends=signals,
        metrics=load_json(METRICS_PATH, {}),
        seed=slot,
        offline=offline,
        topic_seed=os.getenv("TOPIC_SEED", ""),
        debug=env_bool("CONTENT_DEBUG"),
    )
    router.persist()
    run.update(chosen)
    run["trend_source_counts"] = dict(Counter(x["source"] for x in signals))
    run["model_routing"] = router.summary()
    run.setdefault("audit", {}).setdefault("errors", []).extend(errors)

    if not dry_run and not run.get("skipped"):
        client = Threads()
        downgrades: list[str] = []
        post_id = client.publish_text(
            run["text"],
            topic_tag=run.get("topic_tag"),
            poll_options=run.get("poll_options"),
            downgrades_out=downgrades,
        )
        run["post_id"] = post_id
        if downgrades:
            run["publish_downgrades"] = downgrades
            run.setdefault("audit", {}).setdefault("downgrades", []).extend(downgrades)
        followup = str(run.get("followup_reply", "")).strip()
        if followup:
            delay = bounded_int("FOLLOWUP_DELAY_SECONDS", 10, 0, 30)
            if delay > 0:
                time.sleep(delay)
            try:
                run["followup_post_id"] = client.publish_text(followup, reply_to_id=post_id)
            except RuntimeError:
                run.setdefault("audit", {}).setdefault("errors", []).append("followup_reply_failed")
        persisted = {k: v for k, v in {**run, "id": post_id}.items() if k != "audit"}
        append_history(history, persisted)

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
    now = now or dt.datetime.now(dt.timezone.utc)
    if not env_bool("ENABLE_INSIGHTS"):
        return {"mode": "insights", "skipped": "ENABLE_INSIGHTS is false"}
    history = load_json(HISTORY_PATH, [])
    metrics = load_json(METRICS_PATH, {"version": 2, "snapshots": {}})
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
                **values,
                "collected_at": now.isoformat(),
                "age_hours": round(age, 2),
                "source": "threads_api",
                "format": post.get("format", "legacy"),
                "pillar": post.get("pillar", "legacy"),
            }
            fetched += 1
        except RuntimeError:
            errors.append("insights_unavailable_check_threads_manage_insights")
            break
    if not dry_run:
        save_json(METRICS_PATH, metrics)
    return {
        "mode": "insights",
        "dry_run": dry_run,
        "fetched": fetched,
        "errors": errors,
        "performance": engine.performance_context(history, metrics),
    }


def run_replies(dry_run: bool, *, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    insights = collect_insights(dry_run, now=now)
    if not env_bool("ENABLE_REPLIES"):
        run = {"mode": "reply", "dry_run": dry_run, "skipped": "ENABLE_REPLIES is false", "insights": insights}
        save_json(RUN_LOG_PATH, run)
        return run

    history = load_json(HISTORY_PATH, [])
    today = now.astimezone(VIETNAM).date()
    already = {str(x.get("reply_to_id")) for x in history if x.get("reply_to_id")}
    today_sent = sum(
        bool(
            x.get("reply_to_id")
            and iso_time(x.get("at", ""))
            and iso_time(x["at"]).astimezone(VIETNAM).date() == today
        )
        for x in history
    )
    cap = max(0, bounded_int("REPLY_DAILY_CAP", 5, 0, 10) - today_sent)
    sent, inspected = [], 0
    router = ModelRouter(dry_run=dry_run, now=now)
    client = Threads()

    if cap:
        try:
            own_username = str(client.profile().get("username", "")).casefold()
        except (APIError, RuntimeError):
            own_username = ""
        own_ids = {str(x.get("id")) for x in history} | {
            str(x.get("followup_post_id")) for x in history if x.get("followup_post_id")
        }
        replied_users_per_post: Counter[tuple[str, str]] = Counter()
        for post in reversed(engine.post_history(history)[-10:]):
            if len(sent) >= cap or inspected >= 10:
                break
            pid = str(post["id"])
            try:
                comments = client.replies(pid)
            except (APIError, RuntimeError):
                # Token lacks threads_manage_replies scope or post unavailable on Meta
                break
            for comment in comments:
                rid = str(comment.get("id", ""))
                uname = str(comment.get("username", "")).casefold()
                if not rid or rid in already or rid in own_ids or uname == own_username:
                    continue
                if uname and replied_users_per_post[(pid, uname)] >= 2:
                    continue
                inspected += 1
                text = engine.reply_text(str(comment.get("text", "")), str(post.get("text", "")), router.call_json)
                if text and not engine.too_similar(text, [x for x in history if x.get("reply_to_id")]):
                    item = {
                        "mode": "reply",
                        "at": now.isoformat(),
                        "reply_to_id": rid,
                        "parent_post_id": pid,
                        "text": text,
                        "dry_run": dry_run,
                        "source": "gemini_workhorse_reply",
                        "engine_version": "3.0",
                    }
                    if not dry_run:
                        item["id"] = client.publish_text(text, reply_to_id=rid)
                        append_history(history, item)
                    sent.append(item)
                    if uname:
                        replied_users_per_post[(pid, uname)] += 1
                already.add(rid)
                if len(sent) >= cap or inspected >= 10:
                    break
    router.persist()
    run = {
        "mode": "reply",
        "dry_run": dry_run,
        "at": now.isoformat(),
        "sent": sent,
        "model_routing": router.summary(),
        "insights": insights,
    }
    save_json(RUN_LOG_PATH, run)
    return run


def run_refresh_token(dry_run: bool) -> dict[str, Any]:
    if dry_run:
        return {"mode": "refresh-token", "dry_run": True, "skipped": "pass --live to call Meta refresh endpoint"}
    res = Threads().refresh_long_lived_token()
    expires_in = int(res.get("expires_in", 0))
    return {
        "mode": "refresh-token",
        "dry_run": False,
        "refreshed": bool(res.get("access_token")),
        "expires_in_days": round(expires_in / 86400, 1) if expires_in else None,
        "note": "Token value intentionally redacted from stdout/logs. Use get_threads_token.py --refresh locally to inspect and copy.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("auto", "post", "reply", "insights", "refresh-token"), default="post")
    switch = parser.add_mutually_exclusive_group()
    switch.add_argument("--live", action="store_true")
    switch.add_argument("--dry-run", action="store_true", help="Force preview even if DRY_RUN=false")
    switch.add_argument("--offline", action="store_true", help="Preview reserves with zero network calls")
    args = parser.parse_args()
    if args.offline and (args.live or args.mode != "post"):
        parser.error("--offline is only valid for post previews")
    dry_run = True if args.dry_run or args.offline else False if args.live else env_bool("DRY_RUN", True)
    if args.mode == "auto":
        post_run = run_post(dry_run, offline=args.offline)
        reply_run = run_replies(dry_run)
        run = {"mode": "auto", "dry_run": dry_run, "post": post_run, "reply": reply_run}
        save_json(RUN_LOG_PATH, run)
    elif args.mode == "post":
        run = run_post(dry_run, offline=args.offline)
    elif args.mode == "reply":
        run = run_replies(dry_run)
    elif args.mode == "insights":
        run = collect_insights(dry_run)
        save_json(RUN_LOG_PATH, run)
    else:
        run = run_refresh_token(dry_run)
    print(json.dumps(run, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
