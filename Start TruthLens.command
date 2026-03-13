#!/bin/bash
cd "$(dirname "$0")"
echo "Starting TruthLens AI..."
echo "Open http://localhost:8080 in your browser"
echo "Press Ctrl+C to stop"
echo ""
python3 truthlens_api.py
echo ""
read -p "Press Enter to close this window..."
