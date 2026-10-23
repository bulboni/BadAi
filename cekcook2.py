#!/usr/bin/env python3
"""
cekcook.py — Cek cookie e-powerpay via AdsPower + Playwright.

Alur:
  1. Baca cookie dari /tmp/ck.txt
  2. Cek cepat pakai requests (informatif saja)
  3. Start profil AdsPower → inject cookie → buka /verify-login → reload
  4. Deteksi apakah cookie valid dari **konten DOM** + screenshot

Env yang dibutuhkan:
  ADSPOWER_KEY  = api key dari AdsPower → Settings → API
  ADSPOWER_ID   = user_id profil browser (BUKAN user_id akun)

Pemakaian:
  export ADSPOWER_KEY="xxxxx"
  python3 cekcook.py                # hanya list profil
  export ADSPOWER_ID="k1xxxxx"
  python3 cekcook.py                # cek cookie
"""

import os
import sys
import time
import json
import requests
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

# ---------------- KONFIG ----------------
COOKIE_FILE   = "/tmp/ck.txt"
TARGET_URL    = "https://partner.e-powerpay.id/verify-login"
ADSPOWER_HOST = "http://local.adspower.net:50325"
ADSPOWER_KEY  = os.getenv("ADSPOWER_KEY", "").strip()
ADSPOWER_ID   = os.getenv("ADSPOWER_ID", "").strip()
USER_AGENT    = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

DOMAIN = "." + urlparse(TARGET_URL).netloc.replace("partner.", "")


# ---------------- COOKIE ----------------
def load_cookie(path: str):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip().replace("\r", "").replace("\n", "")
    cookies = {}
    for item in raw.split(";"):
        item = item.strip()
        if "=" in item:
            k, v = item.split("=", 1)
            cookies[k] = v
    return raw, cookies


def to_playwright_cookies(cookies: dict) -> list:
    return [{
        "name": k, "value": v,
        "domain": DOMAIN, "path": "/",
        "secure": True, "httpOnly": False, "sameSite": "None",
    } for k, v in cookies.items()]


# ---------------- ADSPOWER API ----------------
def adspower_get(path: str, **params) -> dict:
    if not ADSPOWER_KEY:
        raise RuntimeError("ADSPOWER_KEY kosong. export ADSPOWER_KEY=xxxxx")

    headers = {
        "api-key":       ADSPOWER_KEY,
        "Authorization": f"Bearer {ADSPOWER_KEY}",
    }
    if ADSPOWER_ID:
        params.setdefault("user_id", ADSPOWER_ID)

    url = f"{ADSPOWER_HOST}{path}"
    try:
        r = requests.get(url, params=params, headers=headers, timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f"Tidak bisa hubungi AdsPower di {ADSPOWER_HOST}: {e}")

    print(f"[adspower] GET {path} → HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"[adspower]  body: {r.text[:300]}")
        return {"code": -999, "msg": r.text[:200]}

    try:
        data = r.json()
    except Exception:
        print(f"[adspower]  non-json: {r.text[:300]}")
        return {"code": -998, "msg": r.text[:200]}

    if data.get("code") != 0:
        print(f"[adspower]  response: {data}")
    return data


def list_profiles() -> list:
    out, page = [], 1
    while True:
        data = adspower_get("/api/v1/user/list", page=page, page_size=100)
        if data.get("code") != 0:
            return []
        d = data.get("data") or {}
        lst = d.get("list") or []
        out.extend(lst)
        total = d.get("total") or 0
        if not lst or len(out) >= total:
            break
        page += 1
    return out


def print_profiles(profiles: list):
    if not profiles:
        print("[adspower] ⚠️  Tidak ada profil yang bisa diakses api-key ini.")
        print("            Cek: api-key aktif? workspace sama? profil tidak di-trash?")
        return

    print(f"\n=== {len(profiles)} PROFIL DITEMUKAN ===")
    print(f"{'#':<3} {'user_id':<24} {'serial':<10} {'nama'}")
    print("-" * 70)
    for i, p in enumerate(profiles, 1):
        uid    = p.get("user_id") or p.get("id") or "?"
        serial = str(p.get("serial_number") or "-")
        name   = (p.get("name") or "-")[:40]
        print(f"{i:<3} {uid:<24} {serial:<10} {name}")
    print()
    print('Pakai salah satu user_id:')
    print('  export ADSPOWER_ID="<user_id dari tabel>"')
    print()


def start_adspower() -> dict:
    print(f"[adspower] start profile {ADSPOWER_ID}…")
    data = adspower_get("/api/v1/browser/start", open_tabs=1)
    code = data.get("code")
    msg  = str(data.get("msg", "")).lower()

    if code == -1 and "api-key" in msg:
        raise RuntimeError(
            "Api-key ditolak. Buka AdsPower → Settings → API, copy ulang."
        )

    if "profile does not exist" in msg or "user does not exist" in msg:
        print("\n[adspower] ❌ Profile ID salah. Daftar profil yang tersedia:\n")
        print_profiles(list_profiles())
        raise RuntimeError(
            f"Profile '{ADSPOWER_ID}' tidak ada / tidak bisa diakses api-key."
        )

    if code == -2 or "already" in msg:
        print("[adspower] profil sudah jalan, ambil status…")
        data = adspower_get("/api/v1/browser/status")

    if data.get("code") != 0:
        raise RuntimeError(f"AdsPower error: {data}")

    return data["data"]


def stop_adspower():
    try:
        adspower_get("/api/v1/browser/stop")
    except Exception as e:
        print(f"[adspower] stop warning: {e}")


# ---------------- CEK #1: requests (informatif) ----------------
def check_requests(cookie_str: str, cookies: dict) -> dict:
    """Cek cepat via HTTP — hanya INFORMATIF, bukan penentu valid/tidak."""
    headers = {
        "Cookie": cookie_str,
        "User-Agent": USER_AGENT,
        "X-CSRF-Token": cookies.get("CSRF", ""),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    }
    try:
        # PENTING: allow_redirects=True supaya tahu final URL
        r = requests.get(TARGET_URL, headers=headers,
                         allow_redirects=True, timeout=30)
    except Exception as e:
        print(f"[requests] error: {e}")
        return {"status": None, "final_url": None, "has_password": None}

    final_url = r.url
    body = (r.text or "").lower()
    has_password = ('type="password"' in body) or ('name="password"' in body)

    print(f"[requests] HTTP {r.status_code}  final_url={final_url}")
    print(f"[requests] has_password_form={has_password}")
    print("[requests] (hanya info HTTP — keputusan final dari AdsPower/DOM)")
    return {"status": r.status_code, "final_url": final_url,
            "has_password": has_password}


# ---------------- CEK #2: AdsPower + Playwright ----------------
def _wait_render(page, timeout_ms: int = 12000):
    """Tunggu sampai halaman settle (network idle + salah satu indikator)."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass

    # tunggu sampai minimal ada indikator login ATAU input password
    try:
        page.wait_for_function(
            """() => {
                const pwd       = !!document.querySelector('input[type="password"]');
                const logout    = !!document.querySelector('a[href*="logout" i]');
                const sideb     = !!document.querySelector('[class*="sidebar" i]');
                const dash      = !!document.querySelector('[class*="dashboard" i]');
                const avatar    = !!document.querySelector('[class*="avatar" i]');
                return pwd || logout || sideb || dash || avatar;
            }""",
            timeout=timeout_ms,
        )
    except Exception:
        pass


def _detect_state(page) -> tuple:
    """
    Deteksi apakah sedang di form login atau sudah masuk.
    Return: (success: bool|None, reason: str, info: dict)
    """
    info = {"has_password": False, "logged_in_selectors": [], "body_len": 0}

    # 1) Ada input password yang visible → BELUM login
    try:
        pwd = page.query_selector('input[type="password"]')
        info["has_password"] = bool(pwd and pwd.is_visible())
    except Exception:
        pass

    # 2) Cari indikator logged-in
    indicators = (
        'a[href*="logout" i]',
        'a:has-text("Logout")',
        'button:has-text("Logout")',
        'a:has-text("Keluar")',
        'button:has-text("Keluar")',
        '[class*="sidebar" i]',
        '[class*="avatar" i]',
        '[class*="dashboard" i]',
        '[class*="user-info" i]',
        '[class*="user-profile" i]',
        '[class*="navbar" i]',
    )
    for sel in indicators:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                info["logged_in_selectors"].append(sel)
        except Exception:
            continue

    # 3) Ambil teks body untuk fallback
    body_text = ""
    try:
        body_text = (page.inner_text("body") or "")
    except Exception:
        pass
    info["body_len"] = len(body_text)
    lower = body_text.lower()

    # ---- Keputusan ----
    if info["has_password"]:
        return False, "Input password terlihat (form login)", info

    if info["logged_in_selectors"]:
        return True, f"Ditemukan {len(info['logged_in_selectors'])} indikator logged-in", info

    # Fallback berbasis teks — tapi longgar (jangan panik hanya krn ada 'csrf')
    login_keywords = ("masukkan password", "sign in to", "silakan login",
                      "halaman login", "please log in", "please sign in")
    if any(k in lower for k in login_keywords):
        return False, "Body mengandung frasa form login", info

    # Konten dashboard biasanya cukup banyak dan TIDAK berisi form password
    if info["body_len"] > 200:
        return True, f"Body berisi konten ({info['body_len']} char) tanpa form password", info

    return None, "Tidak jelas — cek screenshot", info


def check_adspower(cookies: dict) -> dict:
    info = start_adspower()

    debug_port = info.get("debug_port")
    if not debug_port:
        raise RuntimeError(f"debug_port tidak ada di response: {info}")

    cdp_http = f"http://127.0.0.1:{debug_port}"
    print(f"[adspower] CDP endpoint: {cdp_http}")

    result = {"success": False, "final_url": None, "screenshot": None,
              "reason": None}

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(cdp_http)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()

            ctx.add_cookies(to_playwright_cookies(cookies))
            print(f"[adspower] inject {len(cookies)} cookie ke {DOMAIN}")

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_extra_http_headers({"X-CSRF-Token": cookies.get("CSRF", "")})

            # --- goto awal ---
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"[adspower] goto warning: {e}")

            _wait_render(page)

            # --- reload (sesuai permintaan) ---
            try:
                page.reload(wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                print(f"[adspower] reload warning: {e}")

            _wait_render(page)
            time.sleep(1)  # grace kecil untuk JS yang telat render

            final_url = page.url
            print(f"[adspower] final_url={final_url}")

            success, reason, di = _detect_state(page)
            print(f"[adspower] has_password_form={di['has_password']}")
            print(f"[adspower] logged_in_selectors={di['logged_in_selectors']}")
            print(f"[adspower] body_len={di['body_len']}")
            print(f"[adspower] verdict={success}  reason={reason}")

            shot = "/tmp/adspower_check.png"
            try:
                page.screenshot(path=shot, full_page=True)
                print(f"[adspower] screenshot → {shot}")
            except Exception as e:
                print(f"[adspower] screenshot warning: {e}")
                shot = None

            result.update(
                success=bool(success),
                final_url=final_url,
                screenshot=shot,
                reason=reason,
                has_password_form=di["has_password"],
                logged_in_selectors=di["logged_in_selectors"],
                body_len=di["body_len"],
            )
    finally:
        print("[adspower] stop profile…")
        stop_adspower()

    return result


# ---------------- MAIN ----------------
def main():
    if not ADSPOWER_KEY:
        print("⚠️  ADSPOWER_KEY kosong. Jalankan: export ADSPOWER_KEY=xxxxx")
        sys.exit(1)

    print(f"Adspower Key  : {ADSPOWER_KEY[:8]}…{ADSPOWER_KEY[-4:]}")
    print(f"Adspower ID   : {ADSPOWER_ID or '(belum di-set)'}")
    print(f"Cookie file   : {COOKIE_FILE}")
    print(f"Target URL    : {TARGET_URL}")
    print()

    # 1) Diagnostik daftar profil
    profiles = list_profiles()
    print_profiles(profiles)

    if not ADSPOWER_ID:
        print("ℹ️  Set ADSPOWER_ID dari salah satu user_id di atas, lalu jalankan ulang.")
        sys.exit(0)

    if profiles:
        ids = {p.get("user_id") or p.get("id") for p in profiles}
        if ADSPOWER_ID not in ids:
            print(f"⚠️  ADSPOWER_ID '{ADSPOWER_ID}' tidak ada dalam daftar profil.")
            print( "   Copy salah satu user_id dari tabel di atas dan jalankan ulang.")
            sys.exit(1)
        print(f"✅ ADSPOWER_ID '{ADSPOWER_ID}' ditemukan. Lanjut…\n")

    # 2) Baca cookie
    if not os.path.exists(COOKIE_FILE):
        print(f"⚠️  File cookie tidak ada: {COOKIE_FILE}")
        sys.exit(1)

    raw, cookies = load_cookie(COOKIE_FILE)
    print(f"Cookies terbaca: {list(cookies.keys())}\n")

    # 3) Cek cepat (info saja)
    check_requests(raw, cookies)
    print()

    # 4) Cek via AdsPower (utama)
    res = check_adspower(cookies)

    print("\n=== HASIL AKHIR ===")
    print(json.dumps(res, indent=2, ensure_ascii=False))

    if res["success"]:
        print("✅ Cookie VALID — halaman menampilkan konten dashboard (bukan form login)")
    else:
        print(f"❌ Cookie TIDAK valid — {res.get('reason')}")


if __name__ == "__main__":
    main()
