#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "== Health =="
curl -s "${BASE_URL}/health" | python -m json.tool

echo
echo "== Models =="
curl -s "${BASE_URL}/v1/models" | python -m json.tool

echo
echo "== Chat (non-stream) with headers =="
curl -i -s "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: demo-trace-1" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Say hi in one sentence"}],"stream":false}' \
  | head -20

echo
echo "== Chat (stream) =="
curl -N -s "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: demo-trace-2" \
  -d '{"model":"fast/demo","messages":[{"role":"user","content":"Count to 3"}],"stream":true}' \
  | head -15

echo
echo "== Provider health (debug) =="
curl -s "${BASE_URL}/debug/health/providers" | python -m json.tool

echo
echo "Done. Auth is not enabled yet (Phase 2)."
echo "Future: -H \"Authorization: Bearer \$GATEWAY_API_KEY\""
