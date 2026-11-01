# Android quick start (local-only)

AppForge runs as a local Python web app. On Android, the supported deployment is an installable PWA served from the phone itself. The Android debug APK workflow in GitHub is a build-pipeline smoke test; it is **not** a standalone APK containing the Python backend.

## One-time setup

1. Install **Termux from F-Droid or the official Termux GitHub releases**. Do not mix Termux and add-on apps from different signing sources.
2. Download and extract the AppForge-Local source ZIP into Termux-accessible storage, or clone this repository.
3. In Termux, enter the extracted AppForge folder and run:

   ```sh
   bash android-setup.sh
   ```

   The script installs only Python and curl, compiles the Python files, and creates safe local settings. No paid API, cloud runtime, Node.js or Android SDK is required to run AppForge itself.

## Daily start

From the AppForge folder, run:

```sh
./android-start.sh
```

It starts the Python service on `127.0.0.1:8787`, checks the health endpoint, and opens Chrome. In Chrome, choose **⋮ → Add to Home screen** (or **Install app**, if offered). After that, launch AppForge from the home-screen icon.

Keep the Termux process alive in the background. On Android 15, exempt Termux from battery optimization if Android repeatedly kills its background process. Do not expose the service on a LAN or public interface.

## Local AI

If llama.cpp is already running in Termux on port 8080, the default settings point to:

`http://127.0.0.1:8080/v1`

Open **Local AI settings** in AppForge and set the exact model identifier returned by your local server's `/v1/models` endpoint. Leave the API key blank when the local server does not require authentication. AppForge does not send an Authorization header for a blank key.

For 8 GB Android devices, use a small quantized model, keep context modest, and close other memory-heavy apps before inference. AppForge remains usable for manual research/project management when the model server is stopped; AI-only actions will report that the local model is unavailable.

## Stop / troubleshoot

- Stop: `kill "$(cat state/server.pid)"`
- Logs: `tail -n 80 state/server.log`
- Health: open `http://127.0.0.1:8787/api/health`
- If the port is busy, stop the old process before starting again.
- Keep `config.local.json`, `state/`, and `workspace/` private; they contain local settings and project data.

## Known Android limitation

The complete Python backend is not bundled into a native APK. The supported Android workflow is Termux-hosted local service + Chrome-installed PWA. A future standalone Android app needs a maintained embedded Python runtime or a native backend rewrite, background-service lifecycle handling, storage migration, and device-level tests. Do not treat the Capacitor smoke-test APK as that product.
