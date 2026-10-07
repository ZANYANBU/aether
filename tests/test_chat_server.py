"""
Tests for chat_server.py.

Standard library only, like the server itself:

    python3 -m unittest discover -s tests -v

No Ollama is needed. A small stand-in server plays its part, so the tests check
what Aether sends to Ollama and what it hands back to the browser.
"""

import http.client
import http.server
import json
import os
import socket
import sys
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import chat_server  # noqa: E402


class FakeOllama(http.server.BaseHTTPRequestHandler):
    """Answers the two Ollama endpoints Aether calls, and records each chat."""

    models = ["qwen2.5:7b", "llava:13b", "gemma2:2b"]
    chats = []
    reply = [b'{"message":{"content":"Hel"}}\n', b'{"message":{"content":"lo"},"done":true}\n']

    def do_GET(self):
        if self.path != "/api/tags":
            return self.send_error(404)
        body = json.dumps({"models": [{"name": n} for n in self.models]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/chat":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0))
        type(self).chats.append(json.loads(self.rfile.read(length)))
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for line in self.reply:
            self.wfile.write(line)

    def log_message(self, *a):
        pass


def serve(handler):
    server = chat_server.Server(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def unused_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ModelRouting(unittest.TestCase):
    def test_vision_models_are_recognised_by_name(self):
        for name in ("llava:13b", "qwen2.5vl:3b", "moondream", "llama3.2-vision:11b", "MiniCPM-V"):
            self.assertTrue(chat_server.is_vision(name), name)

    def test_text_models_are_not_vision(self):
        for name in ("qwen2.5:7b", "llama3.1:8b", "mistral", "gemma2:2b"):
            self.assertFalse(chat_server.is_vision(name), name)

    def test_default_model_when_none_is_chosen(self):
        self.assertEqual(chat_server.pick_model(None, []), chat_server.DEFAULT_MODEL)
        self.assertEqual(chat_server.pick_model("", []), chat_server.DEFAULT_MODEL)

    def test_the_chosen_model_is_honoured_for_text(self):
        messages = [{"role": "user", "content": "hi"}]
        self.assertEqual(chat_server.pick_model("mistral", messages), "mistral")

    def test_an_image_switches_a_text_model_to_the_vision_model(self):
        messages = [{"role": "user", "content": "what is this?", "images": ["aGVsbG8="]}]
        self.assertEqual(chat_server.pick_model("mistral", messages), chat_server.VISION_MODEL)

    def test_an_image_keeps_a_vision_model_the_user_chose(self):
        messages = [{"role": "user", "content": "what is this?", "images": ["aGVsbG8="]}]
        self.assertEqual(chat_server.pick_model("llava:13b", messages), "llava:13b")

    def test_an_empty_image_list_does_not_switch_models(self):
        messages = [{"role": "user", "content": "hi", "images": []}]
        self.assertEqual(chat_server.pick_model("mistral", messages), "mistral")


class HTTPTestCase(unittest.TestCase):
    """Runs Aether against the stand-in Ollama, each on a free local port."""

    @classmethod
    def setUpClass(cls):
        cls.cwd = os.getcwd()
        os.chdir(ROOT)                      # the server serves index.html from here
        cls.real_ollama = chat_server.OLLAMA
        cls.ollama = serve(FakeOllama)
        cls.ollama_url = "http://127.0.0.1:%d" % cls.ollama.server_address[1]
        cls.app = serve(chat_server.Handler)
        cls.port = cls.app.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.app.shutdown()
        cls.app.server_close()
        cls.ollama.shutdown()
        cls.ollama.server_close()
        chat_server.OLLAMA = cls.real_ollama
        os.chdir(cls.cwd)

    def setUp(self):
        chat_server.OLLAMA = self.ollama_url
        FakeOllama.chats.clear()

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response, payload


class Pages(HTTPTestCase):
    def test_root_serves_the_chat_page(self):
        for path in ("/", "/index.html"):
            response, body = self.request("GET", path)
            self.assertEqual(response.status, 200, path)
            self.assertIn(b"<title>Aether", body)

    def test_capabilities_reports_voice_and_the_default_model(self):
        response, body = self.request("GET", "/capabilities")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(body),
                         {"voice_input": chat_server.VOICE_INPUT, "default": chat_server.DEFAULT_MODEL})

    def test_unknown_post_is_404(self):
        response, _ = self.request("POST", "/nope", {})
        self.assertEqual(response.status, 404)

    @unittest.skipIf(chat_server.VOICE_INPUT, "faster-whisper is installed")
    def test_transcribe_says_so_when_voice_is_not_installed(self):
        response, _ = self.request("POST", "/transcribe", {})
        self.assertEqual(response.status, 501)


class Models(HTTPTestCase):
    def test_lists_installed_models_sorted(self):
        response, body = self.request("GET", "/models")
        self.assertEqual(response.status, 200)
        data = json.loads(body)
        self.assertEqual(data["models"], sorted(FakeOllama.models))
        self.assertEqual(data["default"], chat_server.DEFAULT_MODEL)
        self.assertEqual(data["vision_model"], chat_server.VISION_MODEL)

    def test_default_falls_back_to_the_first_installed_model(self):
        installed = FakeOllama.models
        FakeOllama.models = ["mistral", "gemma2:2b"]
        try:
            _, body = self.request("GET", "/models")
        finally:
            FakeOllama.models = installed
        self.assertEqual(json.loads(body)["default"], "gemma2:2b")

    def test_an_unreachable_ollama_gives_an_empty_list_not_an_error(self):
        chat_server.OLLAMA = "http://127.0.0.1:%d" % unused_port()
        response, body = self.request("GET", "/models")
        self.assertEqual(response.status, 200)
        data = json.loads(body)
        self.assertEqual(data["models"], [])
        self.assertEqual(data["default"], chat_server.DEFAULT_MODEL)


class Chat(HTTPTestCase):
    def test_the_reply_is_streamed_through_unchanged(self):
        response, body = self.request("POST", "/chat", {
            "model": "gemma2:2b", "messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Content-Type"), "application/x-ndjson")
        self.assertEqual(response.getheader("X-Model"), "gemma2:2b")
        self.assertEqual(body, b"".join(FakeOllama.reply))

    def test_ollama_receives_the_messages_model_and_temperature(self):
        messages = [{"role": "user", "content": "hi"}]
        self.request("POST", "/chat", {"model": "gemma2:2b", "messages": messages, "temperature": 0.2})
        self.assertEqual(FakeOllama.chats, [{
            "model": "gemma2:2b", "messages": messages, "stream": True,
            "options": {"temperature": 0.2}}])

    def test_temperature_defaults_to_0_7(self):
        self.request("POST", "/chat", {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(FakeOllama.chats[0]["options"], {"temperature": 0.7})
        self.assertEqual(FakeOllama.chats[0]["model"], chat_server.DEFAULT_MODEL)

    def test_an_attached_image_is_routed_to_the_vision_model(self):
        messages = [{"role": "user", "content": "what is this?", "images": ["aGVsbG8="]}]
        response, _ = self.request("POST", "/chat", {"model": "gemma2:2b", "messages": messages})
        self.assertEqual(response.getheader("X-Model"), chat_server.VISION_MODEL)
        self.assertEqual(FakeOllama.chats[0]["model"], chat_server.VISION_MODEL)
        self.assertEqual(FakeOllama.chats[0]["messages"], messages)

    def test_an_unreachable_ollama_is_reported_as_502(self):
        chat_server.OLLAMA = "http://127.0.0.1:%d" % unused_port()
        response, _ = self.request("POST", "/chat", {"messages": [{"role": "user", "content": "hi"}]})
        self.assertEqual(response.status, 502)


if __name__ == "__main__":
    unittest.main()
