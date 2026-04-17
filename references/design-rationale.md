# Design Rationale

Why the skill is split into router + registry + script + starter repos.

## The problem

Left to its own devices, a model given "scaffold a new KMP project" will re-invent the project structure every time. It:
- Generates files from memory (likely wrong for the current toolchain)
- Burns tokens writing Gradle/Kotlin boilerplate
- Produces subtly different output across runs (non-deterministic)
- Can't build-verify because it doesn't know what "correct" looks like
- Mixes optional concerns into the base (auth becomes mandatory, etc.)

## The split

```
┌──────────────────┐ routes   ┌──────────────────┐ reads  ┌────────────────────┐
│ Skill (SKILL.md) │ ───────▶ │ Registry (JSON)  │ ─────▶ │ Starter repo (git) │
└──────────────────┘          └──────────────────┘        └────────────────────┘
         │                              │                             │
         │ invokes                      │ pinned                      │ self-describes
         ▼                              ▼ tag                         ▼ via .scaffold.json
┌──────────────────┐  shallow-clones & applies               ┌─────────────────┐
│ scaffold.py      │ ─────────────────────────────────────▶  │ $DEST project   │
└──────────────────┘                                         └─────────────────┘
```

Each layer has one job:

- **Skill** — decide what to scaffold based on the user's request; pick flags
- **Registry** — map stack names to pinned starter URLs + pack ids
- **Script** — copy, rename, prune, verify (no LLM in the hot path)
- **Starter** — own the actual project shape + declare how to parameterize it

## Why starters declare their own `.scaffold.json`

Earlier iterations of this skill duplicated the starter's shape inside the skill repo. When the starter evolved, the skill drifted. Moving the placeholder map and pack structure into `<starter>/.scaffold.json` makes the starter fully self-describing — the skill is generic.

## Why subtractive instead of additive for KMP packs

The KMP starter is already buildable with all packs integrated. Deletion + `settings.gradle.kts` line-stripping is a one-line-of-code change per pack. Additive (copy base, then copy each pack from a separate tree) required maintaining N extra template trees and debugging file-collision issues.

Trade-off: the starter repo ships with all packs present. A user not using the scaffold sees all packs — but that is correct behavior for a starter repo meant to be explored.

## Why env-driven for Next.js

Next.js already supports feature flags via `process.env`. Forcing a pack/unpack model would mean extracting `src/modules/auth/providers/clerk/` into a pack and copying it back on demand — pointless churn.

Instead, the base starter ships with all providers; the scaffold generates `.env.local` with the requested `AUTH_PROVIDER` set, and at runtime only the chosen provider's code path executes.

## Why git+ URLs with pinned refs

- Single source of truth per starter (no drift vs. a bundled copy)
- Reproducible — `v0.1.0` today == `v0.1.0` next year
- Offline-capable after first run (local cache)
- Simple distribution — one skill repo clone; starters lazy-load

## Why verification is default-on

A scaffold that "looks right" but doesn't compile is worse than no scaffold. Running `./gradlew build` or `pnpm build` immediately surfaces classpath, template, or placeholder bugs. `--skip-verify` exists for the impatient or for CI where a separate build step follows.

## Anti-patterns this skill refuses

- Hand-writing files with the LLM instead of using the script
- Multiple auth providers wired up by default
- Theme values hardcoded across screens
- One monolithic tool that hides every step
- Skills that duplicate starter content inline
- Floating `@main` registry refs in released versions
