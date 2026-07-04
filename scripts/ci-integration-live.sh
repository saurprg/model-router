#!/usr/bin/env bash
# Optional live upstream checks for GitHub Actions integration workflow.
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "== T01 health =="
curl -sf "${BASE_URL}/health" | grep '"status":"ok"'

echo "== T02 models =="
curl -sf "${BASE_URL}/v1/models" | grep 'fast/demo'

if [ -n "${GROQ_API_KEY:-}" ]; then
  echo "== T05 Groq chat =="
  curl -sf "${BASE_URL}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi"}],"stream":false}' \
    | grep 'llama-3.1-8b-instant'
else
  echo "== T05 Groq chat: SKIP (GROQ_API_KEY not set) =="
fi

if [ -n "${DO_MODEL_ACCESS_KEY:-}" ]; then
  echo "== T04 DO chat =="
  curl -sf "${BASE_URL}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{"model":"do/llama","messages":[{"role":"user","content":"Say hi"}],"stream":false}' \
    | grep 'llama3.3-70b-instruct'
else
  echo "== T04 DO chat: SKIP (DO_MODEL_ACCESS_KEY not set) =="
fi

echo "Integration live checks finished."
