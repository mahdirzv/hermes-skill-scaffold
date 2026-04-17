"""Tests for the 3-pass content rewrite + path relocation + drift detection."""
import pytest
import scaffold


def _write(p, content=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _manifest(pairs):
    """Build a .scaffold.json-like dict from [(find, replace_with), ...]."""
    return {"placeholders": [{"find": f, "replace_with": r} for f, r in pairs]}


def test_rewrites_file_contents(tmp_path):
    _write(tmp_path / "app.kt", "package {{pkg}}.foo")
    manifest = _manifest([("{{pkg}}", "{{package_name}}")])
    stats = scaffold.apply_starter_placeholders(tmp_path, manifest, {"package_name": "com.rzv.app"})
    assert stats["changed_files"] == 1
    assert (tmp_path / "app.kt").read_text() == "package com.rzv.app.foo"


def test_relocates_files_when_relpath_matches(tmp_path):
    _write(tmp_path / "src" / "com" / "example" / "foo" / "Bar.kt", "// content")
    manifest = _manifest([("com/example/foo", "{{pkg_path}}")])
    stats = scaffold.apply_starter_placeholders(
        tmp_path, manifest, {"pkg_path": "com/rzv/bar"}
    )
    assert stats["renamed_paths"] == 1
    assert (tmp_path / "src" / "com" / "rzv" / "bar" / "Bar.kt").exists()
    assert not (tmp_path / "src" / "com" / "example" / "foo" / "Bar.kt").exists()


def test_empty_directories_pruned_after_rename(tmp_path):
    _write(tmp_path / "com" / "example" / "Foo.kt", "x")
    manifest = _manifest([("com/example", "com/rzv")])
    scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    # The old nested path should be gone (rmdir pass 3 collapses empties).
    assert not (tmp_path / "com" / "example").exists()


def test_skips_dotgit_and_node_modules(tmp_path):
    """Files under SKIP_DIRS must not be rewritten."""
    _write(tmp_path / ".git" / "config", "placeholder_here")
    _write(tmp_path / "node_modules" / "pkg" / "index.js", "placeholder_here")
    _write(tmp_path / "src" / "file.ts", "placeholder_here")
    manifest = _manifest([("placeholder_here", "REPLACED")])
    scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert (tmp_path / ".git" / "config").read_text() == "placeholder_here"
    assert (tmp_path / "node_modules" / "pkg" / "index.js").read_text() == "placeholder_here"
    assert (tmp_path / "src" / "file.ts").read_text() == "REPLACED"


def test_binary_files_are_skipped_not_crashed(tmp_path):
    """Non-utf8 files must be silently skipped, not raise."""
    (tmp_path / "logo.bin").write_bytes(b"\xff\xfe\x00\x01not-text")
    _write(tmp_path / "file.txt", "FIND_ME")
    manifest = _manifest([("FIND_ME", "REPLACED")])
    stats = scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert stats["changed_files"] == 1
    # Binary file untouched
    assert (tmp_path / "logo.bin").read_bytes().startswith(b"\xff\xfe")


def test_longest_find_string_applied_first(tmp_path):
    """Overlapping finds: the longer one must win to avoid partial clobbering."""
    _write(tmp_path / "f.txt", "com.example.foo")
    manifest = _manifest([
        ("com.example", "SHORT"),
        ("com.example.foo", "LONG"),
    ])
    scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert (tmp_path / "f.txt").read_text() == "LONG"


def test_drift_detection_fails_when_all_finds_miss(tmp_path):
    _write(tmp_path / "f.txt", "unrelated content")
    manifest = _manifest([
        ("NEVER_APPEARS_A", "x"),
        ("NEVER_APPEARS_B", "y"),
    ])
    with pytest.raises(SystemExit):
        scaffold.apply_starter_placeholders(tmp_path, manifest, {})


def test_drift_warns_when_some_finds_miss(tmp_path, capsys):
    _write(tmp_path / "f.txt", "hit_me here")
    manifest = _manifest([
        ("hit_me", "x"),
        ("MISSING", "y"),
    ])
    scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    err = capsys.readouterr().err
    assert "MISSING" in err and "drifted" in err


def test_rename_collision_fails_loud(tmp_path):
    _write(tmp_path / "dir_a" / "file.txt", "a")
    _write(tmp_path / "dir_b" / "file.txt", "b")  # already exists at target
    # Rename dir_a → dir_b via a path-substring find
    manifest = _manifest([("dir_a", "dir_b")])
    with pytest.raises(SystemExit):
        scaffold.apply_starter_placeholders(tmp_path, manifest, {})


def test_match_counts_returned(tmp_path):
    _write(tmp_path / "a.txt", "X X X")
    _write(tmp_path / "b.txt", "X Y")
    manifest = _manifest([("X", "Z"), ("Y", "W")])
    stats = scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    # X appears 4 times across 2 files; Y once.
    assert stats["match_counts"]["X"] == 4
    assert stats["match_counts"]["Y"] == 1


def test_empty_placeholders_is_a_noop(tmp_path):
    _write(tmp_path / "a.txt", "hello")
    stats = scaffold.apply_starter_placeholders(tmp_path, {"placeholders": []}, {})
    assert stats == {"changed_files": 0, "renamed_paths": 0, "match_counts": {}}
    assert (tmp_path / "a.txt").read_text() == "hello"


def test_placeholder_replace_with_expands_values(tmp_path):
    _write(tmp_path / "a.txt", "{{TOK}}")
    manifest = _manifest([("{{TOK}}", "{{project_name}}")])
    scaffold.apply_starter_placeholders(tmp_path, manifest, {"project_name": "Acme"})
    assert (tmp_path / "a.txt").read_text() == "Acme"
