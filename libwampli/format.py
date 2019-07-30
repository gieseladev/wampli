import dataclasses
from typing import Any

import yaml

__all__ = ["human_repr", "human_result", "indent_multiline"]


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
    if result is None:
        return "ok"

    return indent_multiline(human_repr(result))


def indent_multiline(s: str, indentation: str = "  ", add_newlines: bool = True) -> str:
    lines = s.splitlines()
    if len(lines) <= 1:
        return s

    lines_str = "\n".join(f"{indentation}{line}" for line in lines)
    if add_newlines:
        return f"\n{lines_str}\n"
    else:
        return lines_str
