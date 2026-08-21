#!/usr/bin/env bash
# Start everything Ratchet needs, in the right order, from durable paths.
#
#   ./start-demo.sh
#
# Run it from an interactive shell so MOONSHOT_API_KEY is loaded from ~/.zshrc.
# It refuses to start rather than come up half-broken, because a demo that fails
# on camera for an environment reason is worse than one that does not start.

set -euo pipefail

GLC=~/ws/projects/glc_v3
S17=~/ws/projects/S17Code
RATCHET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE=${RATCHET_WORKSPACE:-/tmp/ratchet-demo}

if [ -z "${MOONSHOT_API_KEY:-}" ]; then
  echo "MOONSHOT_API_KEY is not set."
  echo "Open a normal terminal (so ~/.zshrc is sourced) and run this again."
  exit 1
fi

# The old gateway ran from /private/tmp/s14, whose source was deleted, so every
# provider call returned [Errno 2]. Kill it and serve from the durable clone.
if lsof -nP -iTCP:8111 -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "stopping whatever is on 8111"
  lsof -nP -iTCP:8111 -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
  sleep 2
fi

echo "starting glc_v3 gateway on 8111"
( cd "$GLC" && nohup uv run glc serve > /tmp/glc.log 2>&1 & )

for i in $(seq 1 30); do
  if curl -sf --max-time 3 http://127.0.0.1:8111/healthz >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -sf --max-time 5 http://127.0.0.1:8111/healthz >/dev/null || {
  echo "gateway did not come up. last lines of /tmp/glc.log:"; tail -20 /tmp/glc.log; exit 1; }

# Prove the model path before the camera is on, not during the take.
echo "checking the moonshot provider actually answers"
probe=$(curl -s --max-time 300 -X POST http://127.0.0.1:8111/v1/chat \
  -H 'content-type: application/json' \
  -d '{"provider":"moonshot","messages":[{"role":"user","content":"Reply with exactly: ok"}],"max_tokens":3000}')
case "$probe" in
  *'"detail"'*) echo "gateway is up but moonshot is failing:"; echo "$probe" | head -c 400; echo; exit 1 ;;
esac
echo "  moonshot answered"

# Demo workspace: a real defect for phase A to capture and phase B to fix.
mkdir -p "$WORKSPACE/tests"
cat > "$WORKSPACE/calc.py" <<'PY'
def divide(a, b):
    """Divide a by b. Returns 0 when b is zero."""
    return a / b
PY
[ -d "$WORKSPACE/.venv" ] || ( cd "$WORKSPACE" && python3 -m venv .venv && ./.venv/bin/pip -q install pytest )

if lsof -nP -iTCP:8117 -sTCP:LISTEN -t >/dev/null 2>&1; then
  lsof -nP -iTCP:8117 -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
  sleep 1
fi

echo "starting ratchet on 8117"
cd "$RATCHET"
S17CODE_ROOT="$S17" \
RATCHET_WORKSPACE="$WORKSPACE" \
RATCHET_PYTEST="$WORKSPACE/.venv/bin/python -m pytest -q" \
S17_GATEWAY_PROVIDER=moonshot \
GLC_BASE_URL=http://127.0.0.1:8111 \
nohup "$S17/.venv/bin/python" -m uvicorn app:app --port 8117 > /tmp/ratchet.log 2>&1 &

for i in $(seq 1 20); do
  if curl -sf --max-time 3 http://127.0.0.1:8117/health >/dev/null 2>&1; then break; fi
  sleep 1
done
echo
curl -s --max-time 5 http://127.0.0.1:8117/health
echo
echo "Ready. Open http://127.0.0.1:8117/"
echo "Logs: /tmp/glc.log (gateway), /tmp/ratchet.log (ratchet)"
