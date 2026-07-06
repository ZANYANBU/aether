#!/usr/bin/env bash
# One-command launcher for the Qwen local chat.
# Checks Ollama is installed + running, pulls the model if missing, starts the UI.
set -e

MODEL="qwen2.5:7b"
PORT="8100"

if ! command -v ollama >/dev/null 2>&1; then
  echo "❌ Ollama not found. Install it first:  brew install ollama"
  exit 1
fi

# Start the Ollama server in the background if it isn't already up.
if ! curl -s http://localhost:11434/api/version >/dev/null 2>&1; then
  echo "▶ starting ollama server..."
  ollama serve >/tmp/ollama.log 2>&1 &
  until curl -s http://localhost:11434/api/version >/dev/null 2>&1; do sleep 1; done
fi

# Pull the model if we don't have it yet.
if ! ollama list | grep -q "${MODEL%%:*}"; then
  echo "⬇ pulling ${MODEL} (~4.7 GB, one time)..."
  ollama pull "$MODEL"
fi

echo "✅ ready — open http://localhost:${PORT}"
python3 chat_server.py
