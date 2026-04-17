# scaffold-factory

[![smoke](https://github.com/mahdirzv/scaffold-factory/actions/workflows/smoke.yml/badge.svg)](https://github.com/mahdirzv/scaffold-factory/actions/workflows/smoke.yml)
[![release](https://img.shields.io/github/v/tag/mahdirzv/scaffold-factory?label=release&color=blue)](https://github.com/mahdirzv/scaffold-factory/releases)
[![license](https://img.shields.io/github/license/mahdirzv/scaffold-factory)](LICENSE)

**Create a ready-to-build KMP or Next.js project in under 2 minutes — with your package name, auth provider, and theme wired in, from a pinned starter tag your AI agent can't rewrite.**

Built for developers who live inside agent-native workflows (Claude Code, OpenClaw, Hermes) and who start the same kinds of projects repeatedly. The LLM never generates project structure; it routes a small deterministic script that copies from canonical starter repos and applies find-and-replace.

---

## What it does

```bash
$ scaffold.py create kmp PlateTracker --dest ./PlateTracker --package-prefix com.rzv --room
```

60 seconds later you have a working Kotlin Multiplatform app at `./PlateTracker`:

- Compose Multiplatform UI across Android / iOS / Desktop
- Package namespace rewritten from `com.example.kmp_starter_project` → `com.rzv.platetracker` everywhere (source, manifests, Xcode config, 50+ files)
- Optional packs you asked for are kept (`kmp/room_data/` in this run), ones you didn't are deleted along with their `settings.gradle.kts` `include(...)` line
- `local.properties` pointing at your detected Android SDK
- `./gradlew build` already passed — the scaffold fails if the project doesn't compile

Same flow for Next.js 16:

```bash
$ scaffold.py create nextjs MyApp --dest ./MyApp \
    --auth-provider clerk \
    --clerk-publishable-key pk_test_... \
    --clerk-secret-key sk_test_...
```

Generates a minimal `.env.local` with the provider selection + any keys you passed, then runs `pnpm install && pnpm build && pnpm start` and curls every route (`/`, `/sign-in`, `/sign-up`, `/dashboard`) to prove runtime works, not just build. **If you skip the keys, the app still boots** — the starter's auth providers no-op gracefully and show a "configure <provider>" notice on the sign-in page until you fill `.env.local`.

Same works for Supabase via `--supabase-url` / `--supabase-anon-key`.

## Why this exists

An LLM asked to "scaffold a KMP project" will re-invent the project structure every time. It burns tokens, produces non-deterministic output, and can't build-verify because it doesn't know what "correct" looks like.

scaffold-factory flips that: **the LLM routes, a Python script executes**. The starter repos are the single source of truth, pinned by tag. The agent's job is to pick the right flags and confirm with you before running. The output is reproducible across machines and time.

- **No LLM in the hot path.** Every file operation is deterministic copy + substring replace.
- **Pinned sources.** `v0.1.0` of a starter today is `v0.1.0` next year.
- **Build-gated by default.** A scaffold isn't done until `./gradlew build` or `pnpm build` passes.
- **Self-describing starters.** Each starter declares its own placeholders and packs via `.scaffold.json` — swap in your own starter without touching scaffold-factory.
- **Portable.** One `git clone` installs the skill into any agent's skills directory.

## Who this is for

- **Agent-native developers** (Claude Code, OpenClaw, Hermes) who want deterministic scaffolding instead of asking an LLM to type boilerplate
- **Teams with opinionated internal starters** who want every new app to start from the same base
- **Solo devs who start several projects a week** and are tired of `create-next-app` → 20 minutes of cleanup → wire auth → set up the theme tokens → fix the placeholder app name

If you start one Next.js app a year, `create-next-app` is fine. If you start five, this saves you an afternoon per project.

## Install

```bash
git clone https://github.com/mahdirzv/scaffold-factory ~/.claude/skills/scaffold-factory
```

Any agent that loads skills from `~/.claude/skills/` (or equivalent) picks it up automatically. Trigger by asking:

> *"scaffold a KMP project called PlateTracker, package prefix com.rzv, with Room"*
>
> *"create a Next.js starter named MyApp with Clerk auth"*

The agent will confirm your package prefix, pack selection, and destination path before running (see [`SKILL.md`](SKILL.md) — it's instructed not to silently default).

## Requirements

- **Python 3.10+** (modern type syntax; 3.9 and older are rejected at startup with a clear message)
- **git** on PATH (for lazy-cloning starters)
- **Per stack:**
  - KMP → JDK 17+, Android SDK (auto-detected via `ANDROID_HOME` / `ANDROID_SDK_ROOT` or common paths)
  - Next.js → Node.js 20+ and pnpm (`npm i -g pnpm` or `corepack enable`)

Missing executables are reported with an actionable hint ("install pnpm with `npm i -g pnpm`") instead of a Python traceback.

## Commands

```bash
scaffold.py resolve <stack> <name> [flags]       # print the JSON plan
scaffold.py create  <stack> <name> --dest PATH   # resolve + apply + verify
scaffold.py apply   --plan plan.json --dest PATH # apply a saved plan
```

See [`references/command-grammar.md`](references/command-grammar.md) for the full flag set and [`references/registry-schema.md`](references/registry-schema.md) for how the registry and `.scaffold.json` manifests work.

## Architecture

| Layer | File | Role |
|---|---|---|
| Router | [`SKILL.md`](SKILL.md) | Policy + decision rules (loaded by the agent) |
| Registry | [`references/registry.json`](references/registry.json) | Pinned starter tags + pack ids |
| Script | [`scripts/scaffold.py`](scripts/scaffold.py) | Deterministic file operations |
| Starter (KMP) | [mahdirzv/kmp-starter-project](https://github.com/mahdirzv/kmp-starter-project) | Canonical Compose Multiplatform base + packs |
| Starter (Next.js) | [mahdirzv/base-next-starter](https://github.com/mahdirzv/base-next-starter) | Canonical Next.js 16 base |

Each starter owns its own `.scaffold.json` declaring its placeholders and packs. The skill is generic; the starter is authoritative. **Bring your own starter** by adding a `.scaffold.json` to your repo and pointing `registry.json` at it — see [`references/design-rationale.md`](references/design-rationale.md).

## Releases

See [CHANGELOG.md](CHANGELOG.md) for the version history.

## License

MIT — see [LICENSE](LICENSE).
