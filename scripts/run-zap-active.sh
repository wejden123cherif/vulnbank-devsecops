#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PROJECT="vulnbank-dast-${CI_PIPELINE_ID:-local}"
COMPOSE_FILE="docker-compose.dast.yml"
TARGET="http://127.0.0.1:19001"
REPORT_DIR="$PWD/security-reports/zap/active"

mkdir -p "$REPORT_DIR"
cp zap-rules.conf "$REPORT_DIR/zap-rules.conf"

# Generate disposable credentials. Never use existing database secrets.
export DAST_DB_PASSWORD="$(openssl rand -hex 24)"
export DAST_ADMIN_PASSWORD="$(openssl rand -hex 24)"
export DAST_TEST_PASSWORD="$(openssl rand -hex 24)"
export DAST_SECRET_KEY="$(openssl rand -hex 32)"
export DAST_JWT_SECRET="$(openssl rand -hex 32)"

cleanup() {
  docker rm -f "vulnbank-zap-active-${CI_PIPELINE_ID:-local}" >/dev/null 2>&1 || true
  echo "Cleaning up isolated DAST environment..."
  docker-compose -p "$PROJECT" -f "$COMPOSE_FILE" \
    down --remove-orphans || true
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "Starting isolated VulnBank environment..."
docker-compose -p "$PROJECT" -f "$COMPOSE_FILE" \
  up -d --build

echo "Waiting for disposable VulnBank to become ready..."
READY=0

for i in $(seq 1 60); do
  if curl --silent --fail --max-time 3 "$TARGET/healthz" \
      >/dev/null; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "ERROR: Disposable application is not ready."
  docker-compose -p "$PROJECT" -f "$COMPOSE_FILE" \
    logs --tail=60
  exit 1
fi

echo "Running ZAP Active DAST against $TARGET"

set +e

timeout --signal=TERM --kill-after=20s 25m \
  docker run --rm \
    --name "vulnbank-zap-active-${CI_PIPELINE_ID:-local}" \
    --network host \
    --user "$(id -u):$(id -g)" \
    --workdir /zap/wrk \
    -v "$REPORT_DIR:/zap/wrk:rw" \
    -e HOME=/tmp \
    ghcr.io/zaproxy/zaproxy:stable \
    zap-full-scan.py \
    -t "$TARGET" \
    -z "-silent -dir /tmp/zap-home" \
    -T 10 \
    -m 2 \
    -c zap-rules.conf \
    -r active-ci.html \
    -J active-ci.json

RESULT=$?
set -e

case "$RESULT" in
  0)
    echo "PASS: Active scan completed without findings"
    ;;
  1)
    echo "FAIL: Active scan detected a blocking finding"
    exit 1
    ;;
  2)
    echo "ACTIVE SCAN COMPLETE: Security warnings found"
    ;;
  124|137)
    echo "ERROR: Active scan exceeded the time limit"
    exit 1
    ;;
  *)
    echo "ERROR: ZAP active scan failed: $RESULT"
    exit 1
    ;;
esac
