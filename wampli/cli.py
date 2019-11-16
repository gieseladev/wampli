"""WAMPli cli."""

import argparse
import asyncio
import signal
import sys
from typing import Any, Awaitable, Callable

import aiowamp

import libwampli
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


def get_connection_config(args: argparse.Namespace) -> libwampli.ConnectionConfig:
    """Create a connection config from the cli args.

    Args:
        args: Argument Namespace from `get_parser`.

    Returns:
        Connection configuration for `libwampli`
    """
    return libwampli.ConnectionConfig(realm=args.realm, transports=args.url)


def get_client_context(args: argparse.Namespace) -> libwampli.ClientContextManager:
    """Create a session context from the cli args.

    Args:
        args: Argument Namespace from `get_parser`.

    Returns:
        Context manager for `libwampli.Connection` configured
        to the router denoted by the arguments.
    """
    return libwampli.ClientContextManager(get_connection_config(args))


def _run_async(loop: asyncio.AbstractEventLoop, coro: Awaitable) -> Any:
    """Run a coroutine.

    Does some special signal handling to perform a graceful exit.

    Args:
        loop: Event loop to run coroutine in.
        coro: Coroutine to run

    Returns:
        Result of the coroutine.
    """

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


def _run_async_cmd(cmd: Callable[[], Any]) -> Any:
    """Run the coroutine and return its return value."""
    loop = asyncio.get_event_loop()
    _run_async(loop, cmd())


def _run_cmd(cmd: Callable[[], Any]) -> None:
    """Run a WAMP command.

    Uses `_run_async_cmd` to run the command, but handles return values
    and exceptions.
    """
    try:
        result = _run_async_cmd(cmd)
    except aiowamp.ErrorResponse as e:
        sys.exit(str(e))
    else:
        print(libwampli.human_result(result))


def _call_cmd(args: argparse.Namespace) -> None:
    """Call command."""

    async def cmd() -> Any:
        async with get_client_context(args) as client:
            return await client.call(args.uri, *call_args, kwargs=call_kwargs)

    call_args, call_kwargs = libwampli.parse_args(args.args)
    _run_cmd(cmd)


def _publish_cmd(args: argparse.Namespace) -> None:
    """Publish command."""

    async def cmd() -> None:
        async with get_client_context(args) as session:
            # TODO provide options for acknowledge and so on
            ack = session.publish(args.uri, *publish_args, **publish_kwargs)
            if ack is not None:
                return await ack
            else:
                return None

    publish_args, publish_kwargs = libwampli.parse_args(args.args)
    _run_cmd(cmd)


def _subscribe_cmd(args: argparse.Namespace) -> None:
    """Subscribe command."""

    def on_event(event: aiowamp.SubscriptionEventABC) -> None:
        print(libwampli.format_args_mixin(event))

    async def cmd() -> None:
        async with get_client_context(args) as client:
            coro_gen = (client.subscribe(uri, on_event) for uri in args.uri)
            await asyncio.gather(*coro_gen)
            print(f"subscribed to {len(args.uri)} topic(s)")

            # TODO wait for client to close!
            await asyncio.get_running_loop().create_future()

    _run_cmd(cmd)


def _shell_cmd(args: argparse.Namespace) -> None:
    """Shell command.

    Creates a new `wampli.Shell` and runs it.
    """
    shell = wampli.Shell(get_connection_config(args))
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
