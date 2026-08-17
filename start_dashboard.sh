#!/bin/bash
# Start the React dashboard. Requires Node.js.
# Usage: bash start_dashboard.sh

cd "$(dirname "$0")"/dashboard_app
echo "============================================"
echo "  Crude Analysis Dashboard"
echo "  Open: http://localhost:8080"
echo "  Press Ctrl+C to stop"
echo "============================================"
python3 -m http.server 8080