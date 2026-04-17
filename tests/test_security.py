"""Security regression tests — secret leakage, path traversal, symlink-through-write.

These guard against three classes of bug that all share the pattern "scaffold.py
acts on untrusted strings from CLI flags / starter manifests and could
compromise the user's filesystem or secrets if the trust boundary leaked."
"""
import os
from pathlib import Path

import pytest

import scaffold


# ────────────────────────────────────────────────────────────────
# Secret redaction in stdout JSON
# ────────────────────────────────────────────────────────────────

def test_redact_masks_all_four_secret_placeholders():
    plan = {
        "stack": "nextjs",
        "placeholder_map": {
            "project_slug": "my-app",
            "clerk_publishable_key": "pk_live_XXXXXXXXXXXX",
            "clerk_secret_key":      "sk_live_XXXXXXXXXXXX",
            "supabase_url":          "https://real.supabase.co",
            "supabase_anon_key":     "eyJ_real_token_here",
        },
    }
    out = scaffold._redact_plan_for_stdout(plan)
    pm = out["placeholder_map"]
    assert pm["project_slug"] == "my-app"   # non-secret preserved
    assert pm["clerk_publishable_key"] == "[REDACTED]"
    assert pm["clerk_secret_key"]      == "[REDACTED]"
    assert pm["supabase_url"]          == "[REDACTED]"
    assert pm["supabase_anon_key"]     == "[REDACTED]"


def test_redact_does_not_mutate_original_plan():
    """The in-memory plan must keep real values — only the copy is redacted."""
    plan = {"placeholder_map": {"clerk_secret_key": "sk_live_KEEP"}}
    scaffold._redact_plan_for_stdout(plan)
    assert plan["placeholder_map"]["clerk_secret_key"] == "sk_live_KEEP"


def test_redact_preserves_empty_values():
    """Empty secrets stay empty (not replaced with [REDACTED]) — no false positive."""
    plan = {"placeholder_map": {"clerk_secret_key": ""}}
    out = scaffold._redact_plan_for_stdout(plan)
    assert out["placeholder_map"]["clerk_secret_key"] == ""


def test_redact_no_placeholder_map_is_noop():
    plan = {"stack": "nextjs", "name": "MyApp"}
    assert scaffold._redact_plan_for_stdout(plan) == plan


def test_redact_covers_every_flag_in_table():
    """Regression guard: _REDACT_PLACEHOLDER_KEYS must match _SECRET_FLAG_TABLE."""
    expected = {row[1] for row in scaffold._SECRET_FLAG_TABLE}
    assert scaffold._REDACT_PLACEHOLDER_KEYS == frozenset(expected)


# ────────────────────────────────────────────────────────────────
# Path traversal in apply_starter_placeholders
# ────────────────────────────────────────────────────────────────

def _write(p: Path, content: str = "") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_path_traversal_via_parent_segment_rejected(tmp_path):
    """A malicious manifest that expands to `../` in a path is rejected."""
    _write(tmp_path / "src" / "foo.txt", "ok")
    # This placeholder would rename `src/foo.txt` → `../outside/foo.txt`
    manifest = {"placeholders": [{"find": "src", "replace_with": "../outside"}]}
    with pytest.raises(SystemExit) as exc:
        scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_STARTER


def test_placeholder_expansion_containing_dotdot_rejected(tmp_path):
    """Even when the `find` is benign, if the expanded `replace_with` produces `..`,
    reject it. Guards against the replace_with template containing a placeholder
    whose computed value would traverse."""
    _write(tmp_path / "src" / "bar.kt", "x")
    manifest = {"placeholders": [{"find": "src", "replace_with": "{{traverse}}"}]}
    with pytest.raises(SystemExit) as exc:
        scaffold.apply_starter_placeholders(tmp_path, manifest, {"traverse": "../../etc"})
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_STARTER


def test_benign_rename_still_works(tmp_path):
    """Sanity: the path guard doesn't break legitimate renames."""
    _write(tmp_path / "com" / "example" / "foo" / "Bar.kt", "x")
    manifest = {"placeholders": [{"find": "com/example/foo", "replace_with": "com/rzv/bar"}]}
    stats = scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert stats["renamed_paths"] == 1
    assert (tmp_path / "com" / "rzv" / "bar" / "Bar.kt").exists()


# ────────────────────────────────────────────────────────────────
# Symlink-through-write prevention
# ────────────────────────────────────────────────────────────────

@pytest.mark.skipif(os.name == "nt", reason="symlinks require elevated privs on Windows")
def test_symlinks_skipped_in_content_rewrite(tmp_path):
    """A tracked symlink pointing outside dest must NOT be written through
    during the content-rewrite pass."""
    # Create a target OUTSIDE dest that we'll assert stays unmodified
    outside = tmp_path.parent / "outside-sentinel.txt"
    outside.write_text("ORIGINAL", encoding="utf-8")
    try:
        # Scaffold dest with a symlink that would otherwise be rewritten
        dest = tmp_path / "scaf"
        dest.mkdir()
        (dest / "link").symlink_to(outside)
        (dest / "normal.txt").write_text("ORIGINAL", encoding="utf-8")

        manifest = {"placeholders": [{"find": "ORIGINAL", "replace_with": "REWRITTEN"}]}
        scaffold.apply_starter_placeholders(dest, manifest, {})

        # Normal file got rewritten; symlinked-outside target did NOT
        assert (dest / "normal.txt").read_text() == "REWRITTEN"
        assert outside.read_text() == "ORIGINAL"
    finally:
        if outside.exists():
            outside.unlink()


@pytest.mark.skipif(os.name == "nt", reason="symlinks require elevated privs on Windows")
def test_symlinks_skipped_in_rename_pass(tmp_path):
    """A symlink whose relative path matches a find-string must NOT be renamed.

    We include a sibling regular file also matching the find-string so drift
    detection (which aborts if ALL finds miss) has something to bite on —
    proving the symlink is specifically the path being skipped.
    """
    dest = tmp_path / "scaf"
    dest.mkdir()
    target = dest / "target.txt"
    target.write_text("hi", encoding="utf-8")
    (dest / "linkname-L").symlink_to(target)   # symlink that matches the find
    # Real file that also matches the find — keeps drift-detection happy
    (dest / "linkname-F").write_text("ok", encoding="utf-8")

    manifest = {"placeholders": [{"find": "linkname", "replace_with": "renamed"}]}
    scaffold.apply_starter_placeholders(dest, manifest, {})

    # Real file was renamed
    assert (dest / "renamed-F").exists()
    assert not (dest / "linkname-F").exists()
    # Symlink was NOT renamed (skipped by is_symlink guard)
    assert (dest / "linkname-L").is_symlink()
    assert not (dest / "renamed-L").exists()
