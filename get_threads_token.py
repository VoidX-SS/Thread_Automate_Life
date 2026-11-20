#!/usr/bin/env python3
"""Utility script to obtain or refresh a 60-day Threads Long-Lived Access Token (v3.0)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

REDIRECT_URI = "https://localhost/"
SCOPES = ",".join([
    "threads_basic",
    "threads_content_publish",
    "threads_read_replies",
    "threads_manage_replies",
    "threads_manage_insights",
])


def post_form(url: str, form_data: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(form_data).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {err}") from exc


def get_json(url: str, params: dict[str, str]) -> dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {err}") from exc


def refresh_existing() -> int:
    print("=" * 60)
    print(" LÀM MỚI THREADS LONG-LIVED TOKEN (GIA HẠN THÊM 60 NGÀY)")
    print("=" * 60)
    current = os.getenv("THREADS_ACCESS_TOKEN") or input("Nhập Long-Lived Token hiện tại: ").strip()
    if not current:
        print("Lỗi: Token không được để trống.")
        return 1
    try:
        res = get_json(
            "https://graph.threads.net/refresh_access_token",
            {"grant_type": "th_refresh_token", "access_token": current},
        )
    except Exception as exc:
        print(f"\n[!] Gia hạn thất bại: {exc}")
        return 1
    new_token = res.get("access_token")
    days = int(res.get("expires_in", 5184000)) // 86400
    print("\n" + "=" * 60)
    print(f" [THÀNH CÔNG] TOKEN MỚI (hạn ~{days} ngày):")
    print("=" * 60)
    print(new_token)
    print("=" * 60)
    print("Cập nhật lại vào GitHub Secret: THREADS_ACCESS_TOKEN")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Gia hạn token dài hạn hiện có trước khi hết 60 ngày")
    args = parser.parse_args()
    if args.refresh:
        return refresh_existing()

    print("=" * 60)
    print(" CÔNG CỤ TẠO THREADS LONG-LIVED ACCESS TOKEN v3 (5 QUYỀN)")
    print("=" * 60)

    app_id = os.getenv("THREADS_APP_ID") or input("\n1. Nhập App ID: ").strip()
    if not app_id:
        print("Lỗi: App ID không được để trống.")
        return 1

    app_secret = os.getenv("THREADS_APP_SECRET") or input("2. Nhập App Secret: ").strip()
    if not app_secret:
        print("Lỗi: App Secret không được để trống.")
        return 1

    auth_url = (
        f"https://threads.net/oauth/authorize"
        f"?client_id={urllib.parse.quote(app_id)}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&response_type=code"
    )

    print("\n" + "-" * 60)
    print("BƯỚC 1: Mở đường link sau trên trình duyệt (đã đăng nhập Threads):")
    print("-" * 60)
    print(auth_url)
    print("-" * 60)
    print("Scopes yêu cầu:", SCOPES)
    print("Bấm 'Tiếp tục' / 'Cho phép'. Trình duyệt chuyển về https://localhost/?code=...")
    print("-" * 60)

    raw_input = input("\nBƯỚC 2: Dán toàn bộ URL hoặc mã 'code':\n> ").strip()
    if not raw_input:
        print("Lỗi: Chưa nhập mã code.")
        return 1

    if "code=" in raw_input:
        parsed = urllib.parse.urlparse(raw_input)
        code = urllib.parse.parse_qs(parsed.query).get("code", [""])[0]
    else:
        code = raw_input
    code = re.sub(r"#_.*$", "", code).strip()
    if not code:
        print("Lỗi: Không tìm thấy mã code hợp lệ.")
        return 1

    print("\n-> Đổi code lấy Short-lived Token (1 giờ)...")
    short_res = post_form(
        "https://graph.threads.net/oauth/access_token",
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
    )
    short_token = short_res.get("access_token")
    if not short_token:
        print(f"[!] Không nhận được access_token: {short_res}")
        return 1

    print(f"-> Thành công cho User ID: {short_res.get('user_id')}. Đang nâng lên Long-lived Token (60 ngày)...")
    long_res = get_json(
        "https://graph.threads.net/access_token",
        {
            "grant_type": "th_exchange_token",
            "client_secret": app_secret,
            "access_token": short_token,
        },
    )
    long_token = long_res.get("access_token")
    days = int(long_res.get("expires_in", 5184000)) // 86400
    print("\n" + "=" * 60)
    print(f" [THÀNH CÔNG] TOKEN DÀI HẠN (~{days} ngày):")
    print("=" * 60)
    print(long_token)
    print("=" * 60)
    print("Lưu vào GitHub Repo -> Settings -> Secrets and variables -> Actions -> THREADS_ACCESS_TOKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
