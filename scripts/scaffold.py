#!/usr/bin/env python3
"""Deterministic project scaffolder for KMP and Next.js starters.

Resolves pinned starter repos declared in ~/.hermes/.../references/registry.json,
shallow-clones them to a local cache, copies them into $DEST, applies find/replace
rules declared in the starter's own .scaffold.json, and optionally prunes packs
the user did not request.

Usage:
  scaffold.py resolve <stack> <name> [flags]        # print JSON plan
  scaffold.py create  <stack> <name> --dest PATH    # resolve + apply + verify
  scaffold.py apply   --plan plan.json --dest PATH  # apply a saved plan

See references/command-grammar.md for the full flag list.
"""
from __future__ import annotations

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

SCAFFOLD_VERSION = "0.1.0"
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY = SCRIPT_DIR.parent / "references" / "registry.json"
DEFAULT_CACHE = Path.home() / ".cache" / "scaffold-factory"

KIND_ORDER = {"base": 0, "feature": 1, "infra": 2}
SKIP_DIRS = {
    ".git", ".gradle", ".idea", ".kotlin", ".next", ".run", ".sisyphus",
    ".swiftpm", "build", "coverage", "DerivedData", "dist", "node_modules",
    "xcuserdata", ".turbo",
}


# ---------- errors ----------

def fail(message: str, code: int = 1) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# ---------- identifiers ----------

def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug:
        fail(f"cannot slugify project name: {value!r}")
    return slug


def humanize(value: str) -> str:
    if re.search(r"[-_ ]", value):
        parts = [p for p in re.split(r"[-_ ]+", value.strip()) if p]
        return " ".join(p[:1].upper() + p[1:] for p in parts)
    return value.strip()


def compact_identifier(value: str) -> str:
    compact = re.sub(r"[^a-z0-9]+", "", value.lower())
    if not compact:
        fail(f"cannot build compact identifier from {value!r}")
    return compact


def build_identifiers(stack: str, name: str, package_prefix: str, bundle_prefix: str | None) -> dict[str, str]:
    slug = slugify(name)
    display = humanize(name)
    compact = compact_identifier(slug)
    package_name = f"{package_prefix}.{compact}"
    package_path = package_name.replace(".", "/")
    return {
        "stack": stack,
        "project_name": display,
        "project_slug": slug,
        "project_root_name": display.replace(" ", ""),
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
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # fall back to full clone + checkout for raw SHAs
        if tmp.exists():
            shutil.rmtree(tmp)
        cmd = ["git", "clone", url, str(tmp)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            fail(f"git clone failed for {url}: {proc.stderr.strip()}")
        co = subprocess.run(["git", "-C", str(tmp), "checkout", ref], capture_output=True, text=True)
        if co.returncode != 0:
            fail(f"git checkout {ref} failed: {co.stderr.strip()}")
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
            fail(f"source {raw!r} references env var ${env_var} which is not set")
        return Path(val).expanduser().resolve()

    p = Path(raw)
    if p.is_absolute():
        return p.expanduser().resolve()
    return (registry_base / raw).expanduser().resolve()


# ---------- registry ----------

def load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        fail(f"registry not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        fail("registry must be a JSON object")
    data.setdefault("packs", [])
    data.setdefault("stack_defaults", {})
    min_ver = data.get("min_scaffold_py_version")
    if min_ver and tuple(map(int, min_ver.split("."))) > tuple(map(int, SCAFFOLD_VERSION.split("."))):
        fail(f"registry requires scaffold.py >= {min_ver} but this is {SCAFFOLD_VERSION}")
    return data


def validate_entry(entry: dict[str, Any]) -> None:
    for field in ("id", "stack", "kind"):
        if field not in entry:
            fail(f"registry entry missing required field {field!r}: {entry}")
    if entry["kind"] not in KIND_ORDER:
        fail(f"entry {entry['id']!r} has invalid kind {entry['kind']!r}")


def index_registry(entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for e in entries:
        validate_entry(e)
        if e["id"] in idx:
            fail(f"duplicate registry id: {e['id']}")
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
    if args.github:
        ids.append(f"{args.stack}_github")
    ids.extend(args.pack or [])
    seen: set[str] = set()
    return [i for i in ids if not (i in seen or seen.add(i))]


def select_entries(indexed: dict[str, dict[str, Any]], stack: str, selected_ids: list[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    base_id = f"{stack}_base"
    if base_id not in indexed:
        fail(f"missing base entry: {base_id}")
    base = indexed[base_id]
    if base["stack"] != stack:
        fail(f"base entry {base_id} has mismatched stack {base['stack']!r}")

    rest: list[dict[str, Any]] = []
    for eid in selected_ids:
        if eid == base_id:
            continue
        if eid not in indexed:
            fail(f"unknown registry id: {eid}")
        e = indexed[eid]
        if e["stack"] != stack:
            fail(f"entry {eid!r} belongs to stack {e['stack']!r}, expected {stack!r}")
        rest.append(e)
    rest.sort(key=lambda e: (KIND_ORDER[e["kind"]], e["id"]))
    return base, rest


def validate_dependencies(indexed: dict[str, dict[str, Any]], entries: list[dict[str, Any]]) -> None:
    sel = {e["id"] for e in entries}
    for e in entries:
        for dep in e.get("requires", []):
            if dep not in sel:
                fail(f"entry {e['id']!r} requires {dep!r} but it was not selected")
        for con in e.get("conflicts_with", []):
            if con in sel:
                fail(f"entry {e['id']!r} conflicts with {con!r}")


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
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        fail(f"invalid .scaffold.json in {src}: {e}")


def apply_starter_placeholders(dest: Path, manifest: dict[str, Any], values: dict[str, str]) -> tuple[int, int]:
    """Rewrite file CONTENTS and relocate files whose POSIX relpath contains a find string.

    Rules declared by the starter's .scaffold.json:
      placeholders: [ { find: "...", replace_with: "{{...}}" }, ... ]

    The find string is matched on:
      (a) file contents — every text file under dest (except SKIP_DIRS)
      (b) POSIX relative path of each file (so multi-segment paths like
          `com/example/foo/Bar.kt` rename correctly to `com/rzv/bar/Bar.kt`).

    After relocation, empty parent dirs are pruned.
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
        return 0, 0

    def replace_all(text: str) -> str:
        for old, new in pairs:
            text = text.replace(old, new)
        return text

    # ---- Pass 1: rewrite file contents ----
    changed_files = 0
    for path in dest.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
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
    renamed_paths = 0
    relocations: list[tuple[Path, Path]] = []
    for path in dest.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        rel = path.relative_to(dest).as_posix()
        new_rel = replace_all(rel)
        if new_rel != rel:
            relocations.append((path, dest / new_rel))

    for src, tgt in relocations:
        if tgt.exists():
            fail(f"rename collision: {src} → {tgt}")
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

    return changed_files, renamed_paths


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
        "# Generated by scaffold.py — contains only the provider/theme selection.",
        f"# Copy additional keys from {spec.get('template', '.env.example')} once you have real values.",
        "",
    ]
    for k, v in overrides.items():
        lines.append(f"{k}={v}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out.relative_to(dest))


# ---------- copy ----------

def ignore_fn(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in SKIP_DIRS or n == ".DS_Store"}


def copy_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        fail(f"source path does not exist: {src}")
    if not src.is_dir():
        fail(f"source path is not a directory: {src}")
    shutil.copytree(src, dest, dirs_exist_ok=True, ignore=ignore_fn)


# ---------- verification ----------

def run_verify(commands: list[str | list[str]], cwd: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for cmd in commands:
        if isinstance(cmd, list):
            display = " ".join(cmd)
            proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
        else:
            display = cmd
            proc = subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True)
        print(f"$ {display}")
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        results.append({"command": display, "returncode": proc.returncode})
        if proc.returncode != 0:
            fail(f"verification command failed: {display}")
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


def apply_plan(plan: dict[str, Any], dest: Path, *, force: bool = False, skip_verify: bool = False, refresh_cache: bool = False) -> dict[str, Any]:
    dest = dest.expanduser()
    if dest.exists() and any(dest.iterdir()) and not force:
        fail(f"destination already exists and is not empty: {dest}")
    dest.mkdir(parents=True, exist_ok=True)

    registry_base = Path(plan["_registry_path"]).parent
    if registry_base.name == "references":
        registry_base = registry_base.parent
    cache_dir = Path(plan.get("_cache_dir") or DEFAULT_CACHE)

    base = plan["base"]
    # Pre-flight: resolve base source and check it exists BEFORE copying anything
    base_source = resolve_source_path(base["source"], registry_base, cache_dir, refresh=refresh_cache)
    if not base_source.exists():
        fail(f"base source missing after resolve: {base_source}")

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
    changed_files, renamed_paths = apply_starter_placeholders(dest, manifest, plan["placeholder_map"]) if manifest else (0, 0)

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

    return {
        "destination": str(dest),
        "changed_files": changed_files,
        "renamed_paths": renamed_paths,
        "removed_packs": removed,
        "env_file": env_written,
        "android_sdk": sdk_written,
        "verify_results": verify_results,
        "selected_packs": sorted(selected_pack_keys),
    }


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
    p.add_argument("--github", action="store_true")
    p.add_argument("--ci", action="store_true")
    p.add_argument("--no-auth", action="store_true")
    p.add_argument("--no-theme", action="store_true")
    p.add_argument("--pack", action="append", default=[])


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

    create = sub.add_parser("create", help="Resolve and apply in one pass")
    add_scaffold_args(create)
    create.add_argument("--dest", required=True)
    create.add_argument("--force", action="store_true")
    create.add_argument("--skip-verify", action="store_true")
    create.add_argument("--refresh-cache", action="store_true")
    create.add_argument("--plan-out", help="Optional path to write the resolved plan JSON")

    return parser


def load_plan(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    args = build_parser().parse_args()

    if args.command == "resolve":
        plan = resolve_plan(args)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    if args.command == "apply":
        plan = load_plan(args.plan)
        result = apply_plan(plan, Path(args.dest), force=args.force, skip_verify=args.skip_verify, refresh_cache=args.refresh_cache)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.command == "create":
        plan = resolve_plan(args)
        if args.plan_out:
            Path(args.plan_out).expanduser().write_text(json.dumps(plan, indent=2, sort_keys=True), encoding="utf-8")
        result = apply_plan(plan, Path(args.dest), force=args.force, skip_verify=args.skip_verify, refresh_cache=args.refresh_cache)
        print(json.dumps({"plan": plan, "result": result}, indent=2, sort_keys=True))
        return 0

    fail(f"unsupported command: {args.command}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
