import dataclasses
from typing import Any

import yaml

__all__ = ["human_repr", "human_result"]


def human_repr(o: Any) -> str:
    """Convert the given object to a meaningful representation.

    The output is similar to YAML.
    """
    if dataclasses.is_dataclass(o):
        return str(o)

    try:
        return yaml.dump(o)
    except yaml.YAMLError:
        return str(o)


def human_result(result: Any) -> str:
    if result is None:
        return "ok"

    return human_repr(result)
