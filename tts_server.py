#!/usr/bin/env python3
"""Ogden 850 TTS Server — serves static files + TTS + auth (register/login/logout)"""
import asyncio, hashlib, json, os, sys, time, mimetypes, hmac, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

PORT = 8887
BASE = Path(__file__).parent
CACHE = BASE / "tts-cache"
CACHE.mkdir(exist_ok=True)
USERS_FILE = BASE / "users.json"

# ── Auth config ──
SECRET_KEY = "ogden850-secret-2026"
TOKEN_TTL = 86400 * 7  # 7 days

def load_users():
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text())
    return {}

def save_users(users):
    USERS_FILE.write_text(json.dumps(users, indent=2))

def make_token(username: str) -> str:
    exp = int(time.time()) + TOKEN_TTL
    payload = f"{username}:{exp}"
    sig = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
    token = base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode()
    return token

def verify_token(token: str):
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        payload, sig = raw.rsplit(".", 1)
        username, exp = payload.split(":")
        expected = hmac.new(SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        if sig != expected:
            return None
        if int(time.time()) > int(exp):
            return None
        return username
    except Exception:
        return None

# Ensure default user exists
users_db = load_users()
if "ozy" not in users_db:
    users_db["ozy"] = "19990901"
    save_users(users_db)

# ── HTML templates ──
LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Ogden 850 — 登录</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.31.0/dist/tabler-icons.min.css">
<style>
:root {
  --font-sans: 'Rounded Mplus 1c','M PLUS Rounded 1c',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  --bg: #FEF7F0; --text: #3D2C25; --text2: #7A6B5E;
  --border: #E8DCC8; --card: #FFFFFF; --accent: #D4815A; --teal: #5C8A7A;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-sans); padding: 20px;
}
.box {
  background: var(--card); border-radius: 14px; padding: 32px;
  box-shadow: 0 3px 12px rgba(212,129,90,0.10); width: 100%; max-width: 360px;
  border: 1px solid var(--border);
}
h1 { font-size: 20px; color: var(--text); margin-bottom: 4px; text-align: center; }
.sub { font-size: 13px; color: var(--text2); margin-bottom: 24px; text-align: center; }
.field { margin-bottom: 16px; position: relative; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 4px; }
.field input {
  width: 100%; padding: 10px 14px; border: 1px solid var(--border);
  border-radius: 10px; font-size: 14px; font-family: var(--font-sans);
  background: rgba(255,255,255,0.7); color: var(--text);
  outline: none; transition: border 0.2s; padding-right: 40px;
}
.field input:focus { border-color: var(--accent); }
.eye-btn {
  position: absolute; right: 10px; bottom: 6px;
  background: none; border: none; cursor: pointer;
  color: var(--text2); font-size: 18px; padding: 4px;
  display: flex; align-items: center;
}
.eye-btn:hover { color: var(--accent); }
.btn {
  width: 100%; padding: 10px; background: var(--accent); color: #fff;
  border: none; border-radius: 10px; font-size: 15px; font-family: var(--font-sans);
  cursor: pointer; transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.btn-teal { background: var(--teal); margin-top: 8px; }
.error { color: #C4696A; font-size: 13px; margin-top: 10px; text-align: center; }
.links { text-align: center; margin-top: 16px; font-size: 13px; }
.links a { color: var(--accent); text-decoration: none; }
.links a:hover { text-decoration: underline; }
.icon-head { color: var(--accent); font-size: 40px; display: block; text-align: center; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="box">
  <i class="ti ti-books icon-head"></i>
  <h1>Ogden 850</h1>
  <p class="sub">游戏学英语 · 登录</p>
  <form method="post" action="/api/login">
    <div class="field">
      <label>用户名</label>
      <input type="text" name="username" placeholder="输入用户名" autocomplete="username">
    </div>
    <div class="field">
      <label>密码</label>
      <input type="password" name="password" placeholder="输入密码" autocomplete="current-password">
      <button class="eye-btn" onclick="togglePw(this)" type="button" tabindex="-1">👁️</button>
    </div>
    <button class="btn" type="submit">登 录</button>
  </form>
  <div class="error">{error}</div>
  <div class="links">
    还没有账号？<a href="/register">注册</a>
  </div>
</div>
<script>
function togglePw(btn) {
  var pw = btn.previousElementSibling;
  if (pw.type === 'password') { pw.type = 'text'; btn.textContent = '🙈'; }
  else { pw.type = 'password'; btn.textContent = '👁️'; }
}
</script>
</body>
</html>"""

REGISTER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Ogden 850 — 注册</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.31.0/dist/tabler-icons.min.css">
<style>
:root {
  --font-sans: 'Rounded Mplus 1c','M PLUS Rounded 1c',-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,sans-serif;
  --bg: #FEF7F0; --text: #3D2C25; --text2: #7A6B5E;
  --border: #E8DCC8; --card: #FFFFFF; --accent: #D4815A; --teal: #5C8A7A;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  background: var(--bg); min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--font-sans); padding: 20px;
}
.box {
  background: var(--card); border-radius: 14px; padding: 32px;
  box-shadow: 0 3px 12px rgba(212,129,90,0.10); width: 100%; max-width: 360px;
  border: 1px solid var(--border);
}
h1 { font-size: 20px; color: var(--text); margin-bottom: 4px; text-align: center; }
.sub { font-size: 13px; color: var(--text2); margin-bottom: 24px; text-align: center; }
.field { margin-bottom: 16px; position: relative; }
.field label { display: block; font-size: 13px; color: var(--text2); margin-bottom: 4px; }
.field input {
  width: 100%; padding: 10px 14px; border: 1px solid var(--border);
  border-radius: 10px; font-size: 14px; font-family: var(--font-sans);
  background: rgba(255,255,255,0.7); color: var(--text);
  outline: none; transition: border 0.2s; padding-right: 40px;
}
.field input:focus { border-color: var(--accent); }
.eye-btn {
  position: absolute; right: 10px; bottom: 6px;
  background: none; border: none; cursor: pointer;
  color: var(--text2); font-size: 18px; padding: 4px;
  display: flex; align-items: center;
}
.eye-btn:hover { color: var(--accent); }
.btn {
  width: 100%; padding: 10px; background: var(--accent); color: #fff;
  border: none; border-radius: 10px; font-size: 15px; font-family: var(--font-sans);
  cursor: pointer; transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.error { color: #C4696A; font-size: 13px; margin-top: 10px; text-align: center; }
.links { text-align: center; margin-top: 16px; font-size: 13px; }
.links a { color: var(--accent); text-decoration: none; }
.links a:hover { text-decoration: underline; }
.icon-head { color: var(--accent); font-size: 40px; display: block; text-align: center; margin-bottom: 8px; }
</style>
</head>
<body>
<div class="box">
  <i class="ti ti-user-plus icon-head"></i>
  <h1>创建账号</h1>
  <p class="sub">注册 Ogden 850 账号</p>
  <form method="post" action="/api/register">
    <div class="field">
      <label>用户名</label>
      <input type="text" name="username" placeholder="输入用户名" autocomplete="username">
    </div>
    <div class="field">
      <label>密码</label>
      <input type="password" name="password" placeholder="输入密码" autocomplete="new-password">
      <button class="eye-btn" onclick="togglePw(this)" type="button" tabindex="-1">👁️</button>
    </div>
    <div class="field">
      <label>确认密码</label>
      <input type="password" name="confirm" placeholder="再次输入密码" autocomplete="new-password">
    </div>
    <button class="btn" type="submit">注 册</button>
  </form>
  <div class="error">{error}</div>
  <div class="links">
    已有账号？<a href="/login">登录</a>
  </div>
</div>
<script>
function togglePw(btn) {
  var pw = btn.previousElementSibling;
  if (pw.type === 'password') { pw.type = 'text'; btn.textContent = '🙈'; }
  else { pw.type = 'password'; btn.textContent = '👁️'; }
}
</script>
</body>
</html>"""

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
    def _get_token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "token" in params:
            return params["token"][0]
        cookies = self.headers.get("Cookie", "")
        for c in cookies.split(";"):
            c = c.strip()
            if c.startswith("ogden_token="):
                return c[12:]
        return None

    def _check_auth(self):
        token = self._get_token()
        if token and verify_token(token):
            return True
        return False

    def _get_user(self):
        token = self._get_token()
        return verify_token(token)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode() if content_len else ""

        # Parse form data
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                data = {}
            get_val = lambda k, d="": data.get(k, d)
        else:
            params = parse_qs(body)
            get_val = lambda k, d="": (params.get(k, [d]) or [d])[0]

        if path == "/api/login":
            users = load_users()
            username = get_val("username").strip()
            password = get_val("password")
            accept_json = "application/json" in self.headers.get("Accept", "")
            if username in users and users[username] == password:
                token = make_token(username)
                if accept_json:
                    self._json(200, {"token": token, "username": username})
                else:
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.send_header("Set-Cookie", f"ogden_token={token}; Path=/; Max-Age=604800")
                    self.end_headers()
            else:
                if accept_json:
                    self._json(401, {"error": "用户名或密码错误"})
                else:
                    html = LOGIN_HTML.replace("{error}", "用户名或密码错误")
                    self._serve(html.encode(), "text/html; charset=utf-8")
            return

        if path == "/api/register":
            users = load_users()
            accept_json = "application/json" in self.headers.get("Accept", "")
            username = get_val("username").strip()
            password = get_val("password")
            confirm = get_val("confirm")

            errors = []
            if not username:
                errors.append("请输入用户名")
            elif len(username) < 2:
                errors.append("用户名至少2个字符")
            elif username in users:
                errors.append("用户名已被注册")

            if not password:
                errors.append("请输入密码")
            elif len(password) < 4:
                errors.append("密码至少4个字符")
            elif password != confirm:
                errors.append("两次密码不一致")

            if errors:
                if accept_json:
                    self._json(400, {"error": errors[0]})
                else:
                    html = REGISTER_HTML.replace("{error}", errors[0])
                    self._serve(html.encode(), "text/html; charset=utf-8")
            else:
                users[username] = password
                save_users(users)
                token = make_token(username)
                if accept_json:
                    self._json(200, {"token": token, "username": username})
                else:
                    self.send_response(302)
                    self.send_header("Location", "/")
                    self.send_header("Set-Cookie", f"ogden_token={token}; Path=/; Max-Age=604800")
                    self.end_headers()
            return

        if path == "/api/logout":
            # Clear cookie and redirect
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "ogden_token=; Path=/; Max-Age=0")
            self.end_headers()
            return

        self._json(404, {"error": "not found"})

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path.rstrip("/") or "/"

        # ── TTS endpoint (public) ──
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

        # ── Voices endpoint (public) ──
        if path == "/voices":
            self._json(200, {"en": EN_VOICES, "zh": ZH_VOICES})
            return

        # ── Verify token (public) ──
        if path == "/api/verify":
            token_str = self._get_token()
            if token_str and verify_token(token_str):
                self._json(200, {"valid": True})
            else:
                self._json(200, {"valid": False})
            return

        # ── Auth pages (public) ──
        if path == "/login":
            html = LOGIN_HTML.replace("{error}", "")
            self._serve(html.encode(), "text/html; charset=utf-8")
            return

        if path == "/register":
            html = REGISTER_HTML.replace("{error}", "")
            self._serve(html.encode(), "text/html; charset=utf-8")
            return

        if path == "/api/logout":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "ogden_token=; Path=/; Max-Age=0")
            self.end_headers()
            return

        # ── Static files (protected) ──
        if not self._check_auth():
            html = LOGIN_HTML.replace("{error}", "")
            self._serve(html.encode(), "text/html; charset=utf-8")
            return

        # Serve actual file
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(data)

    def _audio(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "max-age=86400")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code: int, obj: dict):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        print(f"[TTS] {self.address_string()} - {fmt % args}")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

if __name__ == "__main__":
    print(f"Ogden 850 TTS Server running on http://0.0.0.0:{PORT}")
    print(f"  HTTPS on https://0.0.0.0:8888")
    print(f"Voices: EN={len(EN_VOICES)}, ZH={len(ZH_VOICES)}")
    print(f"TTS cache: {CACHE}")
    print(f"Users file: {USERS_FILE}")
    print(f"Users: {list(load_users().keys())}")
    
    import ssl, socketserver
    
    # HTTP server
    httpd = HTTPServer(("0.0.0.0", PORT), Handler)
    
    # HTTPS server (same port 8887 with SSL)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain("/home/d/ogden850/server.crt", "/home/d/ogden850/server.key")
    
    class SecureHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        allow_reuse_address = True
    
    httpsd = SecureHTTPServer(("0.0.0.0", 8888), Handler)
    httpsd.socket = ctx.wrap_socket(httpsd.socket, server_side=True)
    
    import threading
    t = threading.Thread(target=httpsd.serve_forever, daemon=True)
    t.start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
        httpsd.shutdown()
