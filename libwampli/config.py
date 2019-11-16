import dataclasses
from typing import List, Union

__all__ = ["ConnectionConfig"]


@dataclasses.dataclass()
class ConnectionConfig:
    """Config for a WAMP connection.

    Attributes:
        realm (str): Realm to connect to
        transports (Union[str, List[dict]]): Transports to use.
    """
    realm: str
    transports: Union[str, List[dict]]

    def __str__(self) -> str:
        return f"(realm={self.realm}, endpoint={self.endpoint})"

    @property
    def endpoint(self) -> str:
        """URL of the WAMP router.

        Not necessarily the correct router url if multiple transports
        were specified.
        """
        if isinstance(self.transports, str):
            return self.transports

        try:
            return self.transports[0]["url"]
        except (IndexError, KeyError):
            raise ValueError("No transport given") from None
