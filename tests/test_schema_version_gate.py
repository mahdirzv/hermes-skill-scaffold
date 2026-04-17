"""Starter-manifest schema version gate — rejects unknown .scaffold.json versions.

Guards against silent misbehavior when a v2 schema ships with new field
semantics. Before this gate, scaffold.py would happily parse v2 as if it were
v1 and produce cryptic downstream errors.
"""
import json
from pathlib import Path

import pytest
import scaffold


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_missing_schema_version_defaults_to_v1(tmp_path):
    """Starters predating the gate have no version field; assume v1 for compat."""
    _write(tmp_path / ".scaffold.json", json.dumps({"stack": "nextjs", "placeholders": []}))
    manifest = scaffold.read_starter_manifest(tmp_path)
    assert manifest["stack"] == "nextjs"


def test_explicit_v1_accepted(tmp_path):
    _write(tmp_path / ".scaffold.json", json.dumps({"scaffold_schema_version": "1", "stack": "kmp"}))
    manifest = scaffold.read_starter_manifest(tmp_path)
    assert manifest["scaffold_schema_version"] == "1"


def test_unknown_schema_version_rejected(tmp_path):
    _write(tmp_path / ".scaffold.json", json.dumps({"scaffold_schema_version": "2", "stack": "nextjs"}))
    with pytest.raises(SystemExit) as exc:
        scaffold.read_starter_manifest(tmp_path)
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_STARTER


def test_numeric_schema_version_rejected(tmp_path):
    """Integer `2` is coerced to `"2"` and still rejected."""
    _write(tmp_path / ".scaffold.json", json.dumps({"scaffold_schema_version": 2, "stack": "nextjs"}))
    with pytest.raises(SystemExit) as exc:
        scaffold.read_starter_manifest(tmp_path)
    code = exc.value.code if isinstance(exc.value.code, int) else 1
    assert code == scaffold.EXIT_STARTER


def test_missing_manifest_returns_empty(tmp_path):
    """No .scaffold.json at all — scaffold.py uses registry placeholders only."""
    assert scaffold.read_starter_manifest(tmp_path) == {}


def test_supported_versions_is_set():
    """Guard against accidental deletion of the constant."""
    assert isinstance(scaffold.SUPPORTED_SCAFFOLD_SCHEMA_VERSIONS, frozenset)
    assert "1" in scaffold.SUPPORTED_SCAFFOLD_SCHEMA_VERSIONS
