"""Exit-code taxonomy: USAGE=2, SYSTEM=3, NETWORK=4, STARTER=5."""
import pytest
import scaffold


def _code_of(exc: pytest.ExceptionInfo) -> int:
    """SystemExit.code can be int, None, or str; normalize to int."""
    code = exc.value.code
    return code if isinstance(code, int) else 1


def test_exit_code_constants():
    assert scaffold.EXIT_USAGE   == 2
    assert scaffold.EXIT_SYSTEM  == 3
    assert scaffold.EXIT_NETWORK == 4
    assert scaffold.EXIT_STARTER == 5


def test_fail_usage_emits_code_2():
    with pytest.raises(SystemExit) as exc:
        scaffold.fail_usage("bad flag")
    assert _code_of(exc) == 2


def test_fail_system_emits_code_3():
    with pytest.raises(SystemExit) as exc:
        scaffold.fail_system("disk full")
    assert _code_of(exc) == 3


def test_fail_network_emits_code_4():
    with pytest.raises(SystemExit) as exc:
        scaffold.fail_network("git clone failed")
    assert _code_of(exc) == 4


def test_fail_starter_emits_code_5():
    with pytest.raises(SystemExit) as exc:
        scaffold.fail_starter("registry malformed")
    assert _code_of(exc) == 5


def test_legacy_fail_defaults_to_generic():
    with pytest.raises(SystemExit) as exc:
        scaffold.fail("uncategorized")
    assert _code_of(exc) == 1


# ── Classification: probe representative call sites to confirm the right code fires ──

def test_invalid_package_prefix_is_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        scaffold.validate_package_prefix("Bad-Prefix")
    assert _code_of(exc) == scaffold.EXIT_USAGE


def test_slugify_empty_is_usage():
    with pytest.raises(SystemExit) as exc:
        scaffold.slugify("!!!")
    assert _code_of(exc) == scaffold.EXIT_USAGE


def test_source_path_missing_is_system(tmp_path):
    with pytest.raises(SystemExit) as exc:
        scaffold.copy_tree(tmp_path / "does_not_exist", tmp_path / "d")
    assert _code_of(exc) == scaffold.EXIT_SYSTEM


def test_missing_registry_is_starter(tmp_path):
    with pytest.raises(SystemExit) as exc:
        scaffold.load_registry(tmp_path / "no.json")
    assert _code_of(exc) == scaffold.EXIT_STARTER


def test_duplicate_registry_id_is_starter():
    with pytest.raises(SystemExit) as exc:
        scaffold.index_registry([
            {"id": "a", "stack": "kmp", "kind": "base"},
            {"id": "a", "stack": "kmp", "kind": "feature"},
        ])
    assert _code_of(exc) == scaffold.EXIT_STARTER


def test_rename_collision_is_starter(tmp_path):
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_a" / "f.txt").write_text("a")
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_b" / "f.txt").write_text("b")
    manifest = {"placeholders": [{"find": "dir_a", "replace_with": "dir_b"}]}
    with pytest.raises(SystemExit) as exc:
        scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert _code_of(exc) == scaffold.EXIT_STARTER


def test_placeholder_drift_is_starter(tmp_path):
    (tmp_path / "f.txt").write_text("nothing here")
    manifest = {"placeholders": [{"find": "NEVER", "replace_with": "x"}]}
    with pytest.raises(SystemExit) as exc:
        scaffold.apply_starter_placeholders(tmp_path, manifest, {})
    assert _code_of(exc) == scaffold.EXIT_STARTER
