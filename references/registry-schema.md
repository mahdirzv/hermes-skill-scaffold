# Registry Schema

Two files, two purposes:

| File | Lives in | Purpose |
|---|---|---|
| `references/registry.json` | skill repo | Points at pinned starter tags; declares stack defaults and pack ids |
| `.scaffold.json` | each starter repo | Declares how to rename and prune the starter |

## `registry.json`

```jsonc
{
  "version": "0.1.0",                       // registry version for traceability
  "min_scaffold_py_version": "0.1.0",       // script will refuse older versions

  "stack_defaults": {
    "<stack>": { "auth_provider": "...", "theme_preset": "..." }
  },

  "packs": [
    {
      "id":   "<stack>_base",               // required
      "stack": "kmp" | "nextjs",            // required
      "kind":  "base" | "feature" | "infra",// required
      "source": "git+<url>@<ref>[#<subpath>]" | "/absolute" | "$ENV_VAR" | "relative",
      "requires":        ["<other_id>"],    // selected together, or fail
      "conflicts_with":  ["<other_id>"],    // cannot coexist
      "placeholder_map": { "key": "value" },// merged into the plan's placeholders
      "verify":          ["cmd", ["cmd", "arg"]]  // run in $DEST after apply
    }
  ]
}
```

Feature/infra packs typically only need `id`, `stack`, and `kind`. The starter's own `.scaffold.json` decides what happens when each pack is selected or not.

### `source` resolution order

1. `git+<url>@<ref>[#<subpath>]` → shallow-clone into `~/.cache/hermes-skill-scaffold/`
2. `$ENV_VAR` → read an absolute path from the environment
3. Absolute path → used as-is
4. Relative path → resolved against the registry file's directory

## `.scaffold.json` (in each starter repo)

```jsonc
{
  "scaffold_schema_version": "1",
  "stack": "kmp" | "nextjs",
  "description": "...",

  "placeholders": [
    { "find": "LITERAL_STRING_IN_REPO", "replace_with": "{{template_key}}" }
  ],

  // Optional: generate an env file (Next.js style provider selection)
  "env_file": {
    "template": ".env.example",
    "output":   ".env.local",
    "set":      { "KEY": "{{template_key}}" }
  },

  // Pack map — keys are pack names (no stack prefix)
  "packs": {
    "<name>": {
      "paths":                         ["relative/path/to/delete/if/unselected"],
      "settings_gradle_include_line":  "include(\":module\")"
    }
  }
}
```

### Placeholder rules

- `find` is a literal substring (no regex).
- `replace_with` is a template containing `{{keys}}` expanded against the plan's merged placeholder map.
- Both file **contents** AND file **paths** (POSIX relpath) are searched. A find string of `com/example/foo` will relocate nested files.
- Longest `find` runs first, so overlapping strings don't collide.
- Strings that look like path separators (`/`) should be declared separately from dotted forms (`.`).

### Subtractive packs (KMP model)

When a pack is NOT selected:
- Its `paths` are deleted from `$DEST`.
- Its `settings_gradle_include_line` is stripped from `settings.gradle.kts` (if present).

### Env-file packs (Next.js model)

For provider-style feature flags, the `env_file` block writes `.env.local` with the requested `AUTH_PROVIDER` / `THEME_PRESET` values and leaves all other keys from `.env.example` intact.

## Template key reference

Built by `scaffold.py build_identifiers()`:

| Key | Example (name=`PlateTracker`, prefix=`com.rzv`) |
|---|---|
| `project_name`      | `PlateTracker` |
| `project_slug`      | `platetracker` |
| `project_root_name` | `PlateTracker` |
| `package_name`      | `com.rzv.platetracker` |
| `package_path`      | `com/rzv/platetracker` |
| `package_prefix`    | `com.rzv` |
| `bundle_id`         | `com.rzv.platetracker` |
| `folder_name`       | `platetracker` |
| `auth_provider`     | (from flag / stack default) |
| `theme_preset`      | (from flag / stack default) |

These are always available to every starter's `.scaffold.json` without declaration.
