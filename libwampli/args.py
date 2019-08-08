"""Argument parsing."""

import io
import re
import shlex
import tokenize
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, Optional, Pattern, Tuple, Union

import yaml

__all__ = ["parse_arg_value", "parse_args",
           "split_function_style", "split_arg_string", "split_kwarg",
           "ready_uri"]

# match: wamp.session.get(12345, key=value)
RE_FUNCTION_STYLE: Pattern = re.compile(
    r"""^
      ((?: (?: [0-9a-z_]+\. ) | \. )* (?: [0-9a-z_]+ )?)    # match URI (1)
      \s?
      \(
        (.*)                                                # arguments (2)
      \)
    $""",
    re.VERBOSE,
)


def split_function_style(text: str) -> List[str]:
    """Split a function style call text representation into its arguments.
    Returns:
        Empty list if the given string didn't match the function style,
        otherwise a list with at least the URI as its first item.
    """
    match = RE_FUNCTION_STYLE.match(text)
    if match is None:
        return []

    uri, arg_string = match.groups()
    args = [uri]

    if arg_string:
        token_gen = tokenize.generate_tokens(io.StringIO(arg_string).readline)
        # get the indices of the commas in the string
        commapos = (
            -1,
            *(token.end[1] for token in token_gen if token.string == ","),
            len(arg_string) + 1,
        )

        args.extend([
            arg_string[commapos[i] + 1: commapos[i + 1] - 1]
            for i in range(len(commapos) - 1)
        ])

    return args


def split_arg_string(arg: str) -> List[str]:
    """Split an argument string into its arguments"""
    res = split_function_style(arg)
    return res or shlex.split(arg)


# match: key=value
RE_KWARGS_MATCH: Pattern = re.compile(r"^([a-z][a-z0-9_]{2,})\s*=(.+)$")


def split_kwarg(arg: str) -> Tuple[Optional[str], str]:
    match = RE_KWARGS_MATCH.match(arg)
    if match is None:
        return None, arg

    k, v = match.groups()
    return k, v


def parse_arg_value(val: str) -> Any:
    """Parse a string value into its Python representation."""
    return yaml.safe_load(val)


def parse_args(args: Union[Iterable[str], str]) -> Tuple[List[Any], Dict[str, Any]]:
    """Parse string arguments into their Python representation.
    Returns:
        2-tuple (args, kwargs) where the first item is a `list` containing
        the positional arguments and the second item a `dict` containing
        the keyword arguments (key=value).
    """
    if isinstance(args, str):
        args = split_arg_string(args)

    _args: List[Any] = []
    _kwargs: Dict[str, Any] = {}

    for arg in args:
        key, raw_value = split_kwarg(arg)
        value = parse_arg_value(raw_value)

        if key is None:
            _args.append(value)
        else:
            _kwargs[key] = value

    return _args, _kwargs


def ready_uri(args: MutableSequence[Any], *, aliases: Mapping[str, str] = None) -> None:
    """Treat the first argument as the uri prepare it.

    The given args may be mutated.

    Args:
        args: Arguments where the first argument is to be treated as a uri.
        aliases: Mapping of alias to uri which is used to replace the uri.

    Raises:
        IndexError: If args is empty.
        TypeError: If the first argument isn't a string.
    """
    try:
        uri = args[0]
    except IndexError:
        raise IndexError("Please provide a URI")

    if not isinstance(uri, str):
        raise TypeError("URI must be a string")

    if aliases:
        try:
            uri = aliases[uri]
        except KeyError:
            pass

    args[0] = uri
