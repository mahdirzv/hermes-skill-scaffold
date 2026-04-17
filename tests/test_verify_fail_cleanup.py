"""Verify-fail cleanup — partial scaffolds are removed if we created the dest.

Before this fix, `pnpm build` failing during `run_verify` left a fully-copied,
partially-configured project on disk. The next `scaffold.py create` run then
hit "destination already exists and is not empty" until the user manually
deleted the dir.
"""
import json
from pathlib import Path

import pytest
import scaffold


def _fake_starter(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.kt").write_text("package PKG.sample", encoding="utf-8")
    (root / ".scaffold.json").write_text(json.dumps({
        "scaffold_schema_version": "1",
        "stack": "kmp",
        "placeholders": [
            {"find": "PKG", "replace_with": "{{package_prefix}}"},
        ],
    }), encoding="utf-8")


def _fake_registry(starter_dir: Path, registry_path: Path, verify_cmd: list) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps({
        "version": "test",
        "min_scaffold_py_version": "0.1.0",
        "stack_defaults": {"kmp": {}},
        "packs": [
            {
                "id": "kmp_base",
                "stack": "kmp",
                "kind": "base",
                "source": str(starter_dir),
                "verify": [verify_cmd],
            }
        ],
    }), encoding="utf-8")


def _make_plan(registry_path: Path, dest: Path) -> dict:
    import argparse
    args = argparse.Namespace(
        stack="kmp", name="FailTest",
        registry=str(registry_path), cache_dir=None,
        package_prefix="com.example", bundle_prefix=None,
        auth_provider=None, theme_preset=None,
        clerk_publishable_key=None, clerk_secret_key=None,
        supabase_url=None, supabase_anon_key=None,
        no_auth=True, no_theme=True, room=False, ci=False,
        pack=[], dest=str(dest),
    )
    return scaffold.resolve_plan(args)


def test_verify_failure_removes_dest_we_created(tmp_path):
    starter = tmp_path / "starter"; _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry, ["false"])  # always exits non-zero
    dest = tmp_path / "newdest"
    plan = _make_plan(registry, dest)

    with pytest.raises(SystemExit) as exc:
        scaffold.apply_plan(plan, dest, skip_verify=False)
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_SYSTEM  # verify failure maps to SYSTEM

    # The dest we created must be gone so a retry doesn't hit "not empty"
    assert not dest.exists(), f"dest leaked: {dest} still exists after verify-fail"


def test_verify_failure_preserves_preexisting_dest(tmp_path):
    """If the user pointed --dest at an existing dir (with --force), never rm it."""
    starter = tmp_path / "starter"; _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry, ["false"])
    dest = tmp_path / "preexists"
    dest.mkdir()
    sentinel = dest / "USER_FILE.txt"
    sentinel.write_text("important", encoding="utf-8")
    plan = _make_plan(registry, dest)

    with pytest.raises(SystemExit):
        scaffold.apply_plan(plan, dest, force=True, skip_verify=False)

    # Pre-existing dest is preserved. User's sentinel still there; scaffold's
    # partial output might still be present (that's the --force contract).
    assert dest.exists()
    assert sentinel.exists()
    assert sentinel.read_text() == "important"


def test_successful_scaffold_leaves_dest(tmp_path):
    """Sanity: successful scaffolds don't trigger cleanup."""
    starter = tmp_path / "starter"; _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry, ["true"])  # exit 0
    dest = tmp_path / "ok"
    plan = _make_plan(registry, dest)

    result = scaffold.apply_plan(plan, dest, skip_verify=False)
    assert dest.exists()
    assert (dest / "src" / "app.kt").exists()
    assert result["destination"] == str(dest)
