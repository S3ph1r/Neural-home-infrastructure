#!/bin/bash
# Move to project root
cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)

# Use explicit python from venv
PYTHON="$PROJECT_DIR/venv/bin/python"
UVICORN="$PROJECT_DIR/venv/bin/uvicorn"

echo "Starting Orchestrator from $PROJECT_DIR..."

if [ ! -f "$UVICORN" ]; then
    echo "Error: uvicorn not found at $UVICORN"
    exit 1
fi

# Kill existing (be careful but firm)
pkill -f "uvicorn orchestrator.main:app" || true

# Start with nohup
nohup "$UVICORN" orchestrator.main:app --host 0.0.0.0 --port 8000 > "$PROJECT_DIR/orchestrator.log" 2>&1 < /dev/null &
PID=$!

echo "Orchestrator started with PID $PID. Logs in $PROJECT_DIR/orchestrator.log"
sleep 3

if ps -p $PID > /dev/null; then
  echo "Process is running (PID $PID)."
  exit 0
else
  echo "Process died immediately. Last 20 lines of log:"
  tail -n 20 "$PROJECT_DIR/orchestrator.log"
  exit 1
fi
