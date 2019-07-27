import asyncio
import dataclasses
import logging
import pathlib
from typing import Awaitable, List, Union

from autobahn import wamp
from autobahn.asyncio.component import Component

__all__ = ["ConnectionConfig", "Connection",
           "get_transports"]

log = logging.getLogger(__name__)

DB_PATH = pathlib.Path("data/connections/db")


@dataclasses.dataclass()
class ConnectionConfig:
    realm: str
    transports: Union[str, List[dict]]

    def __str__(self) -> str:
        return f"(realm={self.realm}, endpoint={self.endpoint})"

    @property
    def endpoint(self) -> str:
        if isinstance(self.transports, str):
            return self.transports

        try:
            return self.transports[0]["url"]
        except (IndexError, KeyError):
            raise ValueError("No transport given") from None


def is_transport_lost(e: Exception) -> bool:
    if isinstance(e, wamp.TransportLost):
        log.info("encountered transport lost, treating as fatal to avoid reconnect. %s", e)
        return True

    return False


class Connection:
    loop: asyncio.AbstractEventLoop
    config: ConnectionConfig

    _component: Component
    _session_future: asyncio.Future

    def __init__(self, config: ConnectionConfig, *,
                 loop: asyncio.AbstractEventLoop = None) -> None:
        self.loop = loop or asyncio.get_event_loop()

        self.config = config
        self._component = Component(
            realm=config.realm,
            transports=config.transports,
            is_fatal=is_transport_lost,
        )
        self.__add_component_listeners()

        self.__reset_session()

    def __repr__(self) -> str:
        return f"Connection({self.config!r})"

    def __str__(self) -> str:
        return f"Connection({self.config})"

    @property
    def component(self) -> Component:
        return self._component

    def __add_component_listeners(self) -> None:
        component = self._component

        @component.on_connect
        def on_connect(session: wamp.ISession, _) -> None:
            log.debug("%s: connected", self)
            self.__fresh_session_future().set_result(session)

        @component.on_join
        async def on_join(*_) -> None:
            log.debug("%s joined", self)

        @component.on_disconnect
        def on_disconnect(_, *, was_clean: bool) -> None:
            log.debug("%s: disconnected clean=%s", self, was_clean)
            self.__reset_session()

        @component.on_connectfailure
        def on_fail(_, e: Exception) -> None:
            log.debug("%s: failed to connect: %s", self, e)
            self.__fresh_session_future().set_exception(e)

        @component.on_leave
        def on_leave(*_) -> None:
            log.debug("%s: left session", self)
            self.__reset_session()

    def __reset_session(self) -> None:
        self._session_future = self.loop.create_future()

    def __fresh_session_future(self) -> asyncio.Future:
        if self._session_future.done():
            log.debug("%s: resetting session future: %s", self, self._session_future)
            self.__reset_session()

        return self._session_future

    @property
    def connected(self) -> bool:
        return self._session_future.done() and not self._session_future.exception()

    @property
    def session(self) -> Awaitable[wamp.ISession]:
        return asyncio.shield(self._session_future, loop=self.loop)

    async def open(self) -> None:
        log.debug("%s: opening connection", self)

        # some exceptions can only be captured by awaiting this,
        # however we don't want to wait until the component is "done"
        # (i.e. closed), so we race it with the session becoming available.
        # So either the session becomes available or the "done" future results
        # to an error.
        done_fut = self._component.start(loop=self.loop)

        done_fs, _ = await asyncio.wait(
            (done_fut, self.session),
            return_when=asyncio.FIRST_COMPLETED
        )

        fut = done_fs.pop()

        try:
            return fut.result()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        log.debug("%s: closing connection", self)
        await self._component.stop()


def get_transports(url: str) -> List[dict]:
    url = url.replace("tcp://", "rs://", 1)

    transport_type = "rawsocket" if url.startswith("rs://") else "websocket"

    transport = {
        "url": url,
        "type": transport_type,
    }

    return [transport]
