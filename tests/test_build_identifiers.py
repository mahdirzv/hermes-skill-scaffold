import pytest
import scaffold


def test_identifiers_basic_kmp():
    ids = scaffold.build_identifiers("kmp", "My Cool App", "com.example", None)
    assert ids["stack"] == "kmp"
    assert ids["project_name"] == "My Cool App"
    assert ids["project_slug"] == "my-cool-app"
    assert ids["project_root_name"] == "MyCoolApp"
    assert ids["package_name"] == "com.example.mycoolapp"
    assert ids["package_path"] == "com/example/mycoolapp"
    assert ids["package_prefix"] == "com.example"
    assert ids["bundle_id"] == "com.example.mycoolapp"
    assert ids["bundle_prefix"] == "com.example"  # falls back to package_prefix
    assert ids["repo_name"] == "my-cool-app"
    assert ids["folder_name"] == "my-cool-app"


def test_bundle_prefix_distinct_from_package_prefix():
    ids = scaffold.build_identifiers("nextjs", "App", "com.example", "io.different")
    assert ids["package_name"] == "com.example.app"
    assert ids["bundle_id"] == "io.different.app"
    assert ids["bundle_prefix"] == "io.different"


def test_name_with_only_punctuation_fails_on_slug():
    # slugify trips first — that's fine, an error gets raised either way.
    with pytest.raises(SystemExit):
        scaffold.build_identifiers("kmp", "!!!", "com.example", None)


def test_name_that_sanitizes_to_empty_root_name_fails():
    # Single underscore: slugify succeeds (yields non-empty slug via digit/letter path?)
    # Use a pathological name — all characters stripped from both slug and root_name.
    with pytest.raises(SystemExit):
        scaffold.build_identifiers("kmp", "   ---   ", "com.example", None)


def test_invalid_package_prefix_rejected():
    with pytest.raises(SystemExit):
        scaffold.build_identifiers("kmp", "App", "Com.Example", None)


def test_invalid_bundle_prefix_rejected():
    with pytest.raises(SystemExit):
        scaffold.build_identifiers("kmp", "App", "com.example", "bad-bundle")


def test_name_retains_digits_in_compact():
    ids = scaffold.build_identifiers("kmp", "App2 Pro", "com.example", None)
    assert ids["project_slug"] == "app2-pro"
    assert ids["package_name"] == "com.example.app2pro"
    assert ids["project_root_name"] == "App2Pro"


def test_slugify_lowercases_and_collapses():
    assert scaffold.slugify("  My   App  ") == "my-app"
    assert scaffold.slugify("A---B") == "a-b"


def test_humanize_preserves_single_word():
    assert scaffold.humanize("Acme") == "Acme"


def test_humanize_title_cases_multiword():
    assert scaffold.humanize("my-cool-app") == "My Cool App"
    assert scaffold.humanize("my_cool_app") == "My Cool App"
