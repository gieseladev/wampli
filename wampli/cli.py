import argparse
import asyncio
from typing import Any, Dict, Iterable, List, Tuple, Callable

from autobahn.wamp import ISession

import wampli


def parse_args(args: Iterable[str]) -> Tuple[List[Any], Dict[str, Any]]:
    return [], {}


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

    def add_procedure_argument(p) -> None:
        p.add_argument("procedure", help="uri of the procedure to call")

    def add_procedure_args_arguments(p) -> None:
        add_procedure_argument(p)
        p.add_argument("args", action="append", help="arguments to provide to the callee", nargs="*")

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
    add_procedure_argument(subscribe)

    shell = subparsers.add_parser("shell", help="start the interactive shell")
    shell.set_defaults(entrypoint_func=_shell_cmd)

    return parser


async def _get_session(args: argparse.Namespace, *, loop: asyncio.AbstractEventLoop) -> ISession:
    c = wampli.create_component(args.realm)
    return await wampli.get_session(c, loop=loop)


def _run_async_cmd(cmd: Callable[[asyncio.AbstractEventLoop], Any]) -> Any:
    loop = asyncio.get_event_loop()
    result = loop.run_until_complete(cmd(loop))

    return result


def _call_cmd(args: argparse.Namespace) -> None:
    async def cmd(loop: asyncio.AbstractEventLoop) -> None:
        session = await _get_session(args, loop=loop)
        return await session.call(args.procedure, *call_args, **call_kwargs)

    call_args, call_kwargs = parse_args(args.args)
    result = _run_async_cmd(cmd)

    print("le call", result)


def _publish_cmd(args: argparse.Namespace) -> None:
    async def cmd(loop: asyncio.AbstractEventLoop) -> None:
        session = await _get_session(args, loop=loop)
        return await session.publish(args.procedure, *publish_args, **publish_kwargs)

    publish_args, publish_kwargs = parse_args(args.args)
    result = _run_async_cmd(cmd)

    print("le publish", result)


def _subscribe_cmd(args: argparse.Namespace) -> None:
    print("le subscribe", args)


def _shell_cmd(args: argparse.Namespace) -> None:
    print("le shell", args)


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
