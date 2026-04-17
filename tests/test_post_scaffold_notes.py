"""Data-driven post-scaffold notes: starter-owned wiring hints via .scaffold.json."""
import scaffold


def test_empty_manifest_returns_empty():
    assert scaffold.collect_post_scaffold_notes({}, set()) == {}


def test_no_selected_packs_returns_empty():
    manifest = {
        "packs": {"auth": {"post_scaffold_note": "wire it"}},
        "post_scaffold_notes": {"heading": ["hi"]},
    }
    assert scaffold.collect_post_scaffold_notes(manifest, set()) == {}


def test_selected_pack_without_note_returns_empty():
    """A pack the user kept but which has no note → no section rendered."""
    manifest = {
        "packs": {"ci": {"paths": [".github"]}},  # no post_scaffold_note
        "post_scaffold_notes": {"heading": ["hi"]},
    }
    assert scaffold.collect_post_scaffold_notes(manifest, {"ci"}) == {}


def test_collects_heading_and_per_pack_note():
    manifest = {
        "packs": {
            "auth": {"post_scaffold_note": "wire auth"},
            "room": {"post_scaffold_note": "wire room"},
        },
        "post_scaffold_notes": {
            "heading": ["Reference packs:"],
            "footer": ["done."],
        },
    }
    out = scaffold.collect_post_scaffold_notes(manifest, {"auth", "room"})
    assert out["heading"] == ["Reference packs:"]
    assert out["footer"] == ["done."]
    assert out["per_pack"] == [("auth", "wire auth"), ("room", "wire room")]


def test_preserves_manifest_declaration_order():
    """Output order follows manifest declaration, not selected_pack_keys set order."""
    manifest = {
        "packs": {
            "ui_theme": {"post_scaffold_note": "theme"},
            "auth":     {"post_scaffold_note": "auth"},
            "room":     {"post_scaffold_note": "room"},
        },
        "post_scaffold_notes": {"heading": ["h"]},
    }
    # Pass selections in shuffled order — result should still follow manifest
    out = scaffold.collect_post_scaffold_notes(manifest, {"room", "ui_theme", "auth"})
    assert [k for k, _ in out["per_pack"]] == ["ui_theme", "auth", "room"]


def test_missing_heading_footer_defaults_to_empty_list():
    manifest = {
        "packs": {"auth": {"post_scaffold_note": "x"}},
        # no post_scaffold_notes block at all
    }
    out = scaffold.collect_post_scaffold_notes(manifest, {"auth"})
    assert out["heading"] == []
    assert out["footer"] == []
    assert out["per_pack"] == [("auth", "x")]


def test_unselected_packs_notes_not_included():
    manifest = {
        "packs": {
            "auth": {"post_scaffold_note": "wire auth"},
            "room": {"post_scaffold_note": "wire room"},
        },
    }
    out = scaffold.collect_post_scaffold_notes(manifest, {"auth"})
    assert out["per_pack"] == [("auth", "wire auth")]


def test_print_next_steps_emits_notes_from_result(capsys):
    """Integration: print_next_steps renders heading/footer/per-pack from result."""
    plan = {"stack": "kmp", "name": "Proj", "placeholder_map": {"project_slug": "proj"}}
    result = {
        "destination": "/tmp/proj",
        "selected_packs": ["auth"],
        "post_scaffold_notes": {
            "heading": ["HEADING_TEXT"],
            "footer": ["FOOTER_TEXT"],
            "per_pack": [("auth", "PACK_NOTE")],
        },
    }
    scaffold.print_next_steps(plan, result)
    err = capsys.readouterr().err
    assert "HEADING_TEXT" in err
    assert "PACK_NOTE" in err
    assert "FOOTER_TEXT" in err
    # The ordering inside the notes block must hold
    assert err.index("HEADING_TEXT") < err.index("PACK_NOTE") < err.index("FOOTER_TEXT")


def test_print_next_steps_no_notes_no_section(capsys):
    """When no per-pack notes, the heading+footer don't leak into output."""
    plan = {"stack": "kmp", "name": "Proj", "placeholder_map": {"project_slug": "proj"}}
    result = {
        "destination": "/tmp/proj",
        "selected_packs": [],
        "post_scaffold_notes": {
            "heading": ["HEADING_TEXT"],
            "footer": ["FOOTER_TEXT"],
            "per_pack": [],
        },
    }
    scaffold.print_next_steps(plan, result)
    err = capsys.readouterr().err
    assert "HEADING_TEXT" not in err
    assert "FOOTER_TEXT" not in err


def test_print_next_steps_handles_missing_notes_key(capsys):
    """Backwards compat: old starter manifests (no post_scaffold_notes) must still work."""
    plan = {"stack": "kmp", "name": "Proj", "placeholder_map": {"project_slug": "proj"}}
    result = {"destination": "/tmp/proj", "selected_packs": []}
    # Must not raise
    scaffold.print_next_steps(plan, result)
    err = capsys.readouterr().err
    assert "Next steps:" in err
