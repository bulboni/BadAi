#!/bin/bash
set -euo pipefail

# --- Pastikan dijalankan sebagai root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "Jalankan skrip ini sebagai root (sudo ./vns.sh)" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# --- 1. Update & install paket ---
echo "[*] Update & install paket..."
apt update -y
apt install -y xfce4 xfce4-goodies tigervnc-standalone-server novnc python3-websockify

# --- 2. Siapkan direktori & password VNC ---
echo "[*] Menyiapkan password VNC..."
mkdir -p ~/.vnc
printf 'cloudshell123' | vncpasswd -f > ~/.vnc/passwd
chmod 600 ~/.vnc/passwd

# --- 3. Matikan sesi :1 jika ada (abaikan error) ---
vncserver -kill :1 2>/dev/null || true

# --- 4. Jalankan VNC server di display :1 ---
echo "[*] Menjalankan VNC server di :1..."
vncserver :1 -geometry 1280x720 -depth 24 -localhost yes

# --- 5. Siapkan noVNC ---
ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# --- 6. Jalankan websockify (background) ---
echo "[*] Menjalankan websockify di port 8080..."
nohup websockify --web=/usr/share/novnc/ 8080 localhost:5901 \
    > /var/log/websockify.log 2>&1 &

echo "[✓] Selesai. Buka http://<IP-server>:8080/vnc.html"
echo "    Password VNC: cloudshell123"
