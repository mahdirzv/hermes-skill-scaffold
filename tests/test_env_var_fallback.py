"""Env-var fallback for provider secret flags — keeps secrets out of shell history."""
import argparse
import scaffold


def _base_args(**overrides):
    """Build an argparse.Namespace shaped like the real CLI would produce."""
    args = argparse.Namespace(
        stack="nextjs",
        name="App",
        package_prefix="com.example",
        bundle_prefix=None,
        auth_provider="clerk",
        theme_preset=None,
        clerk_publishable_key=None,
        clerk_secret_key=None,
        supabase_url=None,
        supabase_anon_key=None,
        no_auth=False,
        no_theme=False,
        room=False,
        ci=False,
        pack=[],
    )
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _registry():
    return {"packs": [], "stack_defaults": {"nextjs": {}}}


def test_flag_value_used_when_provided(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "env_value")
    args = _base_args(clerk_secret_key="flag_value")
    values = scaffold.merged_placeholders(_registry(), {}, [], args)
    assert values["clerk_secret_key"] == "flag_value"


def test_env_var_used_when_flag_omitted(monkeypatch):
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test_fromenv")
    monkeypatch.setenv("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "pk_test_fromenv")
    args = _base_args()
    values = scaffold.merged_placeholders(_registry(), {}, [], args)
    assert values["clerk_secret_key"] == "sk_test_fromenv"
    assert values["clerk_publishable_key"] == "pk_test_fromenv"


def test_empty_when_neither_flag_nor_env(monkeypatch):
    for v in ("CLERK_SECRET_KEY", "NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY",
              "NEXT_PUBLIC_SUPABASE_URL", "NEXT_PUBLIC_SUPABASE_ANON_KEY"):
        monkeypatch.delenv(v, raising=False)
    args = _base_args()
    values = scaffold.merged_placeholders(_registry(), {}, [], args)
    assert values["clerk_secret_key"] == ""
    assert values["supabase_url"] == ""


def test_flag_wins_even_against_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://from-env.supabase.co")
    args = _base_args(supabase_url="https://from-flag.supabase.co")
    values = scaffold.merged_placeholders(_registry(), {}, [], args)
    assert values["supabase_url"] == "https://from-flag.supabase.co"


def test_all_four_secret_flags_mapped():
    """Regression guard: the env-var mapping must cover every secret flag."""
    flag_names = {row[0] for row in scaffold._SECRET_FLAG_TABLE}
    assert flag_names == {
        "clerk_publishable_key",
        "clerk_secret_key",
        "supabase_url",
        "supabase_anon_key",
    }
    # Each row has (flag, placeholder, env_var); none empty
    for flag, placeholder, env_var in scaffold._SECRET_FLAG_TABLE:
        assert flag and placeholder and env_var
        assert env_var.isupper() or "_" in env_var  # env convention
