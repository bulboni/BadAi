#!/bin/bash
set -euo pipefail

# --- Pastikan dijalankan sebagai root ---
if [ "$(id -u)" -ne 0 ]; then
    echo "Jalankan skrip ini sebagai root (sudo ./vns.sh)" >&2
    exit 1
fi

export DEBIAN_FRONTEND=noninteractive

# --- Deteksi arsitektur ---
ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
    arm64|aarch64) echo "[*] Arsitektur ARM64 terdeteksi" ;;
    amd64|x86_64)  echo "[*] Arsitektur AMD64 terdeteksi" ;;
    *)             echo "[*] Arsitektur: $ARCH" ;;
esac

# --- 1. Update & install paket dasar ---
echo "[*] Update & install paket..."
apt update -y
apt install -y xfce4 xfce4-goodies dbus-x11 novnc python3-websockify

# --- Pilih VNC server yang tersedia di repo arm64 ---
echo "[*] Memilih VNC server yang kompatibel dengan $ARCH..."
if apt-cache show tigervnc-standalone-server >/dev/null 2>&1; then
    apt install -y tigervnc-standalone-server tigervnc-common
    VNC_FLAVOR="tigervnc"
elif apt-cache show tightvncserver >/dev/null 2>&1; then
    apt install -y tightvncserver
    VNC_FLAVOR="tightvnc"
else
    echo "[-] Tidak ada VNC server (tigervnc/tightvnc) di repo untuk $ARCH" >&2
    exit 1
fi
echo "[*] VNC server terpasang: $VNC_FLAVOR"

# --- 2. Siapkan direktori & password VNC ---
echo "[*] Menyiapkan password VNC..."
mkdir -p ~/.vnc
printf 'cloudshell123' | vncpasswd -f > ~/.vnc/passwd
chmod 600 ~/.vnc/passwd

# --- xstartup eksplisit ke XFCE (penting di arm64) ---
cat > ~/.vnc/xstartup <<'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
exec startxfce4
EOF
chmod +x ~/.vnc/xstartup

# --- 3. Matikan sesi :1 & bersihkan lock (abaikan error) ---
vncserver -kill :1 2>/dev/null || true
pkill -f "Xvnc :1"       2>/dev/null || true
pkill -f "Xtigervnc :1"  2>/dev/null || true
rm -f /tmp/.X1-lock /tmp/.X11-unix/X1 2>/dev/null || true

# --- 4. Jalankan VNC server di display :1 ---
echo "[*] Menjalankan VNC server di :1..."
if [ "$VNC_FLAVOR" = "tigervnc" ]; then
    vncserver :1 -geometry 1280x720 -depth 24 -localhost yes
else
    # tightvnc tidak menerima argumen "yes"
    vncserver :1 -geometry 1280x720 -depth 24 -localhost
fi

# --- 5. Siapkan noVNC (handle vnc.html / vnc_lite.html) ---
if [ -f /usr/share/novnc/vnc.html ]; then
    ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html
elif [ -f /usr/share/novnc/vnc_lite.html ]; then
    ln -sf /usr/share/novnc/vnc_lite.html /usr/share/novnc/index.html
fi

# --- 6. Jalankan websockify (background) ---
echo "[*] Menjalankan websockify di port 8080..."
pkill -f "websockify.*8080" 2>/dev/null || true
nohup websockify --web=/usr/share/novnc/ 8080 localhost:5901 \
    > /var/log/websockify.log 2>&1 &
sleep 1

echo "[✓] Selesai. Buka http://<IP-server>:8080/vnc.html"
echo "    Password VNC: cloudshell123"
