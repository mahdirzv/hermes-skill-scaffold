"""remove_on_scaffold + generate_readme — starter-identity file handling.

Before v0.4.10, `scaffold.py` copied the starter tree verbatim, which meant
LICENSE (attribution to starter author), README.md ("Base Next.js Starter"),
and SECURITY.md (pointing at the starter maintainer) ended up in every
scaffolded project. These manifest keys let starters declare identity files
to remove, plus an optional templated README for the consumer.
"""
from pathlib import Path

import pytest
import scaffold


def _write(p: Path, content: str = "") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ─────────────────────────── remove_on_scaffold ───────────────────────────

def test_removes_listed_files(tmp_path):
    _write(tmp_path / "LICENSE", "MIT © starter-author")
    _write(tmp_path / "README.md", "# Base Starter")
    _write(tmp_path / "SECURITY.md", "# Security Policy")
    _write(tmp_path / "keep.txt", "keep me")

    removed = scaffold.apply_remove_on_scaffold(tmp_path, {
        "remove_on_scaffold": ["LICENSE", "README.md", "SECURITY.md"]
    })

    assert sorted(removed) == ["LICENSE", "README.md", "SECURITY.md"]
    assert not (tmp_path / "LICENSE").exists()
    assert not (tmp_path / "README.md").exists()
    assert not (tmp_path / "SECURITY.md").exists()
    assert (tmp_path / "keep.txt").exists()


def test_missing_paths_silently_skipped(tmp_path):
    """Starter can declare files that may or may not exist (e.g. optional docs)."""
    _write(tmp_path / "LICENSE", "x")
    removed = scaffold.apply_remove_on_scaffold(tmp_path, {
        "remove_on_scaffold": ["LICENSE", "DOES_NOT_EXIST.md", "other-missing"]
    })
    assert removed == ["LICENSE"]


def test_removes_directories(tmp_path):
    (tmp_path / "examples").mkdir()
    _write(tmp_path / "examples" / "demo.txt", "x")
    removed = scaffold.apply_remove_on_scaffold(tmp_path, {
        "remove_on_scaffold": ["examples"]
    })
    assert removed == ["examples"]
    assert not (tmp_path / "examples").exists()


def test_no_key_is_noop(tmp_path):
    _write(tmp_path / "LICENSE", "x")
    removed = scaffold.apply_remove_on_scaffold(tmp_path, {})
    assert removed == []
    assert (tmp_path / "LICENSE").exists()


def test_empty_list_is_noop(tmp_path):
    _write(tmp_path / "LICENSE", "x")
    removed = scaffold.apply_remove_on_scaffold(tmp_path, {"remove_on_scaffold": []})
    assert removed == []
    assert (tmp_path / "LICENSE").exists()


def test_parent_traversal_rejected(tmp_path):
    """Path-traversal guard (same policy as placeholder rename pass)."""
    sentinel = tmp_path.parent / "outside-of-dest.txt"
    sentinel.write_text("keep", encoding="utf-8")
    try:
        # dest doesn't need the file for the check to fire
        with pytest.raises(SystemExit) as exc:
            scaffold.apply_remove_on_scaffold(tmp_path, {
                "remove_on_scaffold": ["../outside-of-dest.txt"]
            })
        code = exc.value.code if isinstance(exc.value.code, int) else 1
        assert code == scaffold.EXIT_STARTER
        assert sentinel.exists()  # guard worked
    finally:
        if sentinel.exists():
            sentinel.unlink()


# ─────────────────────────── generate_readme ───────────────────────────

def test_string_form_writes_readme(tmp_path):
    written = scaffold.apply_readme_template(
        tmp_path,
        {"generate_readme": "# {{project_name}}\n\nHello."},
        {"project_name": "My App"},
    )
    assert written == "README.md"
    assert (tmp_path / "README.md").read_text() == "# My App\n\nHello."


def test_object_form_with_custom_output(tmp_path):
    written = scaffold.apply_readme_template(
        tmp_path,
        {"generate_readme": {"output": "docs/intro.md", "content": "# {{project_slug}}"}},
        {"project_slug": "my-app"},
    )
    assert written == "docs/intro.md"
    assert (tmp_path / "docs" / "intro.md").read_text() == "# my-app"


def test_no_key_returns_none(tmp_path):
    assert scaffold.apply_readme_template(tmp_path, {}, {}) is None
    assert not (tmp_path / "README.md").exists()


def test_empty_content_returns_none(tmp_path):
    assert scaffold.apply_readme_template(tmp_path, {"generate_readme": ""}, {}) is None
    assert not (tmp_path / "README.md").exists()


def test_placeholder_expansion_applies(tmp_path):
    """Multiple placeholders in the template all expand."""
    scaffold.apply_readme_template(
        tmp_path,
        {"generate_readme": "# {{project_name}}\nSlug: {{project_slug}}\nPkg: {{package_name}}"},
        {
            "project_name": "Epr Validator",
            "project_slug": "epr-validator",
            "package_name": "com.example.eprvalidator",
        },
    )
    body = (tmp_path / "README.md").read_text()
    assert "# Epr Validator" in body
    assert "epr-validator" in body
    assert "com.example.eprvalidator" in body


def test_readme_output_traversal_rejected(tmp_path):
    with pytest.raises(SystemExit) as exc:
        scaffold.apply_readme_template(
            tmp_path,
            {"generate_readme": {"output": "../outside.md", "content": "x"}},
            {},
        )
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_STARTER


# ─────────────────────── remove + generate integration ───────────────────────

def test_remove_then_generate_replaces_starter_readme(tmp_path):
    """The common case: starter ships its own README, we remove it and
    generate a project-specific one."""
    _write(tmp_path / "README.md", "# Base Next.js Starter\n\nThis is about the starter.")
    manifest = {
        "remove_on_scaffold": ["README.md"],
        "generate_readme": "# {{project_name}}\n\nYour project.",
    }
    removed = scaffold.apply_remove_on_scaffold(tmp_path, manifest)
    written = scaffold.apply_readme_template(tmp_path, manifest, {"project_name": "EPR"})
    assert "README.md" in removed
    assert written == "README.md"
    assert (tmp_path / "README.md").read_text() == "# EPR\n\nYour project."
