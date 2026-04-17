---
name: scaffold-factory
description: Scaffold new KMP or Next.js projects from canonical GitHub starter repos plus optional packs (auth, UI/theming, Room, CI, GitHub). Use when the user asks to create a new KMP or Next.js project, bootstrap an app from a starter, or generate a ready-to-build project. Never invents architecture — shallow-clones pinned starter tags and applies deterministic find/replace substitution declared by the starter's own .scaffold.json manifest.
---

# Project Scaffold Factory

Use this skill to create a new KMP or Next.js project from a pinned, versioned starter repo. The goal is **assembly, not invention**: the model routes the request; a Python script does all file work.

## Core flow

```
User: "create kmp MyApp --auth --ui --room"
  ↓
scaffold.py resolve  → build a plan (pinned sources, selected packs, placeholders)
scaffold.py apply    → shallow-clone starter to ~/.cache/, copy to $DEST,
                       subtractive-prune unselected packs, find/replace,
                       generate .env.local (Next.js) or local.properties (KMP),
                       run build verification
  ↓
Ready-to-build project at $DEST
```

## Command

```bash
python3 scripts/scaffold.py create <stack> <name> --dest <path> [flags]
```

- **stack** — `kmp` or `nextjs`
- **name** — project name (gets slugified, humanized, and compacted into package identifiers)
- **--package-prefix** — dotted prefix for Kotlin/Android package, e.g. `com.rzv` (default `com.example`)
- **--auth-provider** — override default (Next.js: `clerk` | `supabase`)
- **--theme-preset** — override default (`neutral` | `vivid`)
- **--room** — include Room data pack (KMP only)
- **--ci** — keep `.github/workflows/` from the starter
- **--no-auth**, **--no-theme** — skip default packs
- **--skip-verify** — skip the build gate (default: build is mandatory)
- **--force** — allow non-empty destination
- **--refresh-cache** — re-clone the starter even if cached

> **Creating a GitHub repo is a separate step.** After scaffold completes, run:
> `cd <dest> && gh repo create <slug> --source . --push --private`.
> The scaffold does not touch remote state for you.

See `references/command-grammar.md` for the full flag set.

## Before running — confirm with the user

Scaffolding is destructive on the target path and generates identifiers that are hard to rename later. Before invoking `scaffold.py create`, make sure the user has chosen — and confirmed — every one of these. **Do not silently default.**

1. **Project name** — used for the directory, Gradle `rootProject.name`, the package suffix, and the generated `.env.local` / `local.properties`. Ask if ambiguous.
2. **Package prefix** (`--package-prefix`) — DO NOT accept the default `com.example` silently. Ask:
   > *"What package prefix would you like? e.g. `com.rzv`, `dev.mahdi`, `io.yourcompany`. This will become `<prefix>.<project>` in all Kotlin/Android sources."*
3. **Which packs** — auth and UI/theme are included by default. Confirm:
   - KMP: `--room` (data/storage layer)? `--ci` (GitHub Actions workflow)?
   - Next.js: `--auth-provider clerk|supabase`? `--theme-preset neutral|vivid`?
4. **Destination path** (`--dest`) — absolute path or sensible relative path. Confirm it doesn't collide with existing work.
5. **Verification** — the script runs `./gradlew build` or `pnpm build` by default (takes a couple of minutes). Warn the user. Only pass `--skip-verify` if the user explicitly opts out.
6. **Auth provider API keys** — if `--auth-provider clerk` or `supabase`, ask:
   > *"Do you have your Clerk (or Supabase) keys ready? If yes, paste them and I'll wire them into `.env.local`. If not, I'll scaffold without keys and the app will show a 'configure <provider>' notice on the sign-in page until you add them."*
   - Clerk keys → pass via `--clerk-publishable-key` and `--clerk-secret-key`.
   - Supabase keys → pass via `--supabase-url` and `--supabase-anon-key`.
   - Unset flags are silently omitted from `.env.local`; the starter's graceful-no-keys path activates.
7. **Always verify with `pnpm dev` (Next.js) or `./gradlew :composeApp:run` (KMP) after the scaffold completes.** `pnpm build` alone does not exercise middleware/runtime; the full dev server + curl on `/`, `/sign-in`, `/dashboard` is what catches proxy and auth bugs.
8. **KMP pack status caveat** — `kmp:auth`, `kmp:room_data`, `kmp:ui_theme` are shipped as **reference modules, not wired dependencies** in the current starter. `composeApp`/`shared` don't import from them. When the user selects any of these packs, the scaffold's "Next steps" block prints a wiring-instructions warning — **relay this warning to the user verbatim**. Don't imply the packs are plug-and-play. (Full cross-target wiring is planned for v0.5.0.) Next.js does NOT have this caveat — its provider switching is fully env-driven as of base-next-starter v0.1.2.

If any answer is ambiguous, **ask** — do not guess.

The script prints a "Next steps" block to stderr after a successful scaffold — relay it to the user verbatim; it includes the exact `gh repo create` command for their project slug.

## Architecture

- **Skill = router & policy** (this file + `references/`)
- **Registry = source of truth for pinned starters** (`references/registry.json`)
- **Script = deterministic execution** (`scripts/scaffold.py`)
- **Starter repos = canonical templates** (remote, pinned via `git+<url>@<tag>`)
- **Starter's `.scaffold.json` = self-describes its placeholders and packs**

## Rules

- One stack per command.
- One base starter per scaffold.
- Optional packs must be explicit flags (or defaults declared in the registry).
- Build verification is mandatory unless `--skip-verify` is passed.
- Never hand-write project structure if the starter already has it.
- Never rewrite project files with the LLM — the script does find/replace.
- Sources are pinned: registry entries use `git+<url>@<tag>`, not floating branches.

## Starter repos

Two canonical remotes, each declares its own `.scaffold.json`:

| Stack | Repo | Pack selection model |
|---|---|---|
| KMP | `github.com/mahdirzv/kmp-starter-project` | Subtractive: base includes `kmp/{auth,room_data,ui_theme}`; unselected packs are deleted and their `include(...)` line stripped from `settings.gradle.kts`. |
| Next.js | `github.com/mahdirzv/base-next-starter` | Env-driven: providers live in `src/modules/auth/providers/`; `.env.local` is generated from `.env.example` with `AUTH_PROVIDER` and `THEME_PRESET` set from flags. |

## Registry shape

```json
{
  "version": "0.1.0",
  "min_scaffold_py_version": "0.1.0",
  "stack_defaults": {
    "kmp":    { "auth_provider": "clerk", "theme_preset": "neutral" },
    "nextjs": { "auth_provider": "clerk", "theme_preset": "neutral" }
  },
  "packs": [
    {
      "id": "kmp_base",
      "stack": "kmp",
      "kind": "base",
      "source": "git+https://github.com/mahdirzv/kmp-starter-project@v0.1.0",
      "verify": ["./gradlew --no-daemon build"]
    },
    { "id": "kmp_auth", "stack": "kmp", "kind": "feature" },
    ...
  ]
}
```

Feature packs do not need `source` — they reference paths inside the base that are pruned or kept based on selection. The subtractive mapping lives in the starter's `.scaffold.json`.

## Starter manifest (`.scaffold.json`)

Each starter repo declares how it should be scaffolded:

```json
{
  "scaffold_schema_version": "1",
  "stack": "kmp",
  "placeholders": [
    { "find": "com.example.kmp_starter_project", "replace_with": "{{package_name}}" },
    { "find": "com/example/kmp_starter_project", "replace_with": "{{package_path}}" },
    { "find": "Kmpstarterproject",               "replace_with": "{{project_root_name}}" }
  ],
  "packs": {
    "auth":     { "paths": ["kmp/auth"],      "settings_gradle_include_line": "include(\":kmp:auth\")" },
    "room":     { "paths": ["kmp/room_data"], "settings_gradle_include_line": "include(\":kmp:room_data\")" },
    "ui_theme": { "paths": ["kmp/ui_theme"],  "settings_gradle_include_line": "include(\":kmp:ui_theme\")" },
    "ci":       { "paths": [".github"] }
  }
}
```

Next.js uses `env_file` instead of (or in addition to) path-based packs:

```json
{
  "env_file": {
    "template": ".env.example",
    "output":   ".env.local",
    "set": { "AUTH_PROVIDER": "{{auth_provider}}", "THEME_PRESET": "{{theme_preset}}" }
  }
}
```

## Failure handling

- Unknown pack id → fail before copy
- Destination exists and is non-empty → fail (unless `--force`)
- Build verification fails → fail loudly; project stays on disk for inspection
- Missing Android SDK → write a commented-out `local.properties` and warn (do not fail)

## References

- `references/registry.json` — the live registry (editable; the authoritative source for pinned tags)
- `references/command-grammar.md` — all flags
- `references/registry-schema.md` — registry and `.scaffold.json` field docs
- `references/design-rationale.md` — why this split (skill/registry/script/starter)
