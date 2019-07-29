import asyncio

from autobahn.asyncio.component import Component
from autobahn.wamp.interfaces import ISession

from .connection import Connection

__all__ = ["SessionContext", "wait_for_leave"]


class SessionContext(Connection):
    async def __aenter__(self) -> ISession:
        await self.open()
        return await self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def wait(self) -> None:
        await wait_for_leave(self._component, loop=self._loop)


def wait_for_leave(c: Component, *, loop: asyncio.AbstractEventLoop) -> asyncio.Future:
    fut = loop.create_future()

    @c.on_leave
    def on_leave(*_) -> None:
        fut.set_result(None)

    return fut
