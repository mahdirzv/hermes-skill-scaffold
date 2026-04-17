import scaffold


def test_expands_single_token():
    assert scaffold.placeholder_expand("hello {{name}}", {"name": "world"}) == "hello world"


def test_expands_multiple_tokens():
    out = scaffold.placeholder_expand(
        "{{a}}-{{b}}-{{a}}", {"a": "x", "b": "y"}
    )
    assert out == "x-y-x"


def test_unknown_tokens_are_left_intact():
    assert scaffold.placeholder_expand("{{missing}} stays", {"other": "v"}) == "{{missing}} stays"


def test_longest_key_wins_on_overlap():
    """Shorter keys must not clobber parts of longer keys (`project` vs `project_name`)."""
    values = {"project": "SHORT", "project_name": "LONG"}
    out = scaffold.placeholder_expand("{{project_name}} / {{project}}", values)
    assert out == "LONG / SHORT"


def test_empty_values_map_is_a_noop():
    assert scaffold.placeholder_expand("{{a}} b", {}) == "{{a}} b"


def test_empty_string_value_replaces_token():
    assert scaffold.placeholder_expand("x={{a}};", {"a": ""}) == "x=;"
