#!/usr/bin/env bash
# Smoke test against a running Compose stack: upload -> poll -> download.
set -euo pipefail
BASE="${BASE_URL:-http://localhost:${API_PORT:-8000}}"
DATA="$(dirname "$0")/../tests/data"

for i in $(seq 1 30); do curl -sf "$BASE/health" >/dev/null && break; sleep 1; done
curl -sf "$BASE/health" >/dev/null || { echo "API not reachable at $BASE"; exit 1; }

resp=$(curl -sf -F obs=@"$DATA/my_data_3.obs" -F nav=@"$DATA/samsung_nav.nav.rnx" "$BASE/jobs")
id=$(echo "$resp" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)
echo "job $id"

for i in $(seq 1 60); do
  body=$(curl -sf "$BASE/jobs/$id")
  status=$(echo "$body" | grep -o '"status":"[a-z]*"' | cut -d'"' -f4)
  [ "$status" = succeeded ] || [ "$status" = failed ] && break
  sleep 1
done
echo "$body"
[ "$status" = succeeded ] || { echo "job ended as: $status"; exit 1; }

lines=$(curl -sf "$BASE/jobs/$id/result/clean.csv" | wc -l)
[ "$lines" -gt 1 ] || { echo "empty result"; exit 1; }
echo "OK: clean.csv has $lines lines"
