import asyncio
from typing import Awaitable

from autobahn.asyncio.component import Component
from autobahn.wamp.interfaces import ISession

__all__ = ["create_component", "wait_for_join", "get_session"]


def create_component(realm: str) -> Component:
    return Component(realm=realm)


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
