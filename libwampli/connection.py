import asyncio
import dataclasses
import functools
import logging
from typing import Any, Awaitable, Dict, Iterable, List, Tuple, Union

import aiobservable
import yarl
from autobahn import wamp
from autobahn.asyncio.component import Component

from .format import human_repr

__all__ = ["ConnectionConfig", "SubscriptionEvent", "Connection",
           "get_transports"]

log = logging.getLogger(__name__)


@dataclasses.dataclass()
class ConnectionConfig:
    realm: str
    transports: Union[str, List[dict]]
    subscriptions: Iterable[str] = None

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


@dataclasses.dataclass()
class SubscriptionEvent:
    uri: str
    args: Tuple[Any]
    kwargs: Dict[str, Any]

    def __str__(self) -> str:
        def repr_multiline(o: object) -> str:
            s = human_repr(o)
            lines = s.splitlines()
            if len(lines) > 1:
                indented = "\n".join(f"  {line}" for line in lines)
                return f"\n{indented}\n"
            else:
                return s

        args_fmt = ", ".join(map(repr_multiline, self.args))
        kwargs_fmt = "\n".join(f"  {key} = {repr_multiline(value)}"
                               for key, value in self.kwargs.items())

        fmt = f"{self.uri}"
        if args_fmt:
            fmt += f" ({args_fmt})"

        if kwargs_fmt:
            fmt += f" *\n{kwargs_fmt}"

        return fmt


class Connection(aiobservable.Observable):
    loop: asyncio.AbstractEventLoop
    config: ConnectionConfig

    _component: Component
    _session_future: asyncio.Future

    _subscriptions: Dict[str, wamp.types.ISubscription]

    def __init__(self, config: ConnectionConfig, *,
                 loop: asyncio.AbstractEventLoop = None) -> None:
        super().__init__(loop=loop or asyncio.get_event_loop())

        self.config = config
        self._component = Component(
            realm=config.realm,
            transports=config.transports,
            is_fatal=is_transport_lost,
        )
        self.__add_component_listeners()
        self.__reset_session()

        self._subscriptions = {}

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
        def on_connect(*_) -> None:
            log.debug("%s: connected", self)

        @component.on_join
        async def on_join(session: wamp.ISession, _) -> None:
            log.debug("%s joined", self)
            self.__fresh_session_future().set_result(session)

            subscriptions = self.config.subscriptions

            if subscriptions:
                coro_gen = (self.add_subscription(topic) for topic in subscriptions)
                await asyncio.gather(*coro_gen, loop=self.loop)

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

    async def __on_event(self, topic: str, *args, **kwargs) -> None:
        await self.emit(SubscriptionEvent(topic, args, kwargs))

    def has_subscription(self, topic: str) -> bool:
        try:
            return self._subscriptions[topic].active()
        except KeyError:
            return False

    async def add_subscription(self, topic: str) -> None:
        if self.has_subscription(topic):
            return

        session = await self.session
        self._subscriptions[topic] = await session.subscribe(
            functools.partial(self.__on_event, topic),
            topic,
        )

    async def remove_subscription(self, topic: str) -> None:
        try:
            subscription = self._subscriptions.pop(topic)
        except KeyError:
            return

        await subscription.unsubscribe()

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
        # So either the session becomes available or the "done" future resolves
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


def get_transports(url: Union[str, yarl.URL]) -> List[dict]:
    url = yarl.URL(url)

    # autobahn python doesn't understand the tcp scheme
    if url.scheme == "tcp":
        url = url.with_scheme("rs")

    if url.scheme in ("rs", "rss"):
        t_type = "rawsocket"
    else:
        t_type = "websocket"

    return [{
        "type": t_type,
        "url": str(url),
    }]
