#!/usr/bin/env bash
# Medya İndirme Platformu - başlatma betiği
set -e
cd "$(dirname "$0")"
if ! python3 -c "import flask, yt_dlp" 2>/dev/null; then
  echo "Bağımlılıklar kuruluyor..."
  pip3 install -r requirements.txt
fi
echo "Başlatılıyor: http://127.0.0.1:5000"
python3 app.py
