import asyncio
from typing import Awaitable

from autobahn.asyncio.component import Component
from autobahn.wamp.interfaces import ISession

__all__ = ["Session", "wait_for_join", "get_session"]


class Session:
    _component: Component
    _sess: ISession
    _loop: asyncio.AbstractEventLoop

    def __init__(self, component: Component, *, loop: asyncio.AbstractEventLoop = None) -> None:
        self._component = component
        self._loop = loop or asyncio.get_event_loop()

    async def __aenter__(self) -> ISession:
        self._sess = await get_session(self._component, loop=self._loop)
        return self._sess

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._sess.leave()


def wait_for_join(c: Component, *, loop: asyncio.AbstractEventLoop) -> Awaitable[ISession]:
    fut = loop.create_future()

    @c.on_join
    def joined(session: ISession, _) -> None:
        fut.set_result(session)

    @c.on_connectfailure
    def failed(_, error: Exception) -> None:
        fut.set_exception(error)

    return fut


async def get_session(c: Component, *, loop: asyncio.AbstractEventLoop) -> ISession:
    sess = c._session
    if sess and sess.is_attached():
        return sess

    # make sure the component is actually running
    asyncio.ensure_future(c.start(loop=loop), loop=loop)

    return await wait_for_join(c, loop=loop)
