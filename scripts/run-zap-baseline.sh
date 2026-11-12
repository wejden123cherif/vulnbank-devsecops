#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT=18999
TARGET="http://127.0.0.1:${PORT}"
REPORT_DIR="$PWD/security-reports/zap/ci"

mkdir -p "$REPORT_DIR"
cp zap-rules.conf "$REPORT_DIR/zap-rules.conf"

# Start a localhost-only connection to the Kubernetes web Deployment.
kubectl -n vulnbank port-forward \
  --address 127.0.0.1 \
  deployment/vulnbank-web "${PORT}:5000" \
  > "$REPORT_DIR/port-forward.log" 2>&1 &

PF_PID=$!

cleanup() {
  kill "$PF_PID" 2>/dev/null || true
  wait "$PF_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Verify that the deployed application is reachable.
READY=0
for i in $(seq 1 30); do
  if curl --max-time 3 -fsS "$TARGET/healthz" >/dev/null; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "ERROR: Kubernetes application is not reachable"
  cat "$REPORT_DIR/port-forward.log"
  exit 1
fi

echo "Running ZAP baseline against $TARGET"

# Capture ZAP's exit code so accepted warnings do not fail CI.
set +e
docker run --rm \
  --network host \
  --user "$(id -u):$(id -g)" \
  -v "$REPORT_DIR:/zap/wrk:rw" \
  -e HOME=/tmp \
  ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py \
  -t "$TARGET" \
  -d \
  -m 2 \
  -c zap-rules.conf \
  -r baseline-ci.html \
  -J baseline-ci.json

RESULT=$?
set -e

case "$RESULT" in
  0)
    echo "PASS: No blocking findings"
    ;;
  1)
    echo "FAIL: A prohibited vulnerability was detected"
    exit 1
    ;;
  2)
    echo "PASS with warnings: Review the ZAP report"
    ;;
  *)
    echo "FAIL: ZAP encountered an execution error: $RESULT"
    exit 1
    ;;
esac
