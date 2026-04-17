#!/usr/bin/env python3
"""Deterministic project scaffolder for KMP and Next.js starters.

Resolves pinned starter repos declared in ~/.claude/skills/scaffold-factory/references/registry.json
(or wherever this script's sibling references/ lives), shallow-clones them to a
local cache, copies them into $DEST, applies find/replace rules declared in the
starter's own .scaffold.json, and optionally prunes packs the user did not request.

Usage:
  scaffold.py resolve <stack> <name> [flags]        # print JSON plan
  scaffold.py create  <stack> <name> --dest PATH    # resolve + apply + verify
  scaffold.py apply   --plan plan.json --dest PATH  # apply a saved plan

Requirements: Python 3.10+, git. Per-stack: JDK+Android SDK (KMP) or Node 20+ and pnpm (Next.js).
See references/command-grammar.md for the full flag list.
"""
from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.stderr.write(
        "scaffold.py requires Python 3.10 or newer. "
        f"You're running Python {sys.version_info.major}.{sys.version_info.minor}.\n"
        "Install a newer Python (e.g. via pyenv, asdf, or brew) and retry.\n"
    )
    raise SystemExit(2)

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

SCAFFOLD_VERSION = "0.4.8"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY = SCRIPT_DIR.parent / "references" / "registry.json"
DEFAULT_CACHE = Path.home() / ".cache" / "scaffold-factory"

KIND_ORDER = {"base": 0, "feature": 1, "infra": 2}
SKIP_DIRS = {
    ".git", ".gradle", ".idea", ".kotlin", ".next", ".run", ".sisyphus",
    ".swiftpm", "build", "coverage", "DerivedData", "dist", "node_modules",
    "xcuserdata", ".turbo",
}

# Starter manifest (`.scaffold.json`) schema versions this scaffold.py
# understands. A starter declaring a version not in this set fails with
# EXIT_STARTER at read time — cheaper than diagnosing cryptic "unexpected
# structure" errors downstream when a new schema ships.
SUPPORTED_SCAFFOLD_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1"})

# Provider secret flags: CLI flag name, placeholder key, env-var fallback.
# Env-var fallback keeps secrets out of shell history when users `export` them.
# CLI flag always wins.
_SECRET_FLAG_TABLE: tuple[tuple[str, str, str], ...] = (
    ("clerk_publishable_key", "clerk_publishable_key", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"),
    ("clerk_secret_key",      "clerk_secret_key",      "CLERK_SECRET_KEY"),
    ("supabase_url",          "supabase_url",          "NEXT_PUBLIC_SUPABASE_URL"),
    ("supabase_anon_key",     "supabase_anon_key",     "NEXT_PUBLIC_SUPABASE_ANON_KEY"),
)

# Placeholder keys whose values must NEVER appear in stdout JSON. Secrets set
# via flags or env fallback flow into plan["placeholder_map"]; without this
# redaction a `scaffold.py resolve ... --clerk-secret-key sk_live_X` would print
# the full secret to stdout and leak it into CI logs, shell history via `> out`,
# or `tee`. The in-memory plan passed to apply_plan keeps real values — we
# redact only at the serialize-to-stdout boundary.
_REDACT_PLACEHOLDER_KEYS: frozenset[str] = frozenset(
    placeholder for _flag, placeholder, _env in _SECRET_FLAG_TABLE
)


def _redact_plan_for_stdout(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a deep-enough copy of `plan` with secret placeholder values masked."""
    pm = plan.get("placeholder_map")
    if not isinstance(pm, dict):
        return plan
    redacted_pm = {
        k: ("[REDACTED]" if k in _REDACT_PLACEHOLDER_KEYS and v else v)
        for k, v in pm.items()
    }
    return {**plan, "placeholder_map": redacted_pm}

# Exit code taxonomy. Lets callers (CI, wrapper scripts, humans) distinguish
# retryable user-input errors from system errors, network failures, and starter
# bugs. 1 is retained as a generic fallback for anything not yet classified.
EXIT_GENERIC = 1
EXIT_USAGE   = 2   # bad flags, invalid identifiers, unknown pack id, dest not empty
EXIT_SYSTEM  = 3   # missing executable, source path missing, filesystem/OS errors, verify failure
EXIT_NETWORK = 4   # git clone/checkout failures, unreachable remote
EXIT_STARTER = 5   # registry/manifest malformed, placeholder drift, rename collision


# ---------- errors ----------

def fail(message: str, code: int = EXIT_GENERIC) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def fail_usage(message: str) -> NoReturn:   fail(message, EXIT_USAGE)
def fail_system(message: str) -> NoReturn:  fail(message, EXIT_SYSTEM)
def fail_network(message: str) -> NoReturn: fail(message, EXIT_NETWORK)
def fail_starter(message: str) -> NoReturn: fail(message, EXIT_STARTER)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# ---------- subprocess wrapper with actionable missing-tool errors ----------

_MISSING_TOOL_HINTS = {
    "pnpm": "Install with `npm i -g pnpm` or `corepack enable`.",
    "npm": "Comes with Node.js — install from https://nodejs.org/.",
    "node": "Install Node.js 20+ from https://nodejs.org/.",
    "git": "Install git from https://git-scm.com/.",
    "gh": "Install GitHub CLI from https://cli.github.com/.",
    "./gradlew": "The scaffolded project should include a Gradle wrapper. If it's missing, the starter may be incomplete.",
    "gradle": "Prefer `./gradlew` from the project root. If you need a system gradle: https://gradle.org/install/.",
}


def _tool_hint(executable: str) -> str:
    if executable in _MISSING_TOOL_HINTS:
        return _MISSING_TOOL_HINTS[executable]
    return "Install it (or add it to PATH) before retrying."


def run_tool(cmd, *, cwd=None, shell=False, capture=True, env=None) -> subprocess.CompletedProcess:
    """Run a subprocess; convert FileNotFoundError into a clean fail() with a hint.

    Trust boundary: shell=True is only reached from run_verify() when a registry
    entry declares a verify command as a string (not a list). The registry is
    shipped in-repo (references/registry.json) and only the maintainer can
    change it — so the shell invocation is trusted. Prefer list form in the
    registry; strings are supported only for backwards compat.
    """
    display = cmd if isinstance(cmd, str) else " ".join(cmd)
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            shell=shell,
            text=True,
            capture_output=capture,
            env=env,
        )
    except FileNotFoundError:
        first = cmd.split()[0] if isinstance(cmd, str) else cmd[0]
        fail_system(
            f"required executable not found: {first!r} "
            f"(while trying to run: {display}). {_tool_hint(first)}"
        )


# ---------- identifiers ----------

def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        fail_usage(f"cannot slugify project name: {value!r}")
    return slug


def humanize(value: str) -> str:
    if re.search(r"[-_ ]", value):
        parts = [p for p in re.split(r"[-_ ]+", value.strip()) if p]
        return " ".join(p[:1].upper() + p[1:] for p in parts)
    return value.strip()


def compact_identifier(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    if not compact:
        fail_usage(f"cannot build compact identifier from {value!r}")
    return compact


# Dotted Kotlin/Java package prefix: lowercase letters, digits, underscores,
# each segment starting with a letter. Matches what Kotlin/Gradle accept
# without backticks in common namespace usage.
_PACKAGE_PREFIX_RE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)*$")


def validate_package_prefix(prefix: str) -> None:
    if not _PACKAGE_PREFIX_RE.match(prefix):
        fail_usage(
            f"invalid --package-prefix {prefix!r}: must be dotted lowercase "
            "segments starting with a letter (e.g. `com.example`, `dev.mahdi`, "
            "`io.yourcompany`). Allowed chars per segment: [a-z0-9_]."
        )


def build_identifiers(stack: str, name: str, package_prefix: str, bundle_prefix: str | None) -> dict[str, str]:
    validate_package_prefix(package_prefix)
    if bundle_prefix is not None:
        validate_package_prefix(bundle_prefix)

    slug = slugify(name)
    display = humanize(name)
    compact = compact_identifier(slug)
    package_name = f"{package_prefix}.{compact}"
    package_path = package_name.replace(".", "/")

    # project_root_name must be Gradle-legal: rootProject.name = "...",
    # Xcode project name, and fs-safe. Strip everything outside [A-Za-z0-9_].
    root_name = re.sub(r"[^A-Za-z0-9_]+", "", display.replace(" ", ""))
    if not root_name:
        fail_usage(
            f"project name {name!r} produces an empty project_root_name after "
            "sanitization (only letters, digits, and underscores are kept). "
            "Pick a name with at least one alphanumeric character."
        )

    return {
        "stack": stack,
        "project_name": display,
        "project_slug": slug,
        "project_root_name": root_name,
        "package_name": package_name,
        "package_path": package_path,
        "package_prefix": package_prefix,
        "bundle_id": f"{bundle_prefix or package_prefix}.{compact}",
        "bundle_prefix": bundle_prefix or package_prefix,
        "repo_name": slug,
        "folder_name": slug,
    }


# ---------- android SDK ----------

def resolve_android_sdk() -> str | None:
    for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SDK"):
        p = os.environ.get(var)
        if p and Path(p).is_dir():
            return p
    for candidate in (
        Path.home() / "Library" / "Android" / "sdk",
        Path.home() / "Android" / "Sdk",
        Path("/usr/local/android-sdk"),
        Path("/opt/android-sdk"),
    ):
        if candidate.is_dir():
            return str(candidate)
    return None


# ---------- git+ source resolution ----------

_GIT_PLUS_RE = re.compile(r"^git\+(?P<url>https?://[^@#]+)(?:@(?P<ref>[^#]+))?(?:#(?P<sub>.*))?$")


def parse_git_source(source: str) -> tuple[str, str, str] | None:
    """Parse `git+https://host/org/repo@ref#subpath` → (url, ref, subpath)."""
    m = _GIT_PLUS_RE.match(source)
    if not m:
        return None
    url = m.group("url")
    ref = m.group("ref") or "HEAD"
    sub = (m.group("sub") or "").strip("/")
    return url, ref, sub


def cache_key(url: str, ref: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.replace(":", "_")
    path = parsed.path.strip("/").replace("/", "_").removesuffix(".git")
    safe_ref = re.sub(r"[^A-Za-z0-9._-]+", "_", ref)
    return f"{host}__{path}__{safe_ref}"


def _git_env() -> dict[str, str]:
    """Subprocess env that disables interactive prompts so git fails fast
    if it ever does need credentials, instead of hanging on a TTY read."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def ensure_cached_clone(url: str, ref: str, cache_dir: Path, refresh: bool = False) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / cache_key(url, ref)
    if dest.exists() and refresh:
        shutil.rmtree(dest)
    if dest.exists():
        return dest

    tmp = dest.with_suffix(".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    cmd = ["git", "clone", "--depth", "1", "--branch", ref, url, str(tmp)]
    print(f"[scaffold] cloning {url}@{ref} → {dest}", file=sys.stderr)
    proc = run_tool(cmd, env=_git_env())
    if proc.returncode != 0:
        # fall back to full clone + checkout for raw SHAs
        if tmp.exists():
            shutil.rmtree(tmp)
        cmd = ["git", "clone", url, str(tmp)]
        proc = run_tool(cmd, env=_git_env())
        if proc.returncode != 0:
            fail_network(f"git clone failed for {url}: {proc.stderr.strip()}")
        co = run_tool(["git", "-C", str(tmp), "checkout", ref], env=_git_env())
        if co.returncode != 0:
            fail_network(f"git checkout {ref} failed: {co.stderr.strip()}")
    tmp.rename(dest)
    return dest


def resolve_source_path(raw: str, registry_base: Path, cache_dir: Path, refresh: bool = False) -> Path:
    """Resolve a registry source string to an on-disk path."""
    git = parse_git_source(raw)
    if git is not None:
        url, ref, sub = git
        root = ensure_cached_clone(url, ref, cache_dir, refresh=refresh)
        return (root / sub).resolve() if sub else root

    if raw.startswith("$"):
        env_var = raw[1:]
        val = os.environ.get(env_var, "").strip()
        if not val:
            fail_usage(f"source {raw!r} references env var ${env_var} which is not set")
        return Path(val).expanduser().resolve()

    p = Path(raw)
    if p.is_absolute():
        return p.expanduser().resolve()
    return (registry_base / raw).expanduser().resolve()


# ---------- registry ----------

def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail_starter(f"registry not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail_starter("registry must be a JSON object")
    data.setdefault("packs", [])
    data.setdefault("stack_defaults", {})
    min_ver = data.get("min_scaffold_py_version")
    if min_ver and tuple(map(int, min_ver.split("."))) > tuple(map(int, SCAFFOLD_VERSION.split("."))):
        fail_starter(f"registry requires scaffold.py >= {min_ver} but this is {SCAFFOLD_VERSION}")
    return data


def validate_entry(entry: dict[str, Any]) -> None:
    for field in ("id", "stack", "kind"):
        if field not in entry:
            fail_starter(f"registry entry missing required field {field!r}: {entry}")
    if entry["kind"] not in KIND_ORDER:
        fail_starter(f"entry {entry['id']!r} has invalid kind {entry['kind']!r}")


def index_registry(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for e in entries:
        validate_entry(e)
        if e["id"] in idx:
            fail_starter(f"duplicate registry id: {e['id']}")
        idx[e["id"]] = e
    return idx


# ---------- pack selection ----------

def collect_selected_ids(args: argparse.Namespace) -> list[str]:
    ids = [f"{args.stack}_base"]
    if not args.no_auth:
        ids.append(f"{args.stack}_auth")
    if not args.no_theme:
        ids.append(f"{args.stack}_ui_theme")
    if args.room:
        ids.append(f"{args.stack}_room")
    if args.ci:
        ids.append(f"{args.stack}_ci")
    ids.extend(args.pack or [])
    seen: set[str] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def select_entries(indexed: dict[str, dict[str, Any]], stack: str, selected_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_id = f"{stack}_base"
    if base_id not in indexed:
        fail_starter(f"missing base entry: {base_id}")
    base = indexed[base_id]
    if base["stack"] != stack:
        fail_starter(f"base entry {base_id} has mismatched stack {base['stack']!r}")

    rest: list[dict[str, Any]] = []
    for eid in selected_ids:
        if eid == base_id:
            continue
        if eid not in indexed:
            fail_usage(f"unknown registry id: {eid}")
        e = indexed[eid]
        if e["stack"] != stack:
            fail_usage(f"entry {eid!r} belongs to stack {e['stack']!r}, expected {stack!r}")
        rest.append(e)
    rest.sort(key=lambda e: (KIND_ORDER[e["kind"]], e["id"]))
    return base, rest


def validate_dependencies(indexed: dict[str, dict[str, Any]], entries: list[dict[str, Any]]) -> None:
    sel = {e["id"] for e in entries}
    for e in entries:
        for dep in e.get("requires", []):
            if dep not in sel:
                fail_usage(f"entry {e['id']!r} requires {dep!r} but it was not selected")
        for con in e.get("conflicts_with", []):
            if con in sel:
                fail_usage(f"entry {e['id']!r} conflicts with {con!r}")


# ---------- placeholders ----------

def merged_placeholders(registry: dict[str, Any], base: dict[str, Any], packs: list[dict[str, Any]], args: argparse.Namespace) -> dict[str, str]:
    values: dict[str, Any] = {}
    values.update(registry.get("stack_defaults", {}).get(args.stack, {}))
    values.update(base.get("placeholder_map", {}) or {})
    for pk in packs:
        values.update(pk.get("placeholder_map", {}) or {})
    values.update(build_identifiers(args.stack, args.name, args.package_prefix, args.bundle_prefix))
    if args.auth_provider:
        values["auth_provider"] = args.auth_provider
    if args.theme_preset:
        values["theme_preset"] = args.theme_preset
    # Optional provider API keys — only recorded if explicitly passed or present
    # in env. Flag wins over env; env keeps secrets out of shell history. Empty
    # values pass through apply_env_file which skips empty lines, so users who
    # omit them get a clean .env.local without placeholder-looking junk.
    for flag_name, placeholder, env_var in _SECRET_FLAG_TABLE:
        flag_value = getattr(args, flag_name, None) or os.environ.get(env_var, "")
        if flag_value:
            values[placeholder] = flag_value
        else:
            values.setdefault(placeholder, "")
    values.setdefault("auth_provider", "clerk")
    values.setdefault("theme_preset", "neutral")
    return {str(k): str(v) for k, v in values.items()}


def placeholder_expand(text: str, values: dict[str, str]) -> str:
    # Longest-key-first substitution of {{key}} tokens
    for key in sorted(values, key=len, reverse=True):
        text = text.replace("{{" + key + "}}", values[key])
    return text


# ---------- .scaffold.json (starter-side manifest) ----------

def read_starter_manifest(src: Path) -> dict[str, Any]:
    p = src / ".scaffold.json"
    if not p.exists():
        return {}
    try:
        manifest = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail_starter(f"invalid .scaffold.json in {src}: {e}")
    # Validate schema version. A starter declaring a newer version than
    # scaffold.py understands would otherwise silently misbehave (e.g.
    # conditional placeholders or per-file matchers added in a v2 schema).
    # If the field is missing, assume v1 for backwards-compat with starters
    # predating this check.
    schema = manifest.get("scaffold_schema_version", "1") if isinstance(manifest, dict) else "1"
    if str(schema) not in SUPPORTED_SCAFFOLD_SCHEMA_VERSIONS:
        fail_starter(
            f"unsupported .scaffold.json schema_version {schema!r} in {src}. "
            f"This scaffold.py (v{SCAFFOLD_VERSION}) supports: "
            f"{sorted(SUPPORTED_SCAFFOLD_SCHEMA_VERSIONS)}. "
            f"Upgrade scaffold-factory or pin the starter to an older tag."
        )
    return manifest


def collect_post_scaffold_notes(manifest: dict[str, Any], selected_pack_keys: set[str]) -> dict[str, Any]:
    """Gather starter-owned post-scaffold notes for the kept packs.

    The starter's .scaffold.json may declare:
      - `post_scaffold_notes.heading`: list[str] rendered once before per-pack notes
      - `post_scaffold_notes.footer`:  list[str] rendered once after per-pack notes
      - `packs.<key>.post_scaffold_note`: str rendered for each kept pack that has one

    Returns {heading, footer, per_pack: [(key, note)]} preserving manifest
    declaration order so output is stable. Returns an empty dict when no
    selected pack has a note — callers can cheaply skip the section.

    This lets scaffold.py stay stack-agnostic: the "reference modules need
    manual wiring" text lives in the starter, not the scaffolder.
    """
    if not manifest:
        return {}
    packs = manifest.get("packs", {}) or {}
    per_pack: list[tuple[str, str]] = []
    for key, spec in packs.items():
        if key not in selected_pack_keys:
            continue
        note = (spec or {}).get("post_scaffold_note")
        if note:
            per_pack.append((key, note))
    if not per_pack:
        return {}
    notes_block = manifest.get("post_scaffold_notes", {}) or {}
    return {
        "heading": list(notes_block.get("heading") or []),
        "footer":  list(notes_block.get("footer")  or []),
        "per_pack": per_pack,
    }


def apply_starter_placeholders(dest: Path, manifest: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    """Rewrite file CONTENTS and relocate files whose POSIX relpath contains a find string.

    Rules declared by the starter's .scaffold.json:
      placeholders: [ { find: "...", replace_with: "{{...}}" }, ... ]

    The find string is matched on:
      (a) file contents — every text file under dest (except SKIP_DIRS)
      (b) POSIX relative path of each file (so multi-segment paths like
          `com/example/foo/Bar.kt` rename correctly to `com/rzv/bar/Bar.kt`).

    Drift detection: any placeholder whose `find` string matches nothing
    emits a warning (likely .scaffold.json is out of sync with the repo);
    if ALL placeholders match nothing, the function fails outright.

    Returns a dict with keys: changed_files, renamed_paths, match_counts.
    """
    pairs: list[tuple[str, str]] = []
    for entry in manifest.get("placeholders", []) or []:
        find = entry.get("find")
        rep = entry.get("replace_with", "")
        if not find:
            continue
        pairs.append((find, placeholder_expand(rep, values)))
    # Longest find first so overlapping substrings resolve correctly
    pairs.sort(key=lambda p: len(p[0]), reverse=True)
    if not pairs:
        return {"changed_files": 0, "renamed_paths": 0, "match_counts": {}}

    match_counts: dict[str, int] = {find: 0 for find, _ in pairs}

    def replace_all(text: str) -> str:
        for old, new in pairs:
            if old in text:
                match_counts[old] += text.count(old)
                text = text.replace(old, new)
        return text

    # Resolve once for the containment check in Pass 2.
    dest_resolved = dest.resolve()

    # ---- Pass 1: rewrite file contents ----
    # Skip symlinks: we don't want to follow them and write *through* the link
    # into something outside `dest` (e.g. a tracked `link -> ~/.ssh/config`).
    changed_files = 0
    for path in dest.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        rewritten = replace_all(original)
        if rewritten != original:
            path.write_text(rewritten, encoding="utf-8")
            changed_files += 1

    # ---- Pass 2: relocate files on full relpath match ----
    # Guards (defence in depth, in order):
    #   (a) skip symlinks
    #   (b) reject any .. segment in the computed new path
    #   (c) reject targets that resolve outside `dest`
    # Any of these failing is a starter bug (malicious or misconfigured
    # `.scaffold.json`), hence EXIT_STARTER.
    renamed_paths = 0
    relocations: list[tuple[Path, Path]] = []
    for path in dest.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_symlink() or not path.is_file():
            continue
        rel = path.relative_to(dest).as_posix()
        new_rel = replace_all(rel)
        if new_rel == rel:
            continue
        if ".." in PurePosixPath(new_rel).parts:
            fail_starter(
                f"placeholder rewrite produced a parent-traversal path: {rel!r} → {new_rel!r}. "
                "Check .scaffold.json placeholders for `find`/`replace_with` pairs that yield `..` segments."
            )
        tgt = dest / new_rel
        try:
            tgt_resolved = tgt.resolve()
        except OSError:
            fail_starter(f"placeholder rewrite target could not be resolved: {tgt}")
        try:
            tgt_resolved.relative_to(dest_resolved)
        except ValueError:
            fail_starter(
                f"placeholder rewrite would move file outside --dest: {rel!r} → {new_rel!r}. "
                "Rejecting to prevent path-traversal."
            )
        relocations.append((path, tgt))

    for src, tgt in relocations:
        if tgt.exists():
            fail_starter(f"rename collision: {src} → {tgt}")
        tgt.parent.mkdir(parents=True, exist_ok=True)
        src.rename(tgt)
        renamed_paths += 1

    # ---- Pass 3: prune empty directories left behind ----
    all_dirs = sorted((p for p in dest.rglob("*") if p.is_dir()),
                      key=lambda p: len(p.parts), reverse=True)
    for d in all_dirs:
        if any(part in SKIP_DIRS for part in d.parts):
            continue
        try:
            d.rmdir()  # succeeds only if empty
        except OSError:
            pass

    # ---- Drift detection ----
    zero_match = [find for find, count in match_counts.items() if count == 0]
    if zero_match and len(zero_match) == len(pairs):
        fail_starter(
            "no placeholder find strings matched anything in the starter; "
            ".scaffold.json is out of sync with the repo. Missing strings: "
            + ", ".join(repr(f) for f in zero_match)
        )
    for find in zero_match:
        warn(
            f"placeholder find string {find!r} matched 0 files/paths; "
            "likely .scaffold.json has drifted from the starter content."
        )

    return {
        "changed_files": changed_files,
        "renamed_paths": renamed_paths,
        "match_counts": match_counts,
    }


# ---------- subtractive prune ----------

def prune_unselected_packs(dest: Path, manifest: dict[str, Any], selected_pack_keys: set[str]) -> list[str]:
    """Delete paths for packs the user did NOT select, and strip their include lines."""
    removed: list[str] = []
    packs = manifest.get("packs", {}) or {}
    for pack_key, spec in packs.items():
        if pack_key in selected_pack_keys:
            continue
        # Path pack: delete listed paths
        for rel in spec.get("paths", []) or []:
            target = dest / rel
            if target.exists():
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
                removed.append(rel)
        # Gradle include line: strip from settings.gradle.kts
        include_line = spec.get("settings_gradle_include_line")
        if include_line:
            sg = dest / "settings.gradle.kts"
            if sg.exists():
                contents = sg.read_text(encoding="utf-8")
                new = "\n".join(ln for ln in contents.splitlines() if ln.strip() != include_line.strip())
                if not new.endswith("\n"):
                    new += "\n"
                if new != contents:
                    sg.write_text(new, encoding="utf-8")
                    removed.append(f"settings.gradle.kts:{include_line}")
    return removed


def apply_env_file(dest: Path, manifest: dict[str, Any], values: dict[str, str]) -> str | None:
    """Write a MINIMAL env file containing only the scaffold's declared overrides.

    We intentionally do NOT copy the whole template — .env.example often
    contains placeholder values (e.g. `CLERK_PUBLISHABLE_KEY=pk_test_`) that
    look valid to third-party SDKs and would break the build. The consumer
    copies the rest from .env.example once they have real keys.
    """
    spec = manifest.get("env_file")
    if not spec:
        return None
    out = dest / spec.get("output", ".env.local")
    overrides = {k: placeholder_expand(v, values) for k, v in (spec.get("set") or {}).items()}
    if not overrides:
        return None
    lines = [
        "# Generated by scaffold.py — contains only the provider/theme selection and",
        "# any keys you passed as CLI flags. Copy additional keys from " + spec.get("template", ".env.example"),
        "# once you have real values.",
        "",
    ]
    for k, v in overrides.items():
        # Skip empty values — avoids writing `KEY=` lines that SDKs may treat as
        # invalid/present-but-blank. Users who didn't pass a CLI flag for this key
        # simply won't see the line at all, which is what graceful no-keys wants.
        if not v:
            continue
        lines.append(f"{k}={v}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out.relative_to(dest))


# ---------- copy ----------

def ignore_fn(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in SKIP_DIRS or n == ".DS_Store"}


def copy_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        fail_system(f"source path does not exist: {src}")
    if not src.is_dir():
        fail_system(f"source path is not a directory: {src}")
    # symlinks=False: do NOT preserve symlinks. Instead of copying them verbatim
    # (which could point outside dest and enable path-traversal when Pass 1
    # writes through them), copytree copies the file they reference. Combined
    # with the is_symlink() skip in apply_starter_placeholders, this keeps all
    # writes confined to `dest`.
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=ignore_fn, symlinks=False)


# ---------- verification ----------

def run_verify(commands: list[str | list[str]], cwd: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cmd in commands:
        if isinstance(cmd, list):
            display = " ".join(cmd)
            proc = run_tool(cmd, cwd=cwd, shell=False)
        else:
            display = cmd
            proc = run_tool(cmd, cwd=cwd, shell=True)
        print(f"$ {display}")
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        results.append({"command": display, "returncode": proc.returncode})
        if proc.returncode != 0:
            fail_system(f"verification command failed: {display}")
    return results


# ---------- android local.properties ----------

def write_local_properties(dest: Path) -> str | None:
    lp = dest / "local.properties"
    if lp.exists():
        return None
    sdk = resolve_android_sdk()
    if sdk:
        lp.write_text(f"sdk.dir={sdk}\n", encoding="utf-8")
        return sdk
    lp.write_text("# sdk.dir=<SET THIS OR EXPORT ANDROID_HOME/ANDROID_SDK_ROOT>\n", encoding="utf-8")
    warn("Android SDK not found; wrote placeholder local.properties. Set ANDROID_HOME or edit local.properties.")
    return None


# ---------- plan / apply ----------

def resolve_plan(args: argparse.Namespace) -> dict[str, Any]:
    registry = load_registry(Path(args.registry))
    indexed = index_registry(registry["packs"])
    selected_ids = collect_selected_ids(args)
    base, packs = select_entries(indexed, args.stack, selected_ids)
    validate_dependencies(indexed, [base] + packs)
    placeholders = merged_placeholders(registry, base, packs, args)

    return {
        "scaffold_version": SCAFFOLD_VERSION,
        "stack": args.stack,
        "name": args.name,
        "destination": str(Path(args.dest).expanduser()) if args.dest else None,
        "base": base,
        "packs": packs,
        "placeholder_map": placeholders,
        "selected_ids": [base["id"], *[e["id"] for e in packs]],
        "_registry_path": str(Path(args.registry).expanduser().resolve()),
        "_cache_dir": str(Path(args.cache_dir).expanduser().resolve()) if args.cache_dir else str(DEFAULT_CACHE),
    }


def apply_plan(
    plan: dict[str, Any],
    dest: Path,
    *,
    force: bool = False,
    skip_verify: bool = False,
    refresh_cache: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Materialize a resolved plan into dest.

    dry_run=True: do all the work (copy, placeholder rewrite, pack pruning,
    env file generation) but against a throwaway tempdir. The user's dest is
    never touched. Verification is always skipped. Returns the same stats dict
    with `dry_run: true` and `destination: None` so tooling can tell the
    difference. Useful for previewing a scaffold before committing to it.
    """
    dest = dest.expanduser()
    intended_dest = dest
    # Track whether *we* created the dest directory this call. If verify fails
    # (or any later step raises), we should rm it so the next run doesn't hit
    # "destination already exists and is not empty". Only cleans directories
    # we ourselves created — never touches a pre-existing dest (which the
    # --force path is explicitly opting into).
    we_created_dest = False
    if dry_run:
        import tempfile
        dest = Path(tempfile.mkdtemp(prefix="scaffold-dryrun-"))
        force = True       # our tmp dir is empty, but be defensive
        skip_verify = True  # never run external verify in dry-run
        we_created_dest = True  # tempdir — always our own
    elif dest.exists() and any(dest.iterdir()) and not force:
        fail_usage(f"destination already exists and is not empty: {dest}")
    else:
        we_created_dest = not dest.exists()
    dest.mkdir(parents=True, exist_ok=True)

    try:
        registry_base = Path(plan["_registry_path"]).parent
        if registry_base.name == "references":
            registry_base = registry_base.parent
        cache_dir = Path(plan.get("_cache_dir") or DEFAULT_CACHE)

        base = plan["base"]
        # Pre-flight: resolve base source and check it exists BEFORE copying anything
        base_source = resolve_source_path(base["source"], registry_base, cache_dir, refresh=refresh_cache)
        if not base_source.exists():
            fail_starter(f"base source missing after resolve: {base_source}")

        # Copy whole base tree
        copy_tree(base_source, dest)

        # Read the starter's .scaffold.json manifest
        manifest = read_starter_manifest(dest)
        if not manifest:
            warn(f"no .scaffold.json in base {base['id']}; scaffold will only use registry placeholder_map")

        # Figure out which packs the user selected (as starter-manifest keys)
        # Registry ids are like "kmp_auth"; strip the stack prefix to match manifest keys.
        selected_pack_keys: set[str] = set()
        stack = plan["stack"]
        prefix = f"{stack}_"
        for e in plan["packs"]:
            key = e["id"][len(prefix):] if e["id"].startswith(prefix) else e["id"]
            selected_pack_keys.add(key)

        # Subtractive prune: delete unselected pack paths and strip include lines
        removed = prune_unselected_packs(dest, manifest, selected_pack_keys) if manifest else []

        # Rewrite find/replace pairs + path renames from the starter manifest
        placeholder_stats = (
            apply_starter_placeholders(dest, manifest, plan["placeholder_map"])
            if manifest else {"changed_files": 0, "renamed_paths": 0, "match_counts": {}}
        )
        changed_files = placeholder_stats["changed_files"]
        renamed_paths = placeholder_stats["renamed_paths"]

        # Starter-owned post-scaffold notes (captured BEFORE the manifest is deleted)
        post_notes = collect_post_scaffold_notes(manifest, selected_pack_keys) if manifest else {}

        # env_file generation (Next.js)
        env_written = apply_env_file(dest, manifest, plan["placeholder_map"]) if manifest else None

        # KMP: local.properties
        sdk_written = None
        if plan["stack"] == "kmp":
            sdk_written = write_local_properties(dest)

        # Remove the manifest from the generated project — it's not part of consumer projects
        sm = dest / ".scaffold.json"
        if sm.exists():
            sm.unlink()

        # Verification (on by default)
        verify_results: list[dict[str, Any]] = []
        if not skip_verify:
            verify = base.get("verify", [])
            for pk in plan["packs"]:
                for v in pk.get("verify", []) or []:
                    if v not in verify:
                        verify.append(v)
            if verify:
                verify_results = run_verify(verify, cwd=dest)

        result = {
            "destination": None if dry_run else str(dest),
            "changed_files": changed_files,
            "renamed_paths": renamed_paths,
            "placeholder_match_counts": placeholder_stats["match_counts"],
            "removed_packs": removed,
            "env_file": env_written,
            "android_sdk": sdk_written,
            "verify_results": verify_results,
            "selected_packs": sorted(selected_pack_keys),
            "post_scaffold_notes": post_notes,
        }
    except SystemExit:
        # Cleanup on any fail_*() during the scaffold body. Only remove the
        # dest if this invocation created it — never touch a pre-existing dir
        # the user pointed --dest at (even with --force, a partial overlay
        # is less bad than destroying what was already there).
        if we_created_dest and not dry_run:
            shutil.rmtree(dest, ignore_errors=True)
            warn(f"cleaned up partially-scaffolded destination: {dest}")
        raise

    if dry_run:
        result["dry_run"] = True
        result["intended_destination"] = str(intended_dest)
        shutil.rmtree(dest, ignore_errors=True)
    return result


# ---------- argparse ----------

def add_scaffold_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("stack", choices=["kmp", "nextjs"])
    p.add_argument("name")
    p.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    p.add_argument("--cache-dir", default=None, help=f"default: {DEFAULT_CACHE}")
    p.add_argument("--package-prefix", default="com.example")
    p.add_argument("--bundle-prefix")
    p.add_argument("--auth-provider")
    p.add_argument("--theme-preset")
    p.add_argument("--room", action="store_true")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--no-auth", action="store_true")
    p.add_argument("--no-theme", action="store_true")
    p.add_argument("--pack", action="append", default=[])
    # Optional provider API keys. If omitted, falls back to the matching env
    # var (NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, CLERK_SECRET_KEY, NEXT_PUBLIC_SUPABASE_URL,
    # NEXT_PUBLIC_SUPABASE_ANON_KEY) — handy to avoid leaking secrets into shell
    # history. If neither flag nor env is set, the starter's graceful-no-keys
    # path activates and the user sees "configure <provider>" notices.
    p.add_argument("--clerk-publishable-key", default=None, help="NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY (also read from env)")
    p.add_argument("--clerk-secret-key",      default=None, help="CLERK_SECRET_KEY (also read from env)")
    p.add_argument("--supabase-url",          default=None, help="NEXT_PUBLIC_SUPABASE_URL (also read from env)")
    p.add_argument("--supabase-anon-key",     default=None, help="NEXT_PUBLIC_SUPABASE_ANON_KEY (also read from env)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deterministic project scaffolder (KMP + Next.js)")
    parser.add_argument("--version", action="version", version=f"scaffold.py {SCAFFOLD_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    resolve = sub.add_parser("resolve", help="Resolve a scaffold plan and print JSON")
    add_scaffold_args(resolve)
    resolve.add_argument("--dest")

    apply = sub.add_parser("apply", help="Apply a saved plan JSON to a destination")
    apply.add_argument("--plan", required=True, help="Path to a plan JSON file or '-' for stdin")
    apply.add_argument("--dest", required=True)
    apply.add_argument("--force", action="store_true")
    apply.add_argument("--skip-verify", action="store_true")
    apply.add_argument("--refresh-cache", action="store_true")
    apply.add_argument("--dry-run", action="store_true",
                       help="Preview changes in a tempdir; do not touch --dest. Implies --skip-verify.")

    create = sub.add_parser("create", help="Resolve and apply in one pass")
    add_scaffold_args(create)
    create.add_argument("--dest", required=True)
    create.add_argument("--force", action="store_true")
    create.add_argument("--skip-verify", action="store_true")
    create.add_argument("--refresh-cache", action="store_true")
    create.add_argument("--plan-out", help="Optional path to write the resolved plan JSON")
    create.add_argument("--dry-run", action="store_true",
                        help="Preview changes in a tempdir; do not touch --dest. Implies --skip-verify.")

    return parser


def load_plan(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def print_next_steps(plan: dict[str, Any], result: dict[str, Any]) -> None:
    """Human-readable summary printed to stderr after a successful scaffold.

    stderr keeps the JSON on stdout clean for tooling that pipes it.
    """
    dest = result.get("destination", "")
    stack = plan.get("stack", "")
    name = plan.get("name", "")
    placeholders = plan.get("placeholder_map", {}) or {}
    lines: list[str] = ["", f"✓ Scaffolded {stack} project {name!r} at {dest}", ""]

    if stack == "nextjs":
        provider = placeholders.get("auth_provider", "clerk")
        has_clerk = bool(placeholders.get("clerk_publishable_key"))
        has_supa = bool(placeholders.get("supabase_url"))
        lines.append("Next steps:")
        step = 1
        if provider == "clerk" and not has_clerk:
            lines.append(f"  {step}. Add Clerk keys to .env.local to enable auth (or sign-in shows a 'configure' notice):")
            lines.append("       NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...")
            lines.append("       CLERK_SECRET_KEY=sk_test_...")
            lines.append("       Get them at https://dashboard.clerk.com")
            step += 1
        elif provider == "supabase" and not has_supa:
            lines.append(f"  {step}. Add Supabase keys to .env.local to enable auth (or sign-in shows a 'configure' notice):")
            lines.append("       NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co")
            lines.append("       NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...")
            lines.append("       Get them at https://supabase.com/dashboard")
            step += 1
        lines.append(f"  {step}. cd {dest} && pnpm dev")
        step += 1
        lines.append(f"  {step}. Push to GitHub (when ready):")
        lines.append(f"       cd {dest} && gh repo create {placeholders.get('project_slug', name.lower())} --source . --push --private")
    elif stack == "kmp":
        lines.append("Next steps:")
        lines.append(f"  1. cd {dest}")
        lines.append("  2. ./gradlew --no-daemon :composeApp:run     # Desktop (JVM)")
        lines.append("  3. ./gradlew --no-daemon :composeApp:assembleDebug   # Android APK")
        lines.append("  4. Open iosApp/ in Xcode for iOS")
        lines.append("  5. Push to GitHub (when ready):")
        lines.append(f"       cd {dest} && gh repo create {placeholders.get('project_slug', name.lower())} --source . --push --private")

    # Starter-owned post-scaffold notes. The starter's .scaffold.json declares
    # heading/footer + a per-pack wiring hint; we just render what's there. No
    # hardcoded pack names, no stack-specific strings in the scaffolder.
    notes = result.get("post_scaffold_notes") or {}
    per_pack = notes.get("per_pack") or []
    if per_pack:
        lines.append("")
        for h in notes.get("heading") or []:
            lines.append(h)
        for _key, note in per_pack:
            lines.append(note)
        for f in notes.get("footer") or []:
            lines.append(f)

    lines.append("")
    print("\n".join(lines), file=sys.stderr)


def print_dry_run_summary(plan: dict[str, Any], result: dict[str, Any]) -> None:
    """Short human summary printed after a --dry-run, to stderr."""
    dest = result.get("intended_destination", "")
    stack = plan.get("stack", "")
    name = plan.get("name", "")
    changed = result.get("changed_files", 0)
    renamed = result.get("renamed_paths", 0)
    removed = result.get("removed_packs") or []
    env_file = result.get("env_file")
    packs = result.get("selected_packs") or []
    lines = [
        "",
        f"[dry-run] would scaffold {stack} project {name!r} to {dest}",
        f"  {changed} files rewritten, {renamed} paths renamed",
        f"  selected packs: {', '.join(packs) if packs else '(none)'}",
        f"  removed (unselected): {len(removed)} path(s)",
    ]
    if env_file:
        lines.append(f"  would write env file: {env_file}")
    lines.append("  NO files were written. Re-run without --dry-run to apply.")
    lines.append("")
    print("\n".join(lines), file=sys.stderr)


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "resolve":
        plan = resolve_plan(args)
        # Redact secrets from stdout. Callers that need the real values should
        # use `create` (which writes .env.local) or `--plan-out` (which writes
        # to a user-specified file — that's an explicit opt-in to persist secrets).
        print(json.dumps(_redact_plan_for_stdout(plan), indent=2, sort_keys=True))
        return 0

    if args.command == "apply":
        plan = load_plan(args.plan)
        result = apply_plan(
            plan, Path(args.dest),
            force=args.force, skip_verify=args.skip_verify,
            refresh_cache=args.refresh_cache, dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        if not args.dry_run:
            print_next_steps(plan, result)
        else:
            print_dry_run_summary(plan, result)
        return 0

    if args.command == "create":
        plan = resolve_plan(args)
        if args.plan_out:
            Path(args.plan_out).expanduser().write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        result = apply_plan(
            plan, Path(args.dest),
            force=args.force, skip_verify=args.skip_verify,
            refresh_cache=args.refresh_cache, dry_run=args.dry_run,
        )
        # Redact secrets from stdout. `apply_plan` above already wrote them to
        # .env.local using the real values, and `--plan-out` (above) persisted
        # the unredacted plan for users who explicitly asked for it.
        print(json.dumps(
            {"plan": _redact_plan_for_stdout(plan), "result": result},
            indent=2, sort_keys=True,
        ))
        if not args.dry_run:
            print_next_steps(plan, result)
        else:
            print_dry_run_summary(plan, result)
        return 0

    fail_usage(f"unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
