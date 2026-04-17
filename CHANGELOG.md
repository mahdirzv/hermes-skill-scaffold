# Changelog

All notable changes to scaffold-factory are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.4.8] — 2026-04-18

Forward-compat and cleanup-on-failure. scaffold.py hardening, no pin change. 106 → 115 pytest tests.

### Added
- **`.scaffold.json` schema version gate.** `read_starter_manifest` now reads `scaffold_schema_version` and fails with `EXIT_STARTER` if the value isn't in the supported set. Missing field defaults to `"1"` (backwards-compat with starters predating this check). Prevents silent misbehavior when a future v2 schema ships with different field semantics.
- **Verify-fail cleanup.** When `run_verify` (or any other step inside `apply_plan`) fails via `SystemExit`, we now `rmtree(dest, ignore_errors=True)` — but only if *we* created the dest this invocation. A pre-existing dest the user pointed `--dest` at (even with `--force`) is never removed. Before this fix, `pnpm build` failure left a half-scaffolded project on disk and subsequent runs hit "destination already exists and is not empty."
- `tests/test_schema_version_gate.py` (6 tests) + `tests/test_verify_fail_cleanup.py` (3 tests): covers missing field defaults to v1, explicit v1 accepted, v2 rejected, numeric coerced-and-rejected, absent manifest returns {}, supported-set is a frozenset; cleanup on verify failure, preservation of pre-existing dest with --force, successful scaffold leaves dest intact.

### Changed
- `SCAFFOLD_VERSION`, `registry.json`, `plugin.json`, `marketplace.json` all bumped to 0.4.8.

## [0.4.7] — 2026-04-18

Pin bump to consume the hardening wave shipped alongside scaffold-factory v0.4.6. No scaffold.py logic changes; 106 pytest tests still pass.

### Changed
- **Registry pin** `base-next-starter@v0.1.9` → `@v0.1.10`. v0.1.10 ships:
  - **Critical fix**: firebase/custom stub providers now redirect protected routes to `/sign-in` at the proxy layer and return `null`/redirect from the server stubs, matching the clerk/supabase graceful-no-config pattern. Previously these stubs crashed `/dashboard` with a 500 via unhandled `NOT_CONFIGURED` throws.
  - Stale `src/modules/` path references swept from user-visible UI (firebase/custom components) and console warnings.
  - Dead code removed (`SignInInput`, `SignUpInput`, `AuthResult` never imported; duplicate `export const config` in clerk proxy).
  - Clerk `toUser` input type now derived from `currentUser()` return type.
- **Registry pin** `kmp-starter-project@v0.1.2` → `@v0.1.3`. v0.1.3 adds a `com.example.kmpstarterproject` → `{{bundle_id}}` placeholder so iOS `PRODUCT_BUNDLE_IDENTIFIER` in `Config.xcconfig` actually gets renamed. Previously every scaffolded iOS app shipped with the demo bundle ID — missed by all three existing placeholders because the string is lowercase + no underscore.

## [0.4.6] — 2026-04-17

Security hardening pass. No breaking API changes. 96 → 106 pytest tests.

### Security
- **Redact secret placeholder values from stdout JSON** in `resolve` and `create`. Before this release, `scaffold.py resolve ... --clerk-secret-key sk_live_X` serialized the full secret into the plan JSON printed to stdout — where it could leak into CI logs, shell history via `>`, or `tee`. Now those four keys (`clerk_publishable_key`, `clerk_secret_key`, `supabase_url`, `supabase_anon_key`) are replaced with `"[REDACTED]"` at the serialize-to-stdout boundary. In-memory plan passed to `apply_plan` keeps real values (so `.env.local` still gets written correctly); `--plan-out` also keeps real values (explicit user opt-in to persist).
- **Path-traversal guard in `apply_starter_placeholders` rename pass.** A malicious or buggy `.scaffold.json` with `{"find": "src/", "replace_with": "../../etc/"}` — or a `replace_with` that expands via `{{…}}` to a value containing `..` — could previously silently move files outside `--dest`. Now: rejects any rename whose resulting path contains `..` segments OR whose resolved path is not a descendant of `dest.resolve()`. Exits `EXIT_STARTER` with a clear message.
- **Skip symlinks in both rglob passes of `apply_starter_placeholders`.** A starter repo could track a symlink (`link → ~/.ssh/config`); the previous rewrite pass would `write_text` *through* the symlink, overwriting files outside the scaffold. Now every pass checks `path.is_symlink()` first.
- **`shutil.copytree(..., symlinks=False)`.** Explicit: we copy what symlinks reference rather than preserving the symlinks themselves. Combined with the rglob guards, keeps every write confined to `--dest`.

### Added
- `tests/test_security.py` — 10 regression tests covering all three fixes (secret redaction matrix, path-traversal via `..`, path-traversal via placeholder-expansion, symlink content-rewrite skip, symlink rename skip, benign-rename still works).

### Changed
- `SCAFFOLD_VERSION`, `registry.json`, `plugin.json`, `marketplace.json` all bumped to 0.4.6.

## [0.4.5] — 2026-04-17

Registry pin bump to consume the Next.js starter's Clerk catch-all route fix. scaffold.py logic unchanged.

### Changed
- **Registry pin** `base-next-starter@v0.1.8` → `@v0.1.9`. v0.1.9 converts the sign-in/sign-up pages to Next.js catch-all routes (`sign-in/[[...rest]]/page.tsx`, `sign-up/[[...rest]]/page.tsx`). Real-world bug found running the starter against live Clerk dev keys: Clerk's hosted `<SignIn/>` / `<SignUp/>` components probe sub-routes (e.g. `/sign-up/SignUp_clerk_catchall_check_<timestamp>`) for their internal state machine — without catch-all pages, those probes 404 and Clerk throws *"The <SignUp/> component is not configured correctly... is not a catch-all route."* Starter now documents this as Known Gotcha #10 in AGENTS.md.
- `SCAFFOLD_VERSION`, `registry.json` version, `plugin.json`, `marketplace.json` all bumped to 0.4.5.

## [0.4.4] — 2026-04-17

Registry pin bump to consume the Next.js starter's industry-standard structural refactor. scaffold.py logic unchanged.

### Changed
- **Registry pin** `base-next-starter@v0.1.7` → `@v0.1.8`. v0.1.8 removes `src/modules/` — the non-idiomatic layout the senior audit flagged as the biggest "feels unfamiliar" issue. New layout matches conventions of t3-turbo / next-forge / feature-sliced design:
  - `src/modules/auth` → **`src/features/auth`**
  - `src/modules/ui/components` → **`src/components/ui`** (shadcn-native location; `pnpm dlx shadcn@latest add` now drops into the right place)
  - `src/modules/ui/{tokens,themes}` → **`src/lib/design/{tokens,themes}`**
  - `components.json` aliases fixed (were pointing at nonexistent paths)
  - `pnpm-workspace.yaml` removed (single-package repo, not a monorepo — workspace file was implied intent that wasn't delivered)
- Starter runtime + public APIs unchanged; zero behaviour change for existing scaffolds.
- `SCAFFOLD_VERSION`, `registry.json` version, `plugin.json`, `marketplace.json` all bumped to 0.4.4.

## [0.4.3] — 2026-04-17

Registry pin bump to consume the Next.js starter's senior-audit fixes. scaffold.py logic unchanged.

### Changed
- **Registry pin** `base-next-starter@v0.1.3` → `@v0.1.7`. Ships the "round out the core" audit wave. v0.1.4 introduced a regression that took three iterations + a proper git bisect to pin down; the actual root cause is **`app/loading.tsx` at the route root**, not `error.tsx` (v0.1.5 guess) and not the proxy entry structure (v0.1.6 guess):
  - Root `src/proxy.ts` now dispatches through a narrow `@/modules/auth/proxy` entry; `authProxy` reads the active provider's proxy from a `Record<AuthProviderName, AuthProxy>` map. Provider dispatch remains env-driven; firebase/custom get real no-op proxy stubs.
  - Vestigial `middleware(req)` method removed from `AuthServerOps` (was a no-op in every real provider).
  - `AuthProviderName` single-sourced from `@/config`; all `process.env.AUTH_PROVIDER ?? 'clerk'` sites replaced with typed `config.auth.provider`.
  - Route boundaries: `app/global-error.tsx` (root-layout failures) + `app/not-found.tsx`. **`loading.tsx` lives inside `app/(auth)/` intentionally** — a root-level `loading.tsx` wraps every route in a Suspense boundary, and Server Components that throw `NEXT_REDIRECT` inside Suspense respond with `200 + streaming RSC body containing the redirect payload` instead of a clean `307`. Non-JS clients (curl, SEO crawlers, health probes) never redirect. Keep `loading.tsx` inside route groups that need a skeleton.
  - `globals.css` `@theme inline { var: var }` circular no-op deleted.
  - Zod env validation in `@/config` — typos in `AUTH_PROVIDER`/`THEME_PRESET` fail loudly at boot.
  - Starter tests: 44 → 46 passing.
- `SCAFFOLD_VERSION`, `registry.json` version, `plugin.json`, `marketplace.json` all bumped to 0.4.3.

## [0.4.2] — 2026-04-17

Starter-owned post-scaffold notes. The "reference modules need manual wiring" message now lives in each starter's `.scaffold.json` instead of being hardcoded per-pack in scaffold.py. Adding a new KMP pack no longer requires a scaffold-factory release.

### Added
- New helper `collect_post_scaffold_notes(manifest, selected_pack_keys)` reads `post_scaffold_notes.heading` / `.footer` and per-pack `packs.<key>.post_scaffold_note` from the starter manifest, preserving manifest declaration order. Returns an empty dict when no selected pack has a note, so callers cheaply skip the section.
- `apply_plan` result now carries `post_scaffold_notes: {heading, footer, per_pack}` so `print_next_steps` can render without re-reading the manifest (already deleted from dest by that point).
- 10 new pytest cases: empty-manifest, no-selected-packs, selected-without-note, order preservation, missing-heading-defaults, print_next_steps integration (heading/footer/per-pack ordering), backwards-compat when the key is absent.

### Changed
- **Registry pin** `kmp-starter-project@v0.1.1` → `@v0.1.2`. v0.1.2 declares the new `post_scaffold_notes` + per-pack notes.
- **scaffold.py `print_next_steps()` is stack-agnostic.** Hardcoded `if pack == "auth" / "room" / "ui_theme":` block deleted. Output is identical for existing KMP scaffolds (same heading, same per-pack lines, same footer) — they just come from the starter now.
- `SCAFFOLD_VERSION`, `registry.json` version, `plugin.json`, `marketplace.json` all bumped to 0.4.2.

## [0.4.1] — 2026-04-17

Hardening wave. Structured exit codes, dry-run preview, env-var fallback for secrets, 86-test pytest suite + CI job, registry pin bump to a bug-free Next.js starter. No breaking changes.

### Added
- **Structured exit codes** (`EXIT_USAGE=2`, `EXIT_SYSTEM=3`, `EXIT_NETWORK=4`, `EXIT_STARTER=5`) with helpers `fail_usage`, `fail_system`, `fail_network`, `fail_starter`. Every `fail()` call site classified. Lets CI/wrappers tell "bad user input" (retryable) from "git clone died" (retryable differently) from "disk full" (hard stop). Generic `1` retained for uncategorised failures.
- **`--dry-run` flag** on `create` and `apply`. Computes the full plan, copies + rewrites in a throwaway tempdir, and prints all the same stats without ever touching `--dest`. Verification is force-skipped. Ideal for previewing a scaffold before committing to a target directory.
- **Env-var fallback for provider secrets**. `--clerk-secret-key` / `--clerk-publishable-key` / `--supabase-url` / `--supabase-anon-key` now fall back to the matching `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` / `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` env var when the flag is omitted. CLI flag always wins. Keeps secrets out of shell history.
- **`tests/` pytest suite (86 tests)** covering the load-bearing helpers in `scripts/scaffold.py`: `parse_git_source` + `cache_key`, `placeholder_expand`, `apply_starter_placeholders` (contents rewrite, path relocation, drift detection, collision handling), `validate_package_prefix`, `prune_unselected_packs`, `build_identifiers` + `slugify`/`humanize`, plus the new exit-code taxonomy, `--dry-run` end-to-end, and env-var fallback matrix. Pure-Python, no toolchains, ~80ms runtime.
- **New `pytest` job** in `.github/workflows/smoke.yml`. Runs on every PR. Closes the highest-leverage test coverage gap from the v0.4.0 audit backlog.

### Changed
- **Registry pin** `base-next-starter@v0.1.2` → `@v0.1.3`. v0.1.3 fixes 3 shipped-failing auth provider tests via call-time env guards (first audit finding); runtime behaviour unchanged.
- **Registry verify commands use list form**. `kmp_base.verify` was `["./gradlew --no-daemon build"]` (string, runs with `shell=True`); now `[["./gradlew", "--no-daemon", "build"]]` (list, `shell=False`). Eliminates the one call site still hitting `shell=True`. `run_tool` docstring documents the trust boundary.
- `SCAFFOLD_VERSION` bumped `0.4.0` → `0.4.1`; `references/registry.json` version field bumped to `0.4.1`.
- README install section rewritten: adds a verify step, separates "Updating" as its own sub-section, and documents two sharp edges of the CLI — (a) `claude plugin update <name>` fails with "not found" unless you qualify it as `<name>@<marketplace>`, and (b) a stale marketplace cache can make updates appear to be no-ops until `claude plugin marketplace update <marketplace>` is run first.

## [0.4.0] — 2026-04-17

Honesty + a real Next.js fix. Closes two dogfooding gaps: Next.js provider dispatch and KMP pack wiring transparency.

### Changed
- **Next.js starter pin** `base-next-starter@v0.1.1` → `@v0.1.2`. Switching provider is now fully env-driven: `AUTH_PROVIDER=supabase` in `.env.local` swaps both the sign-in/sign-up components AND the root proxy at runtime. No manual code edits needed. Previously, users had to hand-edit `src/modules/auth/index.ts` and `src/proxy.ts` despite comments saying it was env-controlled.
- **KMP starter pin** `kmp-starter-project@v0.1.0` → `@v0.1.1`. Documentation-only update labelling each optional pack a "reference module" with a wiring checklist in the starter's AGENTS.md.

### Added
- `print_next_steps()` now prints a per-pack wiring warning when KMP optional packs (`auth`, `room`, `ui_theme`) are kept — explicitly calls out that these packs are NOT auto-wired into composeApp/shared and lists the exact steps to wire each one.
- SKILL.md + `commands/scaffold.md`: new checklist item instructs the agent to relay the KMP pack warning verbatim to the user.

### Scripts
- `scaffold.py` version bumped `0.2.0 → 0.4.0` to match plugin manifest.

### Deferred to v0.5.0
- Full KMP pack cross-target wiring (add android + iOS source sets to each pack, `implementation(projects.kmp.*)` in composeApp, Koin registration in `sharedModules`). Currently the packs target `jvm()` only and cannot be consumed from `composeApp/commonMain`.

## [0.3.0] — 2026-04-17

Distribution milestone. scaffold-factory is now a first-class Claude Code plugin installable via `claude plugin install` with native version updates.

### Added
- **`.claude-plugin/plugin.json`** — plugin manifest declaring the skill (via `"skills": ["./"]` pointing at repo root) and the new `/scaffold` slash command. No file restructure needed; the existing flat layout works as-is.
- **`.claude-plugin/marketplace.json`** — self-hosted single-plugin marketplace so users can `claude plugin marketplace add mahdirzv/scaffold-factory` and then `claude plugin install scaffold-factory`.
- **`commands/scaffold.md`** — explicit `/scaffold <stack> <name> [flags]` slash-command wrapper. Mirrors the skill's pre-flight checklist and flag set; for users who know exactly what they want without natural-language dispatch.

### Changed
- **`SKILL.md` frontmatter `name`:** `project-scaffold-factory` → `scaffold-factory`. Idiomatic `plugin:skill` = `scaffold-factory:scaffold-factory`, matching the Claude Code convention (`code-review:code-review`, `feature-dev:feature-dev`).
- **`README.md` install section:** plugin install is now the recommended path; `git clone` is documented as a fallback. Added a note warning against having both active at once.

### Backward compat
- Existing `git clone … ~/.claude/skills/scaffold-factory` users are unaffected. The plugin system installs to a separate cache (`~/.claude/plugins/cache/`) and does not interfere with skills directories.
- `scripts/scaffold.py`, `references/registry.json`, and CI are all unchanged — same runtime behaviour, only the distribution + invocation layer changed.

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

[Unreleased]: https://github.com/mahdirzv/scaffold-factory/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/mahdirzv/scaffold-factory/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/mahdirzv/scaffold-factory/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/mahdirzv/scaffold-factory/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/mahdirzv/scaffold-factory/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mahdirzv/scaffold-factory/releases/tag/v0.1.0
