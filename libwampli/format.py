"""Formatting WAMP related things."""

import dataclasses
import json
from typing import Any, Iterable, Mapping

import yaml

from .args import split_kwarg

__all__ = ["repr_arg_value", "format_function_style",
           "human_repr", "human_result",
           "indent_multiline"]


def repr_arg_value(val: Any) -> str:
    """Return the value's string representation.

    The representation can be used by `libwampli.parse_arg_value` to retrieve
    the value.
    """
    try:
        return json.dumps(val)
    except ValueError:
        return yaml.safe_dump(val)


def format_function_style(args: Iterable[Any], kwargs: Mapping[str, Any] = None) -> str:
    """Create a function-style representation.

    The representation can be used by `libwampli.parse_args` to get the
    individual components back.

    Args:
        args: Arguments for the call. The first argument is used as the uri.
        kwargs: Keyword arguments for the call. If `None` the kwargs will be
            extracted from args. If no kwargs should be used, pass an empty
            mapping!
    """
    arg_iter = iter(args)
    try:
        uri = str(next(arg_iter))
    except StopIteration:
        raise ValueError("No uri in args") from None

    if kwargs is None:
        arg_strs = []

        for arg in arg_iter:
            if isinstance(arg, str):
                key, value = split_kwarg(arg)
            else:
                key = None
                value = repr_arg_value(arg)

            if key is None:
                arg_strs.append(value)
            else:
                arg_strs.append(f"{key}={value}")

        args_str = ", ".join(arg_strs)
    else:
        args_str = ", ".join(map(repr_arg_value, arg_iter))

        kwargs_str = ", ".join(f"{key}={repr_arg_value(value)}" for key, value in kwargs.items())
        if kwargs_str:
            args_str += f", {kwargs_str}"

    return f"{uri}({args_str})"


def human_repr(o: Any) -> str:
    """Convert the given object to a meaningful representation.

    The output is similar to YAML.
    """
    if dataclasses.is_dataclass(o):
        return str(o)

    try:
        s = yaml.dump(o)
    except yaml.YAMLError:
        return str(o)

    # we don't really care about the document termination
    # and the newlines
    if s.endswith("\n...\n"):
        return s[:-5]
    else:
        return s


def human_result(result: Any) -> str:
    """Convert the given result to human readable text.

    Treats `None` as an ok sign. Apart from this the only difference
    to `human_repr` is that it applies `indent_multiline` automatically.
    """
    if result is None:
        return "ok"

    return indent_multiline(human_repr(result))


def indent_multiline(s: str, indentation: str = "  ", add_newlines: bool = True) -> str:
    """Indent the given string if it contains more than one line.

    Args:
        s: String to indent
        indentation: Indentation to prepend to each line.
        add_newlines: Whether to add newlines surrounding the result
            if indentation was added.
    """
    lines = s.splitlines()
    if len(lines) <= 1:
        return s

    lines_str = "\n".join(f"{indentation}{line}" for line in lines)
    if add_newlines:
        return f"\n{lines_str}\n"
    else:
        return lines_str
