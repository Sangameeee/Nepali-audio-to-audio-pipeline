#!/usr/bin/env bash
# ==============================================================================
# Voice Assistant - Run Script
# File: run.sh
#
# Convenience script to start the Voice Assistant application.
# Usage:
#   chmod +x run.sh
#   ./run.sh
#
# Options:
#   --dev       Run in development mode with auto-reload
#   --prod      Run in production mode
#   --port PORT Specify port (default: 8000)
# ==============================================================================

set -e

# Defaults
PORT=8000
RELOAD="--reload"
HOST="0.0.0.0"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev)
            RELOAD="--reload"
            shift
            ;;
        --prod)
            RELOAD=""
            shift
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: ./run.sh [--dev|--prod] [--port PORT]"
            exit 1
            ;;
    esac
done

# Navigate to backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/backend"

# Check for virtual environment
if [ -d "$SCRIPT_DIR/venv" ]; then
    source "$SCRIPT_DIR/venv/bin/activate"
    echo "✓ Virtual environment activated"
fi

# Check for .env file
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "✓ Created .env from .env.example"
fi

# Create temp directories
mkdir -p temp
mkdir -p "$SCRIPT_DIR/models/tts/outputs"

echo "═══════════════════════════════════════════"
echo "  Voice Assistant"
echo "  Starting on http://localhost:$PORT"
echo "═══════════════════════════════════════════"

# Run the server
uvicorn app.main:app $RELOAD --host $HOST --port $PORT
