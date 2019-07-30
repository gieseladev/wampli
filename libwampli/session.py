from autobahn.wamp.interfaces import ISession

from .connection import Connection

__all__ = ["SessionContext"]


class SessionContext(Connection):
    """Context manager wrapper for a connection."""

    async def __aenter__(self) -> ISession:
        await self.open()
        return await self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
