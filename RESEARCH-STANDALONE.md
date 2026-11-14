# Standalone Research Intelligence

This is an experimental, single-file, browser-native research module for AppForge Local.

## Run
1. Download `research-standalone.html` to an Android device.
2. Open it in Chrome.
3. For GitHub research, enter a public repository URL and select Inspect.
4. If Chrome blocks cross-origin requests from the `file://` origin, download the repository ZIP from GitHub and use ZIP inspection instead.
5. Export Markdown or JSON reports for backups.

## Architecture
- One HTML file; no external JavaScript, CSS, fonts, CDN, backend, cloud database, hosted AI, build step, or Termux.
- GitHub public REST API is contacted directly only after the user starts an inspection.
- ZIP analysis and report generation run in the browser.
- Research history uses IndexedDB when available.
- Repository files are never executed.

## Known limitations
- Chrome may block GitHub API fetches from a local `file://` origin due to opaque-origin/CORS rules. This is a browser security restriction, not fixed by `no-cors` (which would make response contents unreadable). ZIP upload is the offline fallback.
- IndexedDB persistence for local-file origins varies by browser.
- ZIP reader supports stored and Deflate entries when `DecompressionStream('deflate-raw')` is available. Unsupported compression methods are skipped for text extraction.
- GitHub inspection currently retrieves metadata, README, license metadata and tree. Dependency manifests are detected by filename but are not individually fetched from GitHub in this first prototype.
- Static pattern matches are indicators, not a malware scan or security certification.
- License detection is not legal advice.
- No browser-on-device test has been performed as part of this commit.

## Safety
No scripts, package managers, build commands, binaries, or repository workflows are run. No GitHub token or other secret is requested.
