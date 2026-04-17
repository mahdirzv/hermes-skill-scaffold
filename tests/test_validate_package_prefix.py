import pytest
import scaffold


@pytest.mark.parametrize(
    "prefix",
    [
        "com.example",
        "dev.mahdi",
        "io.yourcompany",
        "a",                     # single segment, single char
        "com.example.deeply.nested.namespace",
        "com.ex_ample",          # underscore allowed mid-segment
        "com.example99",         # digits allowed after first char
    ],
)
def test_accepts_valid_prefix(prefix):
    # No exception = pass (function returns None).
    scaffold.validate_package_prefix(prefix)


@pytest.mark.parametrize(
    "prefix",
    [
        "",                       # empty
        "Com.Example",            # uppercase
        "com.example-bad",        # hyphen not allowed
        "com..example",           # empty segment
        "1com.example",           # starts with digit
        "com.1example",           # segment starts with digit
        "com.example.",           # trailing dot
        ".com.example",           # leading dot
        "com example",            # space
        "com.ex ample",           # space mid-segment
        "com.example/foo",        # slash
    ],
)
def test_rejects_invalid_prefix(prefix):
    with pytest.raises(SystemExit):
        scaffold.validate_package_prefix(prefix)
