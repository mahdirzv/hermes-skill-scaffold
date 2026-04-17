"""--dry-run: apply_plan must compute all stats without touching --dest."""
import json
from pathlib import Path

import scaffold


def _fake_starter(root: Path) -> None:
    """Write a minimal 'starter' tree into root that scaffold.py can copy."""
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.kt").write_text("package PKG.sample", encoding="utf-8")
    (root / "README.md").write_text("# PKG-sample", encoding="utf-8")
    # .scaffold.json with a find/replace rule that will match on content
    (root / ".scaffold.json").write_text(json.dumps({
        "placeholders": [
            {"find": "PKG", "replace_with": "{{package_prefix}}"},
        ],
    }), encoding="utf-8")


def _fake_registry(starter_dir: Path, registry_path: Path) -> None:
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
                "source": str(starter_dir),  # absolute path — resolve_source_path accepts this
            }
        ],
    }), encoding="utf-8")


def _make_plan(registry_path: Path, dest: Path) -> dict:
    import argparse
    args = argparse.Namespace(
        stack="kmp",
        name="DryTest",
        registry=str(registry_path),
        cache_dir=None,
        package_prefix="com.example",
        bundle_prefix=None,
        auth_provider=None,
        theme_preset=None,
        clerk_publishable_key=None,
        clerk_secret_key=None,
        supabase_url=None,
        supabase_anon_key=None,
        no_auth=True,
        no_theme=True,
        room=False,
        ci=False,
        pack=[],
        dest=str(dest),
    )
    return scaffold.resolve_plan(args)


def test_dry_run_leaves_dest_untouched(tmp_path):
    starter = tmp_path / "starter"
    _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry)
    dest = tmp_path / "out"

    plan = _make_plan(registry, dest)
    result = scaffold.apply_plan(plan, dest, skip_verify=True, dry_run=True)

    # Stats populated as if the scaffold happened
    assert result["dry_run"] is True
    assert result["intended_destination"] == str(dest)
    assert result["destination"] is None
    assert result["changed_files"] >= 1  # at least app.kt rewritten
    # …but dest itself was never created
    assert not dest.exists()


def test_dry_run_skips_verify_even_without_skip_verify_flag(tmp_path):
    """dry_run=True forces skip_verify=True internally — the stats dict should
    reflect a zero-length verify_results list regardless of the plan's verify."""
    starter = tmp_path / "starter"
    _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry)
    # Mutate the fake registry to declare a verify command that would fail
    reg_data = json.loads(registry.read_text())
    reg_data["packs"][0]["verify"] = [["false"]]  # would exit non-zero if run
    registry.write_text(json.dumps(reg_data))

    dest = tmp_path / "out"
    plan = _make_plan(registry, dest)
    # Explicitly leave skip_verify=False — dry_run should still suppress it
    result = scaffold.apply_plan(plan, dest, skip_verify=False, dry_run=True)
    assert result["verify_results"] == []
    assert result["dry_run"] is True


def test_non_dry_run_writes_to_dest(tmp_path):
    """Sanity: without --dry-run, dest gets populated and no dry_run marker appears."""
    starter = tmp_path / "starter"
    _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry)
    dest = tmp_path / "out"

    plan = _make_plan(registry, dest)
    result = scaffold.apply_plan(plan, dest, skip_verify=True, dry_run=False)
    assert "dry_run" not in result
    assert result["destination"] == str(dest)
    assert (dest / "src" / "app.kt").read_text() == "package com.example.sample"
    assert not (dest / ".scaffold.json").exists()  # manifest cleaned up


def test_dry_run_tempdir_cleaned_up(tmp_path, monkeypatch):
    """After dry-run, the temp working directory must be deleted."""
    import tempfile
    created: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracking_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(path)
        return path

    monkeypatch.setattr(tempfile, "mkdtemp", tracking_mkdtemp)

    starter = tmp_path / "starter"
    _fake_starter(starter)
    registry = tmp_path / "references" / "registry.json"
    _fake_registry(starter, registry)
    dest = tmp_path / "out"

    plan = _make_plan(registry, dest)
    scaffold.apply_plan(plan, dest, skip_verify=True, dry_run=True)

    # At least one tempdir was requested; every one was removed.
    assert created, "expected apply_plan(dry_run=True) to request a tempdir"
    for path in created:
        assert not Path(path).exists(), f"tempdir leaked: {path}"
