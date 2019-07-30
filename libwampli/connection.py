"""Connection to a WAMP router."""

import asyncio
import dataclasses
import functools
import logging
from typing import Any, Awaitable, Dict, List, Optional, Set, Tuple, Union

import aiobservable
import yarl
from autobahn import wamp
from autobahn.asyncio.component import Component

from .format import human_repr, indent_multiline

__all__ = ["ConnectionConfig", "SubscriptionEvent", "Connection",
           "get_transports"]

log = logging.getLogger(__name__)


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


def is_transport_lost(e: Exception) -> bool:
    """Check whether the given exception is `autobahn.wamp.TransportLost`."""
    if isinstance(e, wamp.TransportLost):
        log.info("encountered transport lost, treating as fatal to avoid reconnect. %s", e)
        return True

    return False


@dataclasses.dataclass()
class SubscriptionEvent:
    """Event emitted when an event of a subscribed topic is received.

    Attributes:
        uri (str): Topic of the event.
        args (Tuple[Any]): Arguments of the event.
        kwargs (Dict[str, Any]): Keyword arguments of the event.
    """
    uri: str
    args: Tuple[Any]
    kwargs: Dict[str, Any]

    def __str__(self) -> str:
        fmt = f"{self.uri}"

        args_fmt = self.format_args()
        if args_fmt:
            fmt += f" ({args_fmt})"

        kwargs_fmt = self.format_kwargs()
        if kwargs_fmt:
            fmt += f" *\n{kwargs_fmt}"

        return fmt

    def format_args(self) -> str:
        """Format the arguments into a human readable format.

        Uses `human_repr`.
        """
        return ", ".join(indent_multiline(human_repr(arg)) for arg in self.args)

    def format_kwargs(self) -> str:
        """Format the keyword arguments into a human readable format.

        Uses `human_repr`.
        """
        return "\n".join(f"  {key} = {indent_multiline(human_repr(value))}"
                         for key, value in self.kwargs.items())


class Connection(aiobservable.Observable):
    """Connection to a WAMP router.

    Args:
        config: Connection config
        planned_subscriptions: Set of topics to subscribe to once connected
        loop: Specify the event loop to be used.

    Attributes:
        config (ConnectionConfig): Config that was passed to the constructor.
    """
    config: ConnectionConfig

    _loop: asyncio.get_event_loop()
    _component: Component
    _join_future: asyncio.Future

    _planned_subscriptions: Set[str]
    _active_subscriptions: Dict[str, wamp.types.ISubscription]

    def __init__(self, config: ConnectionConfig, *,
                 planned_subscriptions: Set[str] = None,
                 loop: asyncio.AbstractEventLoop = None) -> None:
        super().__init__()

        self.config = config
        self._component = Component(
            realm=config.realm,
            transports=config.transports,
            # issue! see https://github.com/crossbario/autobahn-python/issues/1231
            is_fatal=is_transport_lost,
        )
        self.__add_component_listeners()

        self._loop = loop or asyncio.get_event_loop()
        self._join_future = self._loop.create_future()

        self._planned_subscriptions = planned_subscriptions or set()
        self._active_subscriptions = {}

    def __repr__(self) -> str:
        return f"Connection({self.config!r})"

    def __str__(self) -> str:
        return f"Connection({self.config})"

    @property
    def component(self) -> Component:
        """Underlying autobahn component."""
        return self._component

    def __add_component_listeners(self) -> None:
        component = self._component

        @component.on_connect
        def on_connect(*_) -> None:
            log.debug("%s: connected", self)

        @component.on_connectfailure
        def on_fail(_, e: Exception) -> None:
            log.debug("%s: failed to connect: %s", self, e)
            try:
                self._join_future.set_exception(e)
            except asyncio.InvalidStateError:
                pass

        @component.on_disconnect
        def on_disconnect(_, *, was_clean: bool) -> None:
            log.debug("%s: disconnected clean=%s", self, was_clean)

        @component.on_join
        def on_join(*_) -> None:
            log.debug("%s joined", self)

            try:
                self._join_future.set_result(None)
            except asyncio.InvalidStateError:
                pass

        @component.on_ready
        async def on_ready(*_) -> None:
            coro_gen = (self._subscribe(topic) for topic in self._planned_subscriptions)
            await asyncio.gather(*coro_gen)

        @component.on_leave
        def on_leave(*_) -> None:
            log.debug("%s: left session", self)
            self._loop.create_future()

    async def __on_event(self, topic: str, *args, **kwargs) -> None:
        await self.emit(SubscriptionEvent(topic, args, kwargs))

    def has_planned_subscription(self, topic: str) -> bool:
        """Check whether the given topic is a planned subscription."""
        return topic in self._planned_subscriptions

    def has_active_subscription(self, topic: str) -> bool:
        """Check whether the given topic is currently subscribed to.

        This implies that the connection is connected and the subscription
        is active.
        """
        try:
            return self._active_subscriptions[topic].active()
        except KeyError:
            return False

    async def _subscribe(self, topic: str) -> None:
        session = await self.session
        self._active_subscriptions[topic] = await session.subscribe(
            functools.partial(self.__on_event, topic),
            topic,
        )

    def get_planned_subscriptions(self) -> Tuple[str, ...]:
        """Get all planned subscription topics."""
        return tuple(self._planned_subscriptions)

    def plan_subscription(self, *topics: str) -> None:
        """Add the given topic(s) to the planned subscriptions.

        A planned subscriptions will be subscribed to once the connection
        is connected.
        If already connected, use `add_subscription`.
        """
        self._planned_subscriptions.update(topics)

    async def add_subscription(self, topic: str) -> None:
        """Add the topic to the planned subscriptions and subscribe to it if
        connected."""
        self.plan_subscription(topic)

        if self.connected:
            await self._subscribe(topic)
        else:
            log.debug("%s: not connected yet, subscribing when ready", self)

    def unplan_subscription(self, *topics: str) -> None:
        """Remove the topic(s) from the planned subscriptions."""
        self._planned_subscriptions.difference_update(topics)

    async def remove_subscription(self, topic: str) -> None:
        """Remove the given topic from the planned subscriptions and unsubscribe."""
        self.unplan_subscription(topic)

        try:
            subscription = self._active_subscriptions.pop(topic)
        except KeyError:
            return

        await subscription.unsubscribe()

    @property
    def component_session(self) -> Optional[wamp.ISession]:
        """Underlying component's session.

        Will be `None` if not connected.
        """
        return self._component._session

    @property
    def connected(self) -> bool:
        """Whether connection is connected to the router."""
        session = self.component_session
        return session and session.is_connected()

    @property
    def session(self) -> Awaitable[wamp.ISession]:
        """Future resolving to a session once joined.

        Resolves right away if already connected.
        """
        return self._loop.create_task(self.get_session())

    async def get_session(self) -> wamp.ISession:
        """Get the session.

        If not connected this opens the connection.
        """
        if not self.connected:
            await self.open()

        session = self.component_session
        assert session, "session should not be None at this point"

        return session

    async def open(self) -> None:
        """Open the connection.

        Waits until the connection is established and the session available.
        """
        log.debug("%s: opening connection", self)

        # some exceptions can only be captured by awaiting this,
        # however we don't want to wait until the component is "done"
        # (i.e. closed), so we race it with joining the session.
        done_fut = self._component.start(loop=self._loop)

        done_fs, _ = await asyncio.wait(
            (done_fut, self._join_future),
            return_when=asyncio.FIRST_COMPLETED
        )

        fut = done_fs.pop()

        try:
            return fut.result()
        except Exception:
            await self.close()
            raise

    async def close(self) -> None:
        """Close the connection.

        Waits until the component is done.
        """
        if not self.connected:
            log.debug("%s: already closed", self)
            return

        log.debug("%s: closing connection", self)
        fut = self.component_session.leave()
        if fut:
            await fut

        await self.wait_done()

    async def wait_done(self) -> None:
        """Wait for the component to be done.

        Being done means that the component is stopped.
        This will wait indefinitely if the component isn't stopped.
        """
        done_f = self._component._done_f
        if done_f:
            try:
                await done_f
            except Exception:
                log.exception("error happened cool")


def get_transports(url: Union[str, yarl.URL]) -> List[dict]:
    """Get the transports for the given url.

    This treats the tcp scheme as a rawsocket connection.
    """
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
