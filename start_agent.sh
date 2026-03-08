#!/bin/bash
set -euo pipefail

# Resolve the directory containing this script regardless of where it's called from
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$BASE_DIR"

if [ ! -f "$BASE_DIR/venv/bin/activate" ]; then
    echo "Virtual environment not found at $BASE_DIR/venv"
    echo "Please run setup.sh first."
    exit 1
fi

source "$BASE_DIR/venv/bin/activate"
exec python "$BASE_DIR/agent.py"
