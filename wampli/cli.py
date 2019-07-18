import argparse
import asyncio
import functools
import signal
import sys
from typing import Any, Awaitable, Callable

import yarl
from autobahn import wamp
from autobahn.asyncio.component import Component

import wampli


def get_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the wampli cli.

    Resulting args contain the special value `entrypoint_func` which
    is either a function which should be called with the args or `None` if no
    subcommand was selected.
    """
    parser = argparse.ArgumentParser("wampli", description="A command line interface for the WAMP protocol.")
    parser.set_defaults(entrypoint_func=None)

    # CURRENTLY UNUSED
    # parser.add_argument("-c", "--config", help="location of the config file")
    # parser.add_argument("--ignore-config", action="store_true", default=False,
    #                     help="don't search for a config file")

    def add_wamp_argument_group(p) -> None:
        wamp = p.add_argument_group("wamp arguments", description="Arguments for WAMP")
        wamp.add_argument("-u", "--url", help="url of the WAMP router to connect to", required=True)
        wamp.add_argument("-r", "--realm", help="realm to join", required=True)

    def add_uri_argument(p, **kwargs) -> None:
        p.add_argument("uri", help="WAMP URI", **kwargs)

    def add_procedure_args_arguments(p) -> None:
        add_uri_argument(p)
        p.add_argument("args",
                       help="Arguments to provide. Use key=value for keyword arguments",
                       nargs="*")

    add_wamp_argument_group(parser)

    subparsers = parser.add_subparsers(title="commands")

    call = subparsers.add_parser("call", help="call a procedure")
    call.set_defaults(entrypoint_func=_call_cmd)
    add_procedure_args_arguments(call)

    publish = subparsers.add_parser("publish", help="publish to a topic")
    publish.set_defaults(entrypoint_func=_publish_cmd)
    add_procedure_args_arguments(publish)

    subscribe = subparsers.add_parser("subscribe", help="subscribe to a topic")
    subscribe.set_defaults(entrypoint_func=_subscribe_cmd)
    add_uri_argument(subscribe, nargs="*")

    shell = subparsers.add_parser("shell", help="start the interactive shell")
    shell.set_defaults(entrypoint_func=_shell_cmd)

    return parser


def _get_component(args: argparse.Namespace) -> Component:
    url = yarl.URL(args.url)

    # autobahn python doesn't understand the tcp scheme
    if url.scheme == "tcp":
        url = url.with_scheme("rs")

    if url.scheme in ("rs", "rss"):
        t_type = "rawsocket"
    else:
        t_type = "websocket"

    transports = [
        {
            "type": t_type,
            "url": str(url),
        },
    ]

    return Component(realm=args.realm, transports=transports)


def _get_session(args: argparse.Namespace, *, loop: asyncio.AbstractEventLoop) -> wampli.Session:
    return wampli.Session(_get_component(args), loop=loop)


def _run_async(loop: asyncio.AbstractEventLoop, coro: Awaitable) -> Any:
    def graceful_exit() -> None:
        pending = asyncio.Task.all_tasks()
        for task in pending:
            task.cancel()

        loop.stop()

    try:
        loop.add_signal_handler(signal.SIGINT, graceful_exit)
        loop.add_signal_handler(signal.SIGTERM, graceful_exit)
    except NotImplementedError:
        pass

    try:
        return loop.run_until_complete(coro)
    except KeyboardInterrupt:
        print("Exiting")

    loop.close()


def _run_async_cmd(cmd: Callable[[asyncio.AbstractEventLoop], Any]) -> Any:
    loop = asyncio.get_event_loop()
    _run_async(loop, cmd(loop))


def _run_cmd(cmd: Callable[[asyncio.AbstractEventLoop], Any]) -> None:
    try:
        result = _run_async_cmd(cmd)
    except wamp.ApplicationError as e:
        sys.exit(e.error_message())
    else:
        if result is None:
            print("done")
        else:
            print(result)


def _call_cmd(args: argparse.Namespace) -> None:
    async def cmd(loop: asyncio.AbstractEventLoop) -> None:
        async with _get_session(args, loop=loop) as session:
            return await session.call(args.uri, *call_args, **call_kwargs)

    call_args, call_kwargs = wampli.parse_args(args.args)
    _run_cmd(cmd)


def _publish_cmd(args: argparse.Namespace) -> None:
    async def cmd(loop: asyncio.AbstractEventLoop) -> None:
        async with _get_session(args, loop=loop) as session:
            # TODO provide options for acknowledge and so on
            ack = session.publish(args.uri, *publish_args, **publish_kwargs)
            if ack is not None:
                return await ack
            else:
                return None

    publish_args, publish_kwargs = wampli.parse_args(args.args)
    _run_cmd(cmd)


def _subscribe_cmd(args: argparse.Namespace) -> None:
    async def on_event(uri: str, *_args, **_kwargs) -> None:
        print(f"{uri}: {_args} {_kwargs}")

    async def cmd(loop: asyncio.AbstractEventLoop) -> None:
        async with _get_session(args, loop=loop) as session:
            gen = (session.subscribe(functools.partial(on_event, uri), uri) for uri in args.uri)
            await asyncio.gather(*gen)
            print(f"subscribed to {len(args.uri)} topic(s)")

            await asyncio.sleep(100)

    _run_cmd(cmd)


def _shell_cmd(args: argparse.Namespace) -> None:
    shell = wampli.Shell(_get_component(args))
    shell.run()


def main() -> None:
    """Entry point for the cli"""
    parser = get_parser()
    args = parser.parse_args()
    func = args.entrypoint_func

    if func is None:
        parser.print_usage()
        return

    func(args)


if __name__ == "__main__":
    main()