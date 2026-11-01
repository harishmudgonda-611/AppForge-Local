#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

if [ -z "${TERMUX_VERSION:-}" ] && [ ! -d "/data/data/com.termux/files/usr" ]; then
  echo "This setup is intended for Termux on Android."
  exit 1
fi

echo "Installing the minimal AppForge runtime (Python + curl)..."
pkg update -y
pkg install -y python curl

cd "$(dirname "$0")"
python -m compileall -q server.py advanced.py
python - <<'PY'
import json
from pathlib import Path
p=Path("config.local.json")
if not p.exists():
    p.write_text(json.dumps({
        "llm_base_url":"http://127.0.0.1:8080/v1",
        "llm_model":"qwen2.5-coder",
        "llm_api_key":"",
        "timeout_seconds":120
    }, indent=2))
print("Local settings ready.")
PY

chmod +x android-start.sh
echo
echo "Setup complete. Start AppForge with: ./android-start.sh"
