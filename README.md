# hermes-skill-scaffold

Portable project-scaffolding skill for KMP and Next.js. Installable into any agent (Claude Code, OpenClaw, Hermes) with a single `git clone`.

## What it does

```
$ scaffold.py create kmp MyApp --dest ./MyApp --package-prefix com.rzv
```

Produces a ready-to-build KMP project at `./MyApp`:
- shallow-clones the canonical starter from a pinned tag
- renames `com.example.kmp_starter_project` → `com.rzv.myapp` across source and paths
- deletes packs the user didn't request (subtractive)
- writes `local.properties` with the detected Android SDK
- runs `./gradlew build` to verify

Same flow for Next.js:

```
$ scaffold.py create nextjs MyApp --dest ./MyApp --auth-provider clerk
```

Generates `.env.local` with `AUTH_PROVIDER=clerk` and runs `pnpm build`.

## Install

```bash
git clone https://github.com/mahdirzv/hermes-skill-scaffold ~/.claude/skills/hermes-skill-scaffold
```

That's it. On first run, starters are lazy-cloned into `~/.cache/hermes-skill-scaffold/`.

### Claude Code / OpenClaw / Hermes

Any agent that loads skills from `~/.claude/skills/` (or equivalent) will pick this up automatically. Trigger by asking: *"create a KMP project called Foo with auth"* or *"scaffold a Next.js starter named Bar"*.

## Commands

```bash
scaffold.py resolve <stack> <name> [flags]       # print the JSON plan
scaffold.py create  <stack> <name> --dest PATH   # resolve + apply + verify
scaffold.py apply   --plan plan.json --dest PATH # apply a saved plan
```

See [`references/command-grammar.md`](references/command-grammar.md) for all flags.

## Architecture

| Layer | File | Role |
|---|---|---|
| Router | [`SKILL.md`](SKILL.md) | Policy + decision rules (loaded by the agent) |
| Registry | [`references/registry.json`](references/registry.json) | Pinned starter tags + pack ids |
| Script | [`scripts/scaffold.py`](scripts/scaffold.py) | Deterministic file operations |
| Starter (KMP) | [mahdirzv/kmp-starter-project](https://github.com/mahdirzv/kmp-starter-project) | Canonical Compose Multiplatform base + packs |
| Starter (Next.js) | [mahdirzv/base-next-starter](https://github.com/mahdirzv/base-next-starter) | Canonical Next.js 16 base |

Each starter owns its own `.scaffold.json` declaring its placeholders and packs. The skill is generic; the starter is authoritative.

## License

MIT — see [`LICENSE`](LICENSE).
