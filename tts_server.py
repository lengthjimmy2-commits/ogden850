#!/usr/bin/env python3
"""Ogden 850 TTS Server — serves static files + generates TTS audio via edge-tts"""
import asyncio, hashlib, json, os, sys, time, mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PORT = 8887
BASE = Path(__file__).parent
CACHE = BASE / "tts-cache"
CACHE.mkdir(exist_ok=True)

# ── Voice mapping ──
EN_VOICES = {
    "en-US-SteffanNeural": "Steffan (US男)",
    "en-US-JennyNeural":   "Jenny (US女)",
    "en-GB-RyanNeural":    "Ryan (英男)",
    "en-GB-LibbyNeural":   "Libby (英女)",
}
ZH_VOICES = {
    "zh-CN-XiaoxiaoNeural": "晓晓 (CN女)",
    "zh-CN-YunxiNeural":    "云希 (CN男)",
    "zh-HK-HiuMaanNeural":  "晓曼 (HK女)",
    "zh-HK-WanLungNeural":  "云龙 (HK男)",
}

# ⚡ Async TTS engine
_loop = asyncio.new_event_loop()

def generate_tts(text: str, voice: str) -> bytes:
    """Generate TTS audio bytes (synchronous wrapper around edge-tts)"""
    cache_key = hashlib.md5(f"{text}:{voice}".encode()).hexdigest()
    cache_path = CACHE / f"{cache_key}.mp3"
    if cache_path.exists():
        return cache_path.read_bytes()
    import edge_tts
    async def _gen():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(cache_path))
        return cache_path.read_bytes()
    return _loop.run_until_complete(_gen())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        # ── TTS endpoint ──
        if path == "/tts":
            text = (params.get("text") or [""])[0]
            voice = (params.get("voice") or ["en-US-SteffanNeural"])[0]
            if not text:
                self._json(400, {"error": "missing text"})
                return
            try:
                data = generate_tts(text, voice)
                self._audio(data)
            except Exception as e:
                self._json(500, {"error": str(e)})
            return

        # ── Voices endpoint ──
        if path == "/voices":
            self._json(200, {"en": EN_VOICES, "zh": ZH_VOICES})
            return

        # ── Static files ──
        filepath = BASE / (path.lstrip("/") or "index.html")
        if not filepath.exists() or not filepath.is_file():
            filepath = BASE / "index.html"
        if not filepath.exists():
            self._json(404, {"error": "not found"})
            return
        content = filepath.read_bytes()
        mime = mimetypes.guess_type(str(filepath))[0] or "application/octet-stream"
        self._serve(content, mime)

    def _serve(self, data: bytes, mime: str):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _audio(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[TTS] {self.address_string()} - {fmt % args}")


if __name__ == "__main__":
    print(f"Ogden 850 TTS Server running on http://0.0.0.0:{PORT}")
    print(f"Voices: EN={len(EN_VOICES)}, ZH={len(ZH_VOICES)}")
    print(f"TTS cache: {CACHE}")
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
