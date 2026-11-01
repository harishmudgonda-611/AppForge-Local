#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p state
if curl --silent --fail --max-time 2 http://127.0.0.1:8787/api/health >/dev/null 2>&1; then
  echo "AppForge is already running at http://127.0.0.1:8787"
else
  nohup python server.py > state/server.log 2>&1 < /dev/null &
  echo $! > state/server.pid
  ready=0
  for _ in $(seq 1 30); do
    if curl --silent --fail --max-time 2 http://127.0.0.1:8787/api/health >/dev/null 2>&1; then
      ready=1
      break
    fi
    sleep 1
  done
  if [ "$ready" -ne 1 ]; then
    echo "AppForge did not start. Recent server log:"
    tail -n 40 state/server.log || true
    exit 1
  fi
fi

echo "Opening AppForge in Chrome..."
am start -a android.intent.action.VIEW -d http://127.0.0.1:8787/ >/dev/null 2>&1 || true
echo "AppForge is running locally. Use Chrome menu > Add to Home screen to install the PWA."
echo "To stop it: kill $(cat state/server.pid)  (run this from the AppForge folder)"
