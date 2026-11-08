#!/usr/bin/env python3
"""Utility script to exchange a Threads authorization code for a 60-day Long-Lived Token."""

import json
import os
import re
import sys
import urllib.parse
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")

REDIRECT_URI = "https://localhost/"


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


def main():
    print("=" * 60)
    print(" CÔNG CỤ TẠO THREADS LONG-LIVED ACCESS TOKEN (60 NGÀY)")
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
        f"&scope=threads_basic,threads_content_publish"
        f"&response_type=code"
    )

    print("\n" + "-" * 60)
    print("BƯỚC 1: Mở đường link sau trên trình duyệt (đã đăng nhập Threads):")
    print("-" * 60)
    print(auth_url)
    print("-" * 60)
    print("Bấm 'Tiếp tục' / 'Cho phép' trên Threads.")
    print("Trình duyệt sẽ chuyển hướng về https://localhost/?code=... (có thể báo lỗi trang không truy cập được - điều này bình thường).")
    print("-" * 60)

    raw_input = input("\nBƯỚC 2: Copy toàn bộ URL trên thanh địa chỉ hoặc mã 'code' rồi dán vào đây:\n> ").strip()
    if not raw_input:
        print("Lỗi: Bạn chưa nhập URL hoặc mã code.")
        return 1

    # Extract code from URL if full URL is pasted
    if "code=" in raw_input:
        parsed = urllib.parse.urlparse(raw_input)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [""])[0]
    else:
        code = raw_input

    # Meta appends #_ to the code sometimes
    code = re.sub(r"#_.*$", "", code).strip()
    if not code:
        print("Lỗi: Không tìm thấy mã code hợp lệ.")
        return 1

    print("\n-> Đang đổi mã code lấy Short-lived Token (1 giờ)...")
    try:
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
    except Exception as exc:
        print(f"\n[!] Thất bại khi lấy Short-lived Token: {exc}")
        return 1

    short_token = short_res.get("access_token")
    user_id = short_res.get("user_id")
    if not short_token:
        print(f"\n[!] Không nhận được access_token: {short_res}")
        return 1

    print(f"-> Đã lấy thành công Token ngắn hạn cho User ID: {user_id}")
    print("-> Đang nâng cấp lên Long-lived Token (60 ngày)...")

    try:
        long_res = get_json(
            "https://graph.threads.net/access_token",
            {
                "grant_type": "th_exchange_token",
                "client_secret": app_secret,
                "access_token": short_token,
            },
        )
    except Exception as exc:
        print(f"\n[!] Thất bại khi nâng cấp Long-lived Token: {exc}")
        print(f"Bạn có thể dùng tạm Short-lived Token này (hạn 1 giờ): {short_token}")
        return 1

    long_token = long_res.get("access_token")
    expires_in = long_res.get("expires_in", 5184000)
    days = expires_in // 86400

    print("\n" + "=" * 60)
    print(" [THÀNH CÔNG] ĐÂY LÀ TOKEN DÀI HẠN CỦA BẠN:")
    print("=" * 60)
    print(long_token)
    print("=" * 60)
    print(f"Hạn sử dụng: khoảng {days} ngày.")
    print("HÃY LƯU TOKEN NÀY VÀO:")
    print("GitHub Repo -> Settings -> Secrets and variables -> Actions -> THREADS_ACCESS_TOKEN")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
