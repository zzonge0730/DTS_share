#!/usr/bin/env bash
set -euo pipefail

# Adapter (acts as Vision peer for DTS)
ADAPTER_LISTEN_HOST="${ADAPTER_LISTEN_HOST:-0.0.0.0}"
ADAPTER_LISTEN_PORT="${ADAPTER_LISTEN_PORT:-50001}"
MECH_HOST="${MECH_HOST:-}"
MECH_PORT="${MECH_PORT:-8000}"
QUERY_MODE="${QUERY_MODE:-vision}" # vision|viz205|viz_full
VIZ_USE_BRANCH="${VIZ_USE_BRANCH:-false}"
VIZ_BRANCH_NAME="${VIZ_BRANCH_NAME:-1}"
VIZ_BRANCH_EXIT="${VIZ_BRANCH_EXIT:-1}"
VIZ_USE_INDEX="${VIZ_USE_INDEX:-false}"
VIZ_INDEX_SKILL="${VIZ_INDEX_SKILL:-1}"
VIZ_INDEX_COUNT="${VIZ_INDEX_COUNT:-1}"
FALLBACK_COUNT="${FALLBACK_COUNT:-7}"
PAYLOAD_FILE="${PAYLOAD_FILE:-}"

# Robot mock
ROBOT_BIND_HOST="${ROBOT_BIND_HOST:-0.0.0.0}"
ROBOT_BIND_PORT="${ROBOT_BIND_PORT:-2000}"
ROBOT_TARGET_HOST="${ROBOT_TARGET_HOST:-172.21.128.1}"
ROBOT_TARGET_PORT="${ROBOT_TARGET_PORT:-2001}"
ROBOT_READY_INTERVAL="${ROBOT_READY_INTERVAL:-1.0}"
STATUS_PORT="${STATUS_PORT:-2002}"

# Gap mock writer (for DTS EvaluateGap JSON input)
# Keep default aligned with DTS App.config relative path (DTS.exe working dir).
GAP_JSON_OUT="${GAP_JSON_OUT:-DTS/DTS/Workspace/DTS/DTS/bin/Debug/gap_input.json}"
GAP_MODE="${GAP_MODE:-ok}" # ok|ng|ng_avg|stale|invalid|icp_low|icp_high|icp_bad|icp_missing
GAP_INTERVAL="${GAP_INTERVAL:-0.5}"

echo "[e2e] start gap writer: ${GAP_MODE} -> ${GAP_JSON_OUT}"
python3 mock/mock_gap_writer.py \
  --out "$GAP_JSON_OUT" \
  --mode "$GAP_MODE" \
  --interval "$GAP_INTERVAL" &
GAP_PID=$!

echo "[e2e] start robot mock: ${ROBOT_BIND_HOST}:${ROBOT_BIND_PORT} (status:${STATUS_PORT})"
python3 mock/mock_robot_udp.py \
  --bind-host "$ROBOT_BIND_HOST" \
  --bind-port "$ROBOT_BIND_PORT" \
  --target-host "$ROBOT_TARGET_HOST" \
  --target-port "$ROBOT_TARGET_PORT" \
  --ready-interval "$ROBOT_READY_INTERVAL" \
  --status-port "$STATUS_PORT" &
ROBOT_PID=$!

echo "[e2e] start adapter: ${ADAPTER_LISTEN_HOST}:${ADAPTER_LISTEN_PORT}"
adapter_args=(
  --listen-host "$ADAPTER_LISTEN_HOST"
  --listen-port "$ADAPTER_LISTEN_PORT"
  --mech-host "$MECH_HOST"
  --mech-port "$MECH_PORT"
  --query-mode "$QUERY_MODE"
  --viz-branch-name "$VIZ_BRANCH_NAME"
  --viz-branch-exit "$VIZ_BRANCH_EXIT"
  --viz-index-skill "$VIZ_INDEX_SKILL"
  --viz-index-count "$VIZ_INDEX_COUNT"
  --fallback-count "$FALLBACK_COUNT"
)
if [ "$VIZ_USE_BRANCH" = "true" ]; then
  adapter_args+=(--viz-use-branch)
fi
if [ "$VIZ_USE_INDEX" = "true" ]; then
  adapter_args+=(--viz-use-index)
fi
if [ -n "$PAYLOAD_FILE" ]; then
  adapter_args+=(--payload-file "$PAYLOAD_FILE")
fi
python3 mock/mech_adapter_tcp.py "${adapter_args[@]}" &
ADAPTER_PID=$!

echo "[e2e] running. stop with Ctrl+C"
echo "[e2e] set DTS App.config key GAP_JSON_PATH=${GAP_JSON_OUT}"
echo "[e2e] then in DTS GUI: Connect_Vision -> Connect_Robot"

cleanup() {
  kill "$ADAPTER_PID" "$ROBOT_PID" "$GAP_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait
