"""
Local chat UI for Qwen 2.5 7B running on Ollama.

  python3 chat_server.py        # -> http://localhost:8100

Ollama serves the model on port 11434. This tiny stdlib server does two jobs:
  1. serves index.html (the chat page)
  2. proxies POST /chat -> Ollama's /api/chat, streaming tokens straight
     through so the browser can render the reply as it's generated.

No pip installs, no web framework. Just talks to Ollama over HTTP.
"""

import json
import urllib.request
import http.server
import socketserver

PORT = 8100
MODEL = "qwen2.5:7b"
OLLAMA = "http://localhost:11434/api/chat"


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path != "/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or "{}")

        payload = json.dumps({
            "model": MODEL,
            "messages": body.get("messages", []),
            "stream": True,
            "options": {"temperature": body.get("temperature", 0.7)},
        }).encode()

        req = urllib.request.Request(
            OLLAMA, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            upstream = urllib.request.urlopen(req)
        except Exception as e:
            self.send_error(502, f"Ollama not reachable: {e}")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for line in upstream:          # each line is one JSON token-chunk
                self.wfile.write(line)     # pass it straight to the browser
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass                           # user navigated away mid-stream

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    print(f"\n  Qwen chat -> http://localhost:{PORT}   (model: {MODEL}, ctrl-C to stop)\n")
    Server(("", PORT), Handler).serve_forever()
