# AppForge Local

**A local-first workspace for researching app opportunities and building original PWAs with AI under your control.**

> **Status: experimental / early development.** This is a working prototype, not a production app factory. Review generated code, test on real devices, and verify all third-party data and policies before release.

## What it includes

- Local web interface and Python API, bound to `127.0.0.1` by default.
- Optional AI analysis and original source generation through a local OpenAI-compatible model endpoint.
- Public Apple App Store search and top-free chart snapshots, with source URLs and collection timestamps. These are not download or revenue metrics.
- Local SQLite research history, review-feed collection where available, and manually recorded local analytics.
- Static project checks (no package scripts execute by default), owner-approved repair workflows, and Git checkpoints.
- An 11-stage Replica-inspired workflow adapter for research, architecture, design, build, test planning and release preflight.
- A Capacitor Android scaffold. It does **not** mean an APK has been built or is ready for Play Store release.

Google Play links are provided for manual research; this project does not claim to scrape or verify Google Play rankings. It aims to build original implementations and does not decompile or copy competitor source code, branding or protected assets.

## Requirements

- Python 3.10 or newer. The server uses the Python standard library; no third-party Python packages are required.
- Optional local model server exposing an OpenAI-compatible `/v1/chat/completions` API (for example llama.cpp or Ollama).
- Optional Node.js 22+ / npm for JavaScript project checks and generated-app workflows.
- For the generated Capacitor 8 Android scaffold: Node.js 22+, Android Studio 2025.2.1+ (or compatible Android SDK command-line tools), JDK 17+, Android SDK Platform 36 and Build Tools 36.0.0. Capacitor 8.6.0's Android template targets API 36.

## Run locally

1. Download or clone this repository.
2. Start the server from the repository folder:

   ```bash
   python server.py
   ```

3. Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

On Windows, `start.bat` is available. On Android, run the server in a Python environment such as Termux and open the same localhost URL in Chrome.

The first run creates `config.local.json` from safe local defaults. Configure the URL and model name in **Settings** to match your local model server. The API key is optional: leave it blank for local servers that do not require authentication; AppForge omits the Authorization header when no key is set. The local config file is ignored by Git so personal settings are not committed. `config.example.json` documents the defaults.

## Tests

Run from the repository root:

```bash
python -m compileall -q server.py advanced.py tests
python -m unittest discover -s tests -v
node --check static/app.js
```

GitHub Actions runs the same Python and JavaScript checks, archive integrity validation, and HTTP smoke tests. Each successful CI run also publishes a current `AppForge-Local-source.zip` artifact (Actions → latest successful AppForge Local CI run → Artifacts). The legacy ZIP files in the repository are retained for reference; use the CI artifact for the latest validated source bundle.

## Android APK build (opt-in GitHub Actions)

The local Capacitor scaffold does not itself install Android SDK tools or produce an APK. For an optional hosted build, commit a generated PWA project under `apps/<app-slug>/` with its `package.json`, committed `package-lock.json`, `capacitor.config.json`, and `index.html`. Run `npm install` once on a trusted development machine to create/update the lockfile, review it, and commit it with the app. The hosted build uses `npm ci` and fails if the lockfile is missing, so dependency resolution is reproducible. Then open **Actions → Build Android APK → Run workflow**, enter the app slug, and start the workflow. A successful run uploads a debug APK artifact for seven days.

This workflow sends the committed app source to a GitHub-hosted runner. Use it only when you explicitly choose a hosted build; it is not local-only. It creates or syncs the Capacitor Android project, runs the app's available tests, builds a debug APK, checks APK archive integrity, verifies the embedded Android package ID matches `capacitor.config.json`, records a SHA-256 checksum, and uploads both the APK and checksum. It does not sign a production release, publish to Google Play, or store signing credentials. Do not commit secrets or private user data into the app folder.

For a fully local build, install Node.js, JDK 17, Android SDK command-line tools and the required Android SDK platform/build-tools on your own build machine, then run the equivalent npm/Capacitor/Gradle commands there. The hosted workflow is optional and is not required to use the local PWA.

## Security and privacy

- The server has no login system. Keep it bound to localhost; do not expose it to the public internet.
- State-changing API requests reject non-loopback Host headers, mismatched browser Origin headers, and cross-site Fetch Metadata. Origin-less local CLI requests remain supported. This is defence in depth, not authentication.
- Do not enable LAN binding: the current application has no authenticated LAN mode or session protection.
- AI endpoints are restricted to localhost/private-LAN HTTP addresses. Do not put real secrets in prompts or generated project files.
- Local project data, SQLite state and local model configuration are excluded from Git.
- AI repair, coding-agent edits, optional npm test execution and local APK builds require explicit approval. Static checks never execute package scripts. APK builds execute project-controlled npm/Capacitor/Gradle tooling; inspect project files and dependencies first. Do not build untrusted projects.
- Git checkpoints override repository hook configuration with an empty hooks directory, so project-controlled Git hooks do not run. Symlinked or non-directory `.git` metadata is rejected. Before staging, checkpoints scan filenames and text content for common secret indicators (environment files, private keys, cloud/API tokens and credential-like assignments) and block suspicious projects. This scanner is a safety net, not a guarantee; never place secrets in generated project folders.
- Approved local APK builds use a reduced environment, non-interactive subprocesses, fixed commands, bounded timeouts, and symlink checks for Android build paths. This reduces accidental environment influence but is **not a sandbox**: npm scripts, Capacitor plugins and Gradle build logic still run with the AppForge user's permissions. Only build code and dependencies you trust; use a separate OS account or disposable build environment for untrusted projects.

## Important limitations

- Apple public feeds/search can be unavailable, rate-limited or incomplete. Historical trends exist only after repeated snapshots.
- Research output is not proof of downloads, revenue, market share or virality.
- A PWA is not automatically an APK. Android packaging requires a valid Capacitor project and a configured Android build toolchain.
- No live ad serving, payment processing, Play Console submission, release signing, guaranteed publication or revenue generation is implemented.

## Project layout

```text
server.py                 Local HTTP server and API
advanced.py               Research, test, workflow and project helpers
static/                   PWA interface, styles, manifest and service worker
tests/                    Automated Python tests
config.example.json       Safe local model configuration defaults
config.local.json         Created locally; ignored by Git
workspace/                Generated projects; local and ignored
state/                    SQLite and local feedback; ignored
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please include reproducible steps and test results with bug reports and pull requests.

## Security reports

See [SECURITY.md](SECURITY.md). Do not publish credentials or exploit details in public issues.
