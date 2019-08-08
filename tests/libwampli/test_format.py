from typing import Any

import pytest

import libwampli


@pytest.mark.parametrize("i,e", [
    ("hello", "hello"),
    (5, "5"),
    (["hey", "there"], "- hey\n- there\n"),
])
def test_human_repr(i: Any, e: str):
    assert libwampli.human_repr(i) == e


def test_format_function_style():
    args = ["wamp.session.get", 123456789, "key=value"]
    assert libwampli.format_function_style(args) == "wamp.session.get(123456789, key=value)"
