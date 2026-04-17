# Command Grammar

The scaffold workflow uses a small explicit grammar. The skill routes these commands; `scripts/scaffold.py` does the deterministic work.

## `create` — resolve and apply in one pass (primary command)

```bash
python3 scripts/scaffold.py create <stack> <name> --dest <path> \
  [--registry PATH] \
  [--cache-dir PATH] \
  [--package-prefix com.example] \
  [--bundle-prefix com.example] \
  [--auth-provider clerk|supabase|...] \
  [--theme-preset neutral|vivid|...] \
  [--room] [--ci] \
  [--no-auth] [--no-theme] \
  [--pack <extra_pack_id>]... \
  [--plan-out plan.json] \
  [--force] [--skip-verify] [--refresh-cache]
```

## `resolve` — print the JSON plan, do not touch files

```bash
python3 scripts/scaffold.py resolve <stack> <name> [same flags as create]
```

## `apply` — run a previously-resolved plan against a destination

```bash
python3 scripts/scaffold.py apply --plan plan.json --dest <path> \
  [--force] [--skip-verify] [--refresh-cache]
```

## Stacks

- `kmp` — Kotlin Multiplatform (Compose MP, Android/iOS/JVM)
- `nextjs` — Next.js 16 App Router

## Defaults

- `--package-prefix`: `com.example`
- `--auth-provider`: registry `stack_defaults[stack].auth_provider` (fallback `clerk`)
- `--theme-preset`: registry `stack_defaults[stack].theme_preset` (fallback `neutral`)
- auth + theme packs included by default; pass `--no-auth` / `--no-theme` to skip
- build verification runs by default; pass `--skip-verify` to opt out

## Pack conventions

Pack ids follow `<stack>_<name>`:

- KMP: `kmp_base`, `kmp_auth`, `kmp_ui_theme`, `kmp_room`, `kmp_ci`
- Next.js: `nextjs_base`, `nextjs_auth`, `nextjs_ui_theme`, `nextjs_ci`

The starter's `.scaffold.json` maps each pack name (without the stack prefix) to either:
- `paths: [...]` — directories/files to delete when unselected (subtractive)
- Or is referenced indirectly via `env_file.set` (Next.js auth/theme packs)

## Cache

Cloned starters live under `~/.cache/scaffold-factory/<cache-key>/`. Re-runs reuse the cache. Use `--refresh-cache` to force a fresh clone.

## Post-scaffold: creating a GitHub repo

The scaffold intentionally does NOT create a GitHub repo for you. After `create` finishes:

```bash
cd <dest>
gh repo create <slug> --source . --push --private   # or --public
```

This keeps the scaffold itself focused on file operations and leaves remote-state side effects to a command you invoke explicitly.
