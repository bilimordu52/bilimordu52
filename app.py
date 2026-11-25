"""URL ile çalışan medya indirme platformu (yt-dlp tabanlı).

Kullanım: python app.py  ->  http://127.0.0.1:5000
"""

import mimetypes
import re
import shutil
import threading
import urllib.request
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import yt_dlp

try:
    from imageio_ffmpeg import get_ffmpeg_exe as _imageio_ffmpeg

    FFMPEG = shutil.which("ffmpeg") or _imageio_ffmpeg()
except ImportError:
    FFMPEG = shutil.which("ffmpeg")

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)

TASKS = {}
LOCK = threading.Lock()


class BadRequest(Exception):
    pass


def base_opts():
    opts = {
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 25,
        "retries": 3,
        "outtmpl": str(DOWNLOAD_DIR / "%(id)s.%(ext)s"),
    }
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG
    return opts


def validate_url(raw):
    url = (raw or "").strip()
    if not url.startswith(("http://", "https://")):
        raise BadRequest("Lütfen http:// veya https:// ile başlayan geçerli bir URL girin.")
    return url


def friendly_error(exc):
    text = str(exc)
    lowered = text.lower()
    if "sign in to confirm" in lowered or "cookies" in lowered:
        return "Site bot koruması uyguladı; bu içerik için tarayıcı çerezleri gerekebilir."
    if "unsupported url" in lowered:
        return "Bu adres desteklenmiyor. Bağlantıyı kontrol edin."
    if "private" in lowered or "login required" in lowered:
        return "Bu medya gizli (private) veya giriş gerektiriyor."
    if "not a valid url" in lowered:
        return "Geçersiz URL."
    if "unable to download" in lowered or "urlopen error" in lowered or "timed out" in lowered:
        return "Bağlantı açılamadı. URL'yi veya internet bağlantısını kontrol edin."
    return f"İndirme hatası: {text}"


def parse_video_options(info):
    best_by_height = {}
    for f in info.get("formats") or []:
        if f.get("vcodec") == "none" or not f.get("height"):
            continue
        height = f["height"]
        current = best_by_height.get(height)
        if current is None or (f.get("tbr") or 0) > (current["_tbr"] or 0):
            best_by_height[height] = {
                "format_id": f["format_id"],
                "label": f"{height}p · {(f.get('ext') or 'mp4').upper()}",
                "height": height,
                "filesize": f.get("filesize") or f.get("filesize_approx"),
                "has_audio": f.get("acodec") != "none",
                "_tbr": f.get("tbr"),
            }

    options = [
        {k: v for k, v in entry.items() if not k.startswith("_")}
        for _, entry in sorted(best_by_height.items(), reverse=True)
    ]
    best_filesize = options[0]["filesize"] if options else None
    options.insert(
        0,
        {
            "format_id": "best",
            "label": "En iyi kalite (otomatik)",
            "height": None,
            "filesize": best_filesize,
            "has_audio": False,
        },
    )
    return options


def download_name(title, suffix):
    safe = re.sub(r'[\\/:*?"<>|]+', " ", title).strip() or "indirilen"
    return f"{safe[:80]}{suffix}"


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def api_info():
    try:
        url = validate_url(request.json.get("url"))
    except BadRequest as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        with yt_dlp.YoutubeDL(base_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        return jsonify({"error": friendly_error(exc)}), 400

    if info.get("_type") == "playlist":
        if not info.get("entries"):
            return jsonify({"error": "Bu oynatma listesinde içerik bulunamadı."}), 400
        info = info["entries"][0]

    return jsonify(
        {
            "title": info.get("title") or "İsimsiz medya",
            "uploader": info.get("uploader") or info.get("channel"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "webpage_url": info.get("webpage_url") or url,
            "extractor": info.get("extractor_key"),
            "video_options": parse_video_options(info),
        }
    )


@app.post("/api/download")
def api_download():
    try:
        url = validate_url(request.json.get("url"))
    except BadRequest as exc:
        return jsonify({"error": str(exc)}), 400
    fmt = request.json.get("format") or "best"
    if fmt not in ("best", "audio") and not re.fullmatch(r"[\w.\-+]+", fmt):
        return jsonify({"error": "Geçersiz format."}), 400

    task_id = uuid.uuid4().hex[:12]
    task = {
        "url": url,
        "fmt": fmt,
        "status": "starting",
        "progress": 0,
        "speed": None,
        "eta": None,
        "title": None,
        "filepath": None,
        "error": None,
    }
    with LOCK:
        TASKS[task_id] = task

    threading.Thread(target=run_download, args=(task_id, task), daemon=True).start()
    return jsonify({"task_id": task_id})


def run_download(task_id, task):
    opts = base_opts()

    def hook(data):
        if data["status"] == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            done = data.get("downloaded_bytes") or 0
            with LOCK:
                task.update(
                    status="downloading",
                    progress=round(done / total * 100) if total else 0,
                    speed=data.get("_speed_str", "").strip(),
                    eta=data.get("_eta_str", "").strip(),
                )
        elif data["status"] == "finished":
            with LOCK:
                task.update(status="processing", progress=100)

    opts["progress_hooks"] = [hook]

    if task["fmt"] == "audio":
        if not FFMPEG:
            with LOCK:
                task.update(status="error", error="MP3 dönüştürme için ffmpeg gerekli.")
            return
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    else:
        chosen = task["fmt"]
        if chosen != "best":
            opts["format"] = f"{chosen}+bestaudio/{chosen}/best/bestaudio"
        else:
            opts["format"] = "bestvideo*+bestaudio/best"
        opts["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(task["url"], download=True)
            if info.get("_type") == "playlist":
                info = info["entries"][0]
            filepath = None
            for entry in info.get("requested_downloads") or []:
                filepath = entry.get("filepath")
            if not filepath or not Path(filepath).is_file():
                filepath = ydl.prepare_filename(info)
                if task["fmt"] == "audio":
                    filepath = str(Path(filepath).with_suffix(".mp3"))
        with LOCK:
            task.update(
                status="done",
                progress=100,
                title=info.get("title"),
                filepath=filepath,
            )
    except yt_dlp.utils.DownloadError as exc:
        task.update(status="error", error=friendly_error(exc))
    except Exception as exc:
        task.update(status="error", error=f"Beklenmeyen hata: {exc}")


@app.get("/api/progress/<task_id>")
def api_progress(task_id):
    with LOCK:
        task = TASKS.get(task_id)
        if not task:
            return jsonify({"error": "İş bulunamadı."}), 404
        return jsonify({k: task[k] for k in (
            "status", "progress", "speed", "eta", "title", "error")})


@app.get("/api/file/<task_id>")
def api_file(task_id):
    with LOCK:
        task = TASKS.get(task_id)
    if not task or task["status"] != "done" or not task.get("filepath"):
        return jsonify({"error": "Dosya hazır değil."}), 404
    path = Path(task["filepath"])
    if not path.is_file():
        return jsonify({"error": "Dosya bulunamadı."}), 404

    from flask import after_this_request

    @after_this_request
    def cleanup(_response):
        try:
            path.unlink()
        except OSError:
            pass
        with LOCK:
            TASKS.pop(task_id, None)
        return _response

    return send_file(
        path,
        as_attachment=True,
        download_name=download_name(task.get("title") or path.stem, path.suffix),
        mimetype=mimetypes.guess_type(str(path))[0],
    )


@app.get("/api/thumbnail")
def api_thumbnail():
    url = request.args.get("url", "")
    title = request.args.get("title", "thumbnail")
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Geçersiz URL."}), 400
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
            ctype = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
    except Exception:
        return jsonify({"error": "Görsel indirilemedi."}), 400
    ext = mimetypes.guess_extension(ctype) or ".jpg"
    response = app.response_class(data, mimetype=ctype)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="{download_name(title, ext)}"'
    )
    return response


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
