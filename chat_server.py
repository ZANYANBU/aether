"""
Local multimodal chat server for Qwen on Ollama — text, vision, and voice.

  python3 chat_server.py            # text + vision + talk-back (voice output)
  .venv/bin/python chat_server.py   # ^ plus voice input (local Whisper)

Everything runs on your machine:
  * text replies  -> qwen2.5:7b        (via Ollama, port 11434)
  * image replies -> qwen2.5vl:3b      (auto-selected when a photo is attached)
  * speech -> text -> local Whisper    (only if faster-whisper is installed)
  * text -> speech -> your browser's built-in local voices (no server needed)

This server itself has ZERO required dependencies (Python stdlib). Voice INPUT
is an optional bonus: install it with `pip install faster-whisper` and run the
server with the venv Python.
"""

import io
import json
import tempfile
import urllib.request
import http.server
import socketserver

PORT = 8100
MODEL_TEXT = "qwen2.5:7b"       # smart text model
MODEL_VISION = "qwen2.5vl:3b"   # can see images (also handles text)
OLLAMA = "http://localhost:11434/api/chat"

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


def has_image(messages):
    return any(m.get("images") for m in messages)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/capabilities":
            return self._json({"voice_input": VOICE_INPUT,
                               "text_model": MODEL_TEXT, "vision_model": MODEL_VISION})
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/chat":
            return self._chat()
        if self.path == "/transcribe":
            return self._transcribe()
        self.send_error(404)

    # ---- chat: proxy to Ollama, pick model by whether an image is present --
    def _chat(self):
        body = self._read_json()
        messages = body.get("messages", [])
        model = MODEL_VISION if has_image(messages) else MODEL_TEXT
        payload = json.dumps({
            "model": model, "messages": messages, "stream": True,
            "options": {"temperature": body.get("temperature", 0.7)},
        }).encode()
        req = urllib.request.Request(OLLAMA, data=payload,
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
    print(f"\n  Qwen multimodal chat -> http://localhost:{PORT}")
    print(f"  text: {MODEL_TEXT}   vision: {MODEL_VISION}   voice-input: {v}\n")
    Server(("", PORT), Handler).serve_forever()
