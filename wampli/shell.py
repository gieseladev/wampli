import io

__all__ = ["Shell"]


class AsyncInputReader:
    _reader: io.TextIOBase

    def __init__(self, reader: io.TextIOBase) -> None:
        self._reader = reader


# TODO call
# TODO publish
# TODO subscribe
# TODO alias uri

class Shell:
    pass
