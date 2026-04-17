---
name: scaffold
description: "Scaffold a new KMP or Next.js project from the canonical starter. Usage: /scaffold <stack> <name> [flags]. Example: /scaffold nextjs MyApp --auth-provider clerk. Invokes scripts/scaffold.py deterministically — never rewrites project structure with an LLM."
---

# /scaffold

Deterministic project scaffolder. Wraps `scripts/scaffold.py` from the scaffold-factory plugin.

Under the hood this is the same skill as `scaffold-factory:scaffold-factory`, triggered by slash command instead of natural language.

## Usage

```
/scaffold <stack> <name> [flags]
```

- **stack** — `kmp` or `nextjs`
- **name** — project name (slugified, humanized, and compacted into package identifiers)

## Before running — confirm with the user

Same checklist as the skill. **Do not silently default:**

1. **Project name** — directory, Gradle `rootProject.name`, package suffix, env files.
2. **Package prefix** (`--package-prefix`) — ask if unspecified; do not use `com.example` silently.
3. **Which packs** — auth + UI/theme on by default. Confirm:
   - KMP: `--room`? `--ci`?
   - Next.js: `--auth-provider clerk|supabase`? `--theme-preset neutral|vivid`?
4. **Destination** (`--dest`) — absolute or sensible relative path.
5. **Verification** — runs `./gradlew build` / `pnpm build` by default; pass `--skip-verify` only if user opts out.
6. **Auth provider API keys** — if `--auth-provider clerk` or `supabase`, ask whether the user has keys ready. If yes, collect and pass via `--clerk-publishable-key` / `--clerk-secret-key` / `--supabase-url` / `--supabase-anon-key`. If no, the starter's graceful-no-keys path will show a "configure <provider>" notice on the sign-in page.
7. **Always verify with `pnpm dev` / `./gradlew :composeApp:run` after scaffold.** Build alone does not exercise middleware/runtime.
8. **KMP pack caveat** — `kmp:auth`, `kmp:room_data`, `kmp:ui_theme` are reference modules, not wired dependencies. The scaffold's stderr prints a wiring-instruction warning when these packs are kept — relay that warning to the user. (Full wiring tracked for v0.5.0.)

## Flags

See [`references/command-grammar.md`](../references/command-grammar.md) for the full set. Core flags:

```
--dest PATH                   # destination directory (required for create)
--package-prefix com.rzv      # dotted lowercase prefix
--auth-provider clerk|supabase
--theme-preset neutral|vivid
--room                        # KMP Room data pack
--ci                          # keep GitHub Actions workflow
--no-auth / --no-theme        # skip default packs
--clerk-publishable-key / --clerk-secret-key
--supabase-url / --supabase-anon-key
--skip-verify                 # skip the mandatory build gate
--force                       # allow non-empty destination
--refresh-cache               # re-clone the starter even if cached
```

## What the script does

1. Shallow-clones the pinned starter into `~/.cache/scaffold-factory/`.
2. Copies into `$DEST`.
3. Subtractive-prunes unselected KMP packs (deletes dirs + strips `settings.gradle.kts` include lines).
4. Applies find/replace substitutions declared by the starter's own `.scaffold.json`.
5. Generates `.env.local` (Next.js) or `local.properties` (KMP).
6. Runs build verification unless `--skip-verify` is passed.
7. Prints a "Next steps" block to stderr with stack-specific dev-server command, required env vars, and `gh repo create` invocation.

After scaffold completes, relay the Next Steps block to the user verbatim.
