# Changelog

All notable changes to scaffold-factory are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

_No unreleased changes._

## [0.2.0] — 2026-04-17

Runtime-reliability milestone. `pnpm build` in CI was not enough — this release closes the gap.

### Added
- **Optional provider API key flags** for the Next.js stack: `--clerk-publishable-key`, `--clerk-secret-key`, `--supabase-url`, `--supabase-anon-key`. When set, they're written into the generated `.env.local`; when omitted, the starter's graceful-no-keys path activates and the sign-in page shows a "configure <provider>" notice with the exact env vars to fill in.
- **Post-scaffold "Next steps" block** printed to stderr: stack-specific next commands (`pnpm dev` / `./gradlew composeApp:run`), exact env vars to set, and the `gh repo create` command for the project slug.
- **Runtime verification in CI.** The `nextjs` smoke job now runs `pnpm start` after `pnpm build`, then curls `/`, `/sign-in`, `/sign-up`, `/dashboard` and asserts each response code. This is the test that would have caught v0.1.0's proxy-location bug before release.
- SKILL.md: new mandatory checklist items for the agent — ask about API keys up front, and always verify with `pnpm dev` (not just `pnpm build`) after scaffold.

### Changed
- Next.js starter pin bumped `mahdirzv/base-next-starter@v0.1.0` → `@v0.1.1` (carries the proxy.ts location fix and graceful-no-keys behaviour for both Clerk and Supabase).
- `apply_env_file()` now skips empty values rather than writing `KEY=` lines, so users who don't pass key flags get a clean `.env.local` with only the provider/theme selection.
- README rewritten: benefit-first hero, "why this exists," audience statement, bring-your-own-starter hint.
- Repo description + topics updated on GitHub for discoverability (`scaffolding`, `kotlin-multiplatform`, `kmp`, `nextjs`, `claude-code`, `ai-agents`, `project-template`, `starter-template`, `code-generation`).

### Fixed
- (Downstream of base-next-starter@v0.1.1) scaffolded Next.js projects no longer crash at runtime without API keys. Previously `pnpm dev` threw `clerkMiddleware() was not run` because `proxy.ts` was at the wrong location and Clerk middleware used non-null assertions on missing env vars.

## [0.1.1] — 2026-04-17

### Added
- GitHub Actions smoke workflow (`.github/workflows/smoke.yml`) running on every PR and push to main. Three jobs:
  - **errors** — asserts known-bad inputs (`--package-prefix com.rzv-bad`, project name `"!!!"`) still produce actionable errors
  - **kmp** — scaffolds a KMP project on Ubuntu + JDK 17 + Android SDK, runs `./gradlew :shared:assemble`
  - **nextjs** — scaffolds a Next.js project on Ubuntu + Node 20 + pnpm 10, runs full `pnpm build`
- Smoke status badge on README.
- `GIT_TERMINAL_PROMPT=0` in subprocess env so git fails fast instead of hanging on a credential prompt in non-interactive contexts.

### Changed
- Starter repos `mahdirzv/kmp-starter-project` and `mahdirzv/base-next-starter` flipped to public. Anonymous `git clone` from any machine now works without credentials.

## [0.1.0] — 2026-04-17

First release. Single-skill consolidation + git+-pinned source resolution + subtractive pack pruning.

### Added
- Single skill: `project-scaffold-factory`. (Previous overlapping companion skills merged into `references/design-rationale.md`.)
- Pinned `git+` source resolution. Registry entries take URLs like `git+https://github.com/mahdirzv/kmp-starter-project@v0.1.0`. Starters are shallow-cloned into `~/.cache/scaffold-factory/` on first use and reused thereafter.
- Starter-owned `.scaffold.json` manifests. Each starter declares its own find/replace placeholders and pack map — the skill itself is generic.
- Subtractive pack pruning for KMP. The base starter ships with all packs integrated; the scaffold deletes unselected pack directories and strips their `include(...)` lines from `settings.gradle.kts`.
- Env-driven provider selection for Next.js. Scaffold generates a minimal `.env.local` with `AUTH_PROVIDER` / `THEME_PRESET` set from CLI flags.
- Verify-on-by-default build gate. `./gradlew build` or `pnpm build` runs after scaffold; `--skip-verify` to opt out.
- Drift detection. Per-placeholder match counts; warn when a find string matched nothing, fail when all did.
- Friendly errors for missing executables (pnpm / git / gradle / gh / node) via `run_tool()` wrapper that converts `FileNotFoundError` into an actionable hint.
- Sanitization of `project_root_name` to Gradle-legal characters; validation of `--package-prefix` against a dotted-lowercase regex. Both fail at plan-build time rather than deep in Kotlin/Gradle output.
- Python 3.10+ preflight guard. Older interpreters are rejected at startup with a readable message.
- `SKILL.md` — "Before running, confirm with the user" checklist so agents don't silently default (package prefix, pack selection, destination, verification preference).
- `references/design-rationale.md` — why the router/registry/script/starter split.
- `references/registry-schema.md` — full schema docs for `registry.json` and `.scaffold.json`.

### Canonical starters tagged at v0.1.0

- [mahdirzv/kmp-starter-project@v0.1.0](https://github.com/mahdirzv/kmp-starter-project/releases/tag/v0.1.0)
- [mahdirzv/base-next-starter@v0.1.0](https://github.com/mahdirzv/base-next-starter/releases/tag/v0.1.0)

[Unreleased]: https://github.com/mahdirzv/scaffold-factory/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/mahdirzv/scaffold-factory/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/mahdirzv/scaffold-factory/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdirzv/scaffold-factory/releases/tag/v0.1.0
