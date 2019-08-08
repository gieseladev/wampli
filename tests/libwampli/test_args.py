from typing import List, Optional, Tuple, Any, Dict

import libwampli
import pytest


@pytest.mark.parametrize("inp,expected", [
    ("a()", ["a"]),
    ("a.b(hello, world)", ["a.b", "hello", "world"]),
    ("test(key=value)", ["test", "key=value"]),
])
def test_split_function_style(inp: str, expected: List[str]):
    assert libwampli.split_function_style(inp) == expected


@pytest.mark.parametrize("inp,expected", [
    ("test(a, b=c, d, key=value)", ["test", "a", "b=c", "d", "key=value"]),
    ("hello world \"multi word\"", ["hello", "world", "multi word"])
])
def test_split_arg_string(inp: str, expected: List[str]):
    assert libwampli.split_arg_string(inp) == expected


@pytest.mark.parametrize("inp,expected", [
    ("hey", (None, "hey")),
    ("key=value", ("key", "value")),
    ("2=5", (None, "2=5")),
    ("hey=", (None, "hey="))
])
def test_split_kwarg(inp: str, expected: Tuple[Optional[str], str]):
    assert libwampli.split_kwarg(inp) == expected


@pytest.mark.parametrize("inp,expected", [
    (
            ("hello", "55", "[a, 3., c]", "key=value", "val=5"),
            (["hello", 55, ["a", 3., "c"]], {"key": "value", "val": 5})
    ),
])
def test_parse_args(inp: Tuple[str], expected: Tuple[List[Any], Dict[str, Any]]):
    assert libwampli.parse_args(inp) == expected


def test_ready_uri():
    with pytest.raises(IndexError):
        libwampli.ready_uri([])
    with pytest.raises(TypeError):
        libwampli.ready_uri([5])

    a = ["hello", "world"]
    libwampli.ready_uri(a)
    assert a == ["hello", "world"]

    libwampli.ready_uri(a, aliases={"hello": "wamp.session.welcome", "world": "nothing"})
    assert a == ["wamp.session.welcome", "world"]
