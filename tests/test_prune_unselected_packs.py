import scaffold


def _write(p, content=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test_deletes_paths_of_unselected_packs(tmp_path):
    # Layout: two packs; select only 'auth'. 'room' dirs/files should vanish.
    _write(tmp_path / "kmp" / "auth" / "keep.txt", "keep")
    _write(tmp_path / "kmp" / "room_data" / "drop.txt", "drop")
    _write(tmp_path / "README.md", "hi")

    manifest = {
        "packs": {
            "auth":      {"paths": ["kmp/auth"]},
            "room_data": {"paths": ["kmp/room_data"]},
        },
    }

    removed = scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys={"auth"})
    assert "kmp/room_data" in removed
    assert not (tmp_path / "kmp" / "room_data").exists()
    assert (tmp_path / "kmp" / "auth" / "keep.txt").exists()


def test_selected_pack_files_are_preserved(tmp_path):
    _write(tmp_path / "kmp" / "auth" / "a.kt", "a")
    manifest = {"packs": {"auth": {"paths": ["kmp/auth"]}}}
    removed = scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys={"auth"})
    assert removed == []
    assert (tmp_path / "kmp" / "auth" / "a.kt").exists()


def test_missing_pack_paths_are_silently_skipped(tmp_path):
    # No 'kmp/room_data' on disk, but pack declares it — do not crash.
    _write(tmp_path / "kmp" / "auth" / "a.kt", "a")
    manifest = {
        "packs": {
            "auth":      {"paths": ["kmp/auth"]},
            "room_data": {"paths": ["kmp/room_data"]},  # absent on disk
        },
    }
    removed = scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys={"auth"})
    assert removed == []


def test_strips_settings_gradle_include_line_for_unselected(tmp_path):
    settings = tmp_path / "settings.gradle.kts"
    settings.write_text(
        'rootProject.name = "foo"\n'
        'include(":composeApp")\n'
        'include(":kmp:auth")\n'
        'include(":kmp:room_data")\n',
        encoding="utf-8",
    )
    manifest = {
        "packs": {
            "auth":      {"settings_gradle_include_line": 'include(":kmp:auth")'},
            "room_data": {"settings_gradle_include_line": 'include(":kmp:room_data")'},
        },
    }

    removed = scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys={"auth"})
    content = settings.read_text()
    assert 'include(":kmp:auth")' in content
    assert 'include(":kmp:room_data")' not in content
    assert any("room_data" in r for r in removed)
    # File ends with newline
    assert content.endswith("\n")


def test_include_line_stripping_tolerates_surrounding_whitespace(tmp_path):
    settings = tmp_path / "settings.gradle.kts"
    settings.write_text('  include(":kmp:room_data")  \n', encoding="utf-8")
    manifest = {
        "packs": {
            "room_data": {"settings_gradle_include_line": 'include(":kmp:room_data")'},
        },
    }
    scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys=set())
    assert 'include(":kmp:room_data")' not in settings.read_text()


def test_deletes_single_files_not_just_dirs(tmp_path):
    _write(tmp_path / "experimental.kt", "x")
    manifest = {"packs": {"exp": {"paths": ["experimental.kt"]}}}
    removed = scaffold.prune_unselected_packs(tmp_path, manifest, selected_pack_keys=set())
    assert "experimental.kt" in removed
    assert not (tmp_path / "experimental.kt").exists()


def test_empty_manifest_is_a_noop(tmp_path):
    _write(tmp_path / "a.txt", "a")
    removed = scaffold.prune_unselected_packs(tmp_path, {}, selected_pack_keys=set())
    assert removed == []
    assert (tmp_path / "a.txt").exists()
