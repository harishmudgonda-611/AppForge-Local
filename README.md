# AppForge Local

**Build and manage AI-assisted applications locally, with control over your models, files and workflow.**

AppForge Local is an experimental, local-first application-building workspace. Its goal is to help developers turn an app brief into a mobile-friendly Progressive Web App (PWA), inspect and iterate on projects, and keep model execution under the developer's control.

> **Project status:** Early development / experimental. Features, setup steps and platform support may change. Review the current code and CI results before relying on this project.

## Why AppForge Local?

- **Local-first:** designed to work with a locally hosted model endpoint rather than requiring a paid hosted AI API.
- **PWA-oriented:** targets responsive, installable web applications.
- **Developer-controlled:** keeps project files and iteration workflows under the developer's control.
- **Extensible:** intended to grow through modular analysis, generation, testing and improvement workflows.

Local-first does not mean every feature is guaranteed to work offline. Model inference requires a running local model server, and optional research or download workflows may require an internet connection.

## Repository contents

The repository currently includes packaged project snapshots:

- [AppForge-Local-Advanced.zip](./AppForge-Local-Advanced.zip)
- [AppForge-Local-Replica-Integrated-v3.zip](./AppForge-Local-Replica-Integrated-v3.zip)

The source tree is not yet committed as ordinary browsable files at the repository root. The CI workflow expects the v3 archive to contain `appforge_local/server.py`, the related application modules, static assets and tests. It also checks for a native Android Gradle project before producing an APK. Until those files are present and the workflow passes, do not treat an APK build or release as verified.

## Getting started

1. Open the [v3 integrated archive](./AppForge-Local-Replica-Integrated-v3.zip) and inspect its contents.
2. Extract it locally.
3. Follow the setup instructions included in the extracted project, if present.
4. Configure the model endpoint to point to a local inference server that you control.
5. Start the application using the instructions shipped with that version.
6. Review generated files and test them before using or distributing an app.

Because the archive layout and dependencies may change, use the README or setup script inside the exact archive version you download. Do not assume that older instructions apply to newer snapshots.

## Local model setup

AppForge Local is intended to connect to a local model server exposing a compatible chat-completions API. Configure the endpoint in the application's documented settings or environment configuration. Keep it bound to loopback (for example, `127.0.0.1`) unless you understand and have secured the network exposure.

Never expose an unauthenticated model server or development server to an untrusted network. Do not commit API keys, passwords, private model files or personal data.

## Development and validation

The GitHub Actions workflow in `.github/workflows/appforge-ci.yml` is intended to:

- validate required application files;
- compile Python and check JavaScript syntax;
- run the Python unit test suite;
- start the local server and exercise HTTP smoke tests;
- build and verify a debug APK when a native Android Gradle project and wrapper are committed.

A workflow definition is not proof that these checks currently pass. See the repository's [Actions](../../actions) tab for actual run results.

## Project structure

The intended source layout is:

```text
appforge_local/
  server.py
  advanced.py
  static/
    index.html
    app.js
    styles.css
  tests/
android/                 # optional native Android wrapper/project
.github/
  workflows/
```

This is the target layout expected by the current CI workflow; it is not a claim that all these paths are already committed.

## Contributing

Contributions, bug reports and documentation improvements are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. Be clear about tested environments and include reproducible steps for bugs.

## Security

Please do not report exploitable vulnerabilities in public issues. See [SECURITY.md](SECURITY.md) for responsible disclosure guidance.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Maintainer

Maintained by [harishmudgonda-611](https://github.com/harishmudgonda-611).
