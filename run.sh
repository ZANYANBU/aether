#!/usr/bin/env bash
# One-command launcher for the Qwen local chat.
# Checks Ollama is installed + running, pulls the model if missing, starts the UI.
set -e

MODEL_TEXT="qwen2.5:7b"
MODEL_VISION="qwen2.5vl:3b"
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

# Pull the models if we don't have them yet.
for m in "$MODEL_TEXT" "$MODEL_VISION"; do
  if ! ollama list | grep -q "${m%%:*}"; then
    echo "⬇ pulling ${m} (one time)..."
    ollama pull "$m"
  fi
done

# Use the venv Python if it exists (enables local Whisper voice input), else system python3.
PY="python3"; [ -x ".venv/bin/python" ] && PY=".venv/bin/python"

echo "✅ ready — open http://localhost:${PORT}"
"$PY" chat_server.py
