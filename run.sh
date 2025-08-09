#!/bin/bash

# FAR Comms Startup Script (Cheng's setup)  
# Usage: ./scripts/run_far_comms.sh [--tunnel]

set -e

# Parse arguments
RUN_TUNNEL=false
if [[ "$1" == "--tunnel" ]]; then
    RUN_TUNNEL=true
fi

# Cleanup function
cleanup() {
    echo -e "\n🛑 Stopping services..."
    [[ -n "$TUNNEL_PID" ]] && kill $TUNNEL_PID 2>/dev/null || true
    [[ -n "$SERVER_PID" ]] && kill $SERVER_PID 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start tunnel if requested (background)
if [[ "$RUN_TUNNEL" == "true" ]]; then
    echo "🌐 Starting tunnel..."
    cloudflared tunnel --url "http://localhost:8000" > output/tunnel.log 2>&1 &
    TUNNEL_PID=$!
    
    # Wait for tunnel to fully start and generate URL
    sleep 5
    echo "Tunnel URL:"
    grep -o 'https://[^[:space:]]*\.trycloudflare\.com' output/tunnel.log | head -1 || echo "   Still starting... check output/tunnel.log"
    echo ""
fi

# Start server (FOREGROUND - you'll see all logs)
eval "$(conda shell.bash hook)"
conda activate llm-agents
echo "API docs: http://localhost:8000/docs"
echo "Press Ctrl+C to stop"
echo ""
PYTHONPATH=src uvicorn far_comms.main:app --reload --port 8000