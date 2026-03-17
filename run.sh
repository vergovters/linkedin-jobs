#!/usr/bin/env bash
# Start the app and open the browser. Keep this window open while using the app.

cd "$(dirname "$0")"

if [[ ! -d ".venv" ]]; then
  echo "Run Setup first (double-click Setup.command or run ./setup.sh)."
  read -p "Press Enter to close..."
  exit 1
fi

# Open browser after a short delay so the server is up
(sleep 3 && open "http://127.0.0.1:5000" 2>/dev/null || true) &

echo "Starting the app. Your browser will open in a few seconds."
echo "Keep this window open while you use the app. Close it to stop."
echo ""

.venv/bin/python app.py
echo ""
read -p "Server stopped. Press Enter to close..."
