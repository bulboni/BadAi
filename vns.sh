#!/bin/bash
apt update -y
apt install -y xfce4 xfce4-goodies tigervnc-standalone-server novnc python3-websockify && mkdir -p ~/.vnc && echo "cloudshell123" | vncpasswd -f > ~/.vnc/passwd 
chmod 600 ~/.vnc/passwd && vncserver -kill :1 2>/dev/null; vncserver :1 -geometry 1280x720 -depth 24 
ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html && websockify --web=/usr/share/novnc/ 8080 localhost:5901