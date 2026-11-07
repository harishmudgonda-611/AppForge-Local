# AppForge Local — Development Roadmap

**Status:** Proposed roadmap based on repository inspection  
**Baseline:** `main` at the time this roadmap was prepared  
**Product direction:** Local-first research and original PWA creation, with optional, clearly disclosed Android packaging

This roadmap prioritizes reliability and a usable end-to-end workflow over adding more features. It does not imply that any milestone is already implemented.

## Product goals

1. Let a user go from an app idea to an inspectable, original PWA project through a guided workflow.
2. Keep model inference, project files, research history, and analytics local by default.
3. Make every generated project reproducible, testable, and recoverable.
4. Treat Android packaging and publication as explicit, separate steps.
5. Report evidence and limitations honestly: research snapshots are not market proof, and a scaffold is not a built or released APK.

## Repository baseline

The repository already contains:

- `server.py`: local HTTP API, configuration, generation validation, project checks, Git checkpointing, approved repair, and launch configuration.
- `advanced.py`: research, workflow, project helpers, and test support.
- `static/`: HTML/CSS/JS PWA interface, manifest, service worker, and icon.
- `tests/`: Python tests for server, advanced features, and generation resilience.
- `.github/workflows/appforge-ci.yml`: project CI and source archive workflow.
- `.github/workflows/android-apk.yml`: opt-in hosted debug APK workflow.
- Local SQLite/state and generated workspace paths excluded from Git.

The README documents Python 3.10+, optional local OpenAI-compatible inference, optional Node.js checks, and the Android toolchain required for Capacitor builds.

## Priority roadmap

### P0 — Make the existing workflow dependable

**Objective:** Establish a stable baseline before expanding capabilities.

Tasks:
- Run the documented Python compile and unittest suite, JavaScript syntax check, and CI smoke tests on the current baseline.
- Record a reproducible local setup and a single source of truth for runtime/tool versions.
- Verify the complete idea → research → brief → generated files → static checks → project preview path.
- Verify error states for unavailable local model, malformed model response, timeout, invalid file map, and incomplete generated PWA.
- Ensure project status and generated artifacts remain understandable after restart.
- Confirm that sensitive local configuration, SQLite state, workspace files, model files, and credentials never enter Git.

Acceptance criteria:
- Documented checks pass on a clean checkout, or failures are recorded with exact reproduction steps.
- A sample PWA can be generated without external model/API access only where deterministic fixtures or a clearly documented fallback exist.
- Invalid or incomplete generation is rejected without partial project writes.
- Existing projects are not overwritten silently.
- A user can inspect, export, and recover a generated project.

### P1 — Guided project lifecycle and quality gates

**Objective:** Turn the existing workflow adapter into a clear, stateful project journey.

Tasks:
- Define project lifecycle states: idea, researched, brief-approved, generated, checks-passed, previewed, Android-ready, release-preflight.
- Persist stage status, timestamps, input/source references, output paths, and failure details locally.
- Add explicit approval checkpoints before model edits, dependency installation, npm test, or Android build.
- Provide actionable validation results and distinguish blocked, skipped, failed, and passed checks.
- Add generated-project preview and a checklist for responsive layout, accessibility, offline behavior, and original content.
- Keep the 11-stage workflow, but ensure each stage has defined inputs, outputs, and exit criteria.

Acceptance criteria:
- A project can resume after server restart without losing stage history.
- Each stage records its outcome and artifacts.
- Approval-required actions cannot run without approval.
- The UI never labels skipped or unavailable checks as passed.
- The user can see the exact generated files and validation report before moving forward.

### P2 — Improve generated-app quality and mobile usability

**Objective:** Make generated PWAs more useful on Android phones and small screens.

Tasks:
- Improve generation briefs to specify audience, problem, core flow, screen states, data model, offline needs, and acceptance tests.
- Add template-based validation for semantic HTML, viewport, manifest, service worker, accessible names, focus visibility, and responsive layout.
- Add a local preview flow that works well on narrow screens and supports a user-owned project folder.
- Test service-worker install/update behavior and avoid stale cached builds.
- Provide a concise generated-project README with setup, features, known limitations, and validation commands.
- Add deterministic sample projects and regression fixtures to test generation resilience.

Acceptance criteria:
- Generated projects include the required PWA files and a valid manifest.
- JavaScript syntax and available static checks pass before a project is marked ready.
- Mobile viewport and offline behavior are manually or automatically checked and clearly reported.
- Generated source remains readable and editable; no obfuscation or hidden external dependency.
- Sample project fixtures cover malformed, incomplete, oversized, and unsafe output.

### P3 — Local-first research and decision quality

**Objective:** Help users select ideas using transparent evidence rather than unsupported AI conclusions.

Tasks:
- Preserve source URL, collection timestamp, query, region, and data type for each research result.
- Separate observed data from AI interpretation and user assumptions.
- Add a research comparison view for problem, audience, competitors, differentiation, effort, and monetization hypothesis.
- Label unavailable, stale, or incomplete source data.
- Add a lightweight validation plan: user interviews, landing-page test, prototype test, and measurable success criteria.
- Do not claim App Store snapshots, reviews, or manually entered analytics represent revenue or download counts.

Acceptance criteria:
- Every externally sourced research item has provenance and timestamp.
- The UI explicitly identifies missing or stale evidence.
- Idea recommendations include assumptions and a low-cost validation action.
- No market size, revenue, virality, or ranking claims are invented.

### P4 — Android packaging, kept optional and safe

**Objective:** Make the path from a validated PWA to a debug APK predictable without misrepresenting local-first behavior.

Tasks:
- Add a preflight checklist for Node, JDK, Android SDK/platform/build-tools, Capacitor configuration, package identifiers, and project dependencies.
- Clearly label hosted GitHub Actions builds as external processing and require an explicit user choice.
- Keep local Android build instructions separate from the hosted workflow.
- Validate the APK artifact exists and is non-empty; report debug vs release, signing status, and artifact retention.
- Add device installation and smoke-test instructions for Android.
- Do not automate Play Store publishing, signing-key handling, or billing without a separate security review and explicit product scope.

Acceptance criteria:
- Build preflight identifies missing tools before invoking Gradle.
- Hosted build requires a deliberate workflow dispatch and clearly discloses source transfer.
- A successful build is reported only after the APK artifact is verified.
- Debug APKs are never described as production-signed releases.
- No release credentials are stored in the repository.

### P5 — Security, reliability, and release readiness

**Objective:** Strengthen the local development tool without pretending generated code is sandboxed.

Tasks:
- Review HTTP host/origin checks, request size limits, timeouts, path validation, symlink handling, and subprocess boundaries.
- Add regression tests for unsafe paths, symlinked workspace/config/state, malicious generated filenames, oversized model responses, and secret scanning.
- Review service-worker caching and local API access from the browser.
- Document the threat model, trusted-project assumption, and safe handling of generated dependencies.
- Add a backup/export/restore path for user projects and research data.
- Add release checklist and versioned changelog.

Acceptance criteria:
- Security regression tests cover documented guardrails.
- Untrusted projects are not installed, repaired, or built automatically.
- Local model endpoints remain restricted to localhost/private network as documented.
- Export and restore are tested with a sample project.
- Release notes distinguish implemented, experimental, and unavailable features.

## Suggested execution sequence

| Milestone | Focus | Exit condition |
|---|---|---|
| M0 | Baseline verification | Test/CI results recorded; critical failures triaged |
| M1 | Lifecycle reliability | Guided project flow persists and reports stage results |
| M2 | PWA quality | Generated sample passes required checks and mobile review |
| M3 | Research provenance | Evidence and assumptions are separated; idea validation plan available |
| M4 | Android preflight | Local and hosted build paths clearly distinguished and tested |
| M5 | Release hardening | Security regression suite, export/restore, and release checklist complete |

## Recommended first sprint

1. Run baseline CI and inspect the latest workflow result.
2. Reproduce one successful local project generation and one rejected malformed response.
3. Map the current UI actions to backend endpoints and lifecycle stages.
4. Add lifecycle persistence and clear check-state reporting.
5. Add regression tests for the lifecycle and generation failure paths.
6. Verify a generated project on a mobile viewport.
7. Update README with verified steps and exact known limitations.

## Explicit non-goals for this roadmap

- Automatically copying competitor apps, source code, branding, or protected assets.
- Claiming that public rankings establish downloads, revenue, or demand.
- Automatic trading, ad serving, payment collection, or Play Store publishing.
- Treating GitHub-hosted builds as local-only.
- Running arbitrary generated projects or dependencies without user approval.
- Replacing the existing Python/vanilla-JS/SQLite architecture without evidence that it is the bottleneck.

## Validation and maintenance

At each milestone, record:
- commit SHA and environment/tool versions;
- commands run and exact pass/fail/skip results;
- manual device checks performed;
- artifacts created and their locations;
- known gaps and the next priority.

This roadmap should be revised after baseline tests and a real end-to-end run. Priorities are provisional until measured against the current implementation and user workflow.
