"""
A private, 100% local AI chat server — works with ANY Ollama model.

  python3 chat_server.py            # text + vision + talk-back
  .venv/bin/python chat_server.py   # ^ plus voice input (local Whisper)

Nothing leaves your machine. This tiny stdlib server:
  * lists whatever models you have installed (GET /models)
  * proxies chat to Ollama, streaming tokens straight to the browser
  * auto-routes to a vision model when you attach an image
  * (optionally) transcribes speech on-device with faster-whisper

The core server has ZERO required dependencies. Voice input is an optional
bonus: `pip install faster-whisper` and run with the venv Python.
"""

import json
import tempfile
import urllib.request
import http.server
import socketserver

PORT = 8100
DEFAULT_MODEL = "qwen2.5:7b"    # used if the browser hasn't picked one yet
VISION_MODEL = "qwen2.5vl:3b"   # auto-used when an image is attached
OLLAMA = "http://localhost:11434"

VISION_HINTS = ("vl", "llava", "vision", "moondream", "bakllava", "minicpm-v", "llama3.2-vision")

# ---- optional local speech-to-text (Whisper) -----------------------------
try:
    from faster_whisper import WhisperModel
    _whisper = None
    def get_whisper():
        global _whisper
        if _whisper is None:
            print("loading Whisper (base.en)…")
            _whisper = WhisperModel("base.en", device="cpu", compute_type="int8")
        return _whisper
    VOICE_INPUT = True
except Exception:
    VOICE_INPUT = False


def is_vision(name):
    return any(h in name.lower() for h in VISION_HINTS)


def pick_model(chosen, messages):
    """Honor the user's choice; switch to a vision model only when needed."""
    model = chosen or DEFAULT_MODEL
    if any(m.get("images") for m in messages) and not is_vision(model):
        return VISION_MODEL
    return model


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/models":
            return self._models()
        if self.path == "/capabilities":
            return self._json({"voice_input": VOICE_INPUT, "default": DEFAULT_MODEL})
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/chat":
            return self._chat()
        if self.path == "/transcribe":
            return self._transcribe()
        self.send_error(404)

    # ---- list installed Ollama models -------------------------------------
    def _models(self):
        try:
            with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=5) as r:
                tags = json.load(r).get("models", [])
            names = sorted(m["name"] for m in tags)
        except Exception:
            names = []
        default = DEFAULT_MODEL if DEFAULT_MODEL in names else (names[0] if names else DEFAULT_MODEL)
        self._json({"models": names, "default": default, "vision_model": VISION_MODEL})

    # ---- chat: stream from Ollama, model chosen by the client -------------
    def _chat(self):
        body = self._read_json()
        messages = body.get("messages", [])
        model = pick_model(body.get("model"), messages)
        payload = json.dumps({
            "model": model, "messages": messages, "stream": True,
            "options": {"temperature": body.get("temperature", 0.7)},
        }).encode()
        req = urllib.request.Request(OLLAMA + "/api/chat", data=payload,
                                     headers={"Content-Type": "application/json"})
        try:
            upstream = urllib.request.urlopen(req)
        except Exception as e:
            return self.send_error(502, f"Ollama not reachable: {e}")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("X-Model", model)
        self.end_headers()
        try:
            for line in upstream:
                self.wfile.write(line); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ---- transcribe: raw audio bytes -> text, via local Whisper ------------
    def _transcribe(self):
        if not VOICE_INPUT:
            return self.send_error(501, "Voice input not installed (pip install faster-whisper)")
        length = int(self.headers.get("Content-Length", 0))
        audio = self.rfile.read(length)
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=True) as f:
            f.write(audio); f.flush()
            segments, _ = get_whisper().transcribe(f.name, beam_size=1)
            text = "".join(s.text for s in segments).strip()
        self._json({"text": text})

    # ---- helpers -----------------------------------------------------------
    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or "{}")

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    v = "ON (local Whisper)" if VOICE_INPUT else "off (pip install faster-whisper to enable)"
    print(f"\n  Local AI chat -> http://localhost:{PORT}")
    print(f"  default model: {DEFAULT_MODEL}   vision: {VISION_MODEL}   voice-input: {v}")
    print("  (pick any installed model from the dropdown in the UI)\n")
    Server(("", PORT), Handler).serve_forever()
