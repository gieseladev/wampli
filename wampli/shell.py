import asyncio
import cmd
import dataclasses
import io
import queue
import re
import shlex
import textwrap
import threading
import tokenize
from typing import Any, Dict, Iterable, List, Mapping, MutableSequence, NoReturn, Optional, Pattern, Tuple, Union

import txaio
import yaml
from autobahn.asyncio.component import Component
from autobahn.wamp import ApplicationError

import wampli

__all__ = ["Shell", "parse_args"]

# match: wamp.session.get(12345, key=value)
RE_FUNCTION_STYLE: Pattern = re.compile(
    r"""^
      ((?: (?: [0-9a-z_]+\. ) | \. )* (?: [0-9a-z_]+ )?)    # match URI (1)
      \s?
      \(
        (.*)                                                # arguments (2)
      \)
    $""",
    re.VERBOSE,
)

# match: key=value
RE_KWARGS_MATCH: Pattern = re.compile(r"^([a-z][a-z0-9_]{2,})\s*=(.*)$")


def parse_arg_value(val: str) -> Any:
    """Parse a string value into its Python representation."""
    return yaml.safe_load(val)


def split_function_style(text: str) -> List[str]:
    """Split a function style call text representation into its arguments.

    Returns:
        Empty list if the given string didn't match the function style,
        otherwise a list with at least the URI as its first item.
    """
    match = RE_FUNCTION_STYLE.match(text)
    if match is None:
        return []

    uri, arg_string = match.groups()
    args = [uri]

    if arg_string:
        token_gen = tokenize.generate_tokens(io.StringIO(arg_string).readline)
        # get the indices of the commas in the string
        commapos = (
            -1,
            *(token.end[1] for token in token_gen if token.string == ","),
            len(arg_string) + 1,
        )

        args.extend([
            arg_string[commapos[i] + 1: commapos[i + 1] - 1]
            for i in range(len(commapos) - 1)
        ])

    return args


def split_arg_string(arg: str) -> List[str]:
    """Split an argument string into its arguments"""
    res = split_function_style(arg)
    return res or shlex.split(arg)


def parse_args(args: Union[Iterable[str], str]) -> Tuple[List[Any], Dict[str, Any]]:
    """Parse string arguments into their Python representation.

    Returns:
        2-tuple (args, kwargs) where the first item is a `list` containing
        the positional arguments and the second item a `dict` containing
        the keyword arguments (key=value).
    """
    if isinstance(args, str):
        args = split_arg_string(args)

    _args: List[Any] = []
    _kwargs: Dict[str, Any] = {}

    for arg in args:
        match = RE_KWARGS_MATCH.match(arg)

        if match is None:
            _args.append(parse_arg_value(arg))
        else:
            key, value = match.groups()
            _kwargs[key] = parse_arg_value(value)

    return _args, _kwargs


# special signal to indicate that the worker thread should stop
STOP_SIGNAL = object()


@dataclasses.dataclass()
class Task:
    action: str
    args: Iterable[Any] = dataclasses.field(default_factory=list)
    kwargs: Mapping[str, Any] = dataclasses.field(default_factory=dict)


def worker(component: Component, receive: queue.Queue, send: queue.Queue) -> None:
    """Thread worker which performs async tasks.

    You can send `STOP_SIGNAL` to the `receive` queue to stop the worker.

    Args:
        component: WAMP Component to use
        receive: Queue to get new tasks from.
            As soon as the worker is running it will pull `Task` instances
            from the queue and execute them. Each time a task is finished
            `queue.Queue.task_done()` is called.
            The special "task" `STOP_SIGNAL` stops the worker.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    txaio.config.loop = loop

    async def handle_task(task: Task) -> None:
        session = await wampli.get_session(component, loop=loop)

        if task.action == "call":
            try:
                result = await session.call(*task.args, **task.kwargs)
            except ApplicationError as e:
                print(e.error_message())
            else:
                print(result)
        elif task.action == "publish":
            ack = session.publish(*task.args, **task.kwargs)
            if ack is not None:
                await ack

            print("done")
        else:
            print(f"unknown task given to worker: {task}")

    async def runner() -> NoReturn:
        async def _handle_task(_task: Task) -> None:
            try:
                await handle_task(_task)
            finally:
                receive.task_done()

        while True:
            task = await loop.run_in_executor(None, receive.get)

            if task is STOP_SIGNAL:
                print("stopping worker")
                break
            else:
                loop.create_task(_handle_task(task))

        this_task = asyncio.current_task()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            if task is not this_task:
                task.cancel()

    loop.run_until_complete(runner())
    loop.close()


# TODO subscribe
# TODO alias uri

class Shell(cmd.Cmd):
    intro = textwrap.dedent("""
        Type 'help' or '?' to list all commands. 
        Use 'exit' to exit the shell.
    """).strip()

    prompt = "(WAMPli) "

    _component: Component

    _send_queue: queue.Queue
    _receive_queue: queue.Queue
    _worker_thread: Optional[threading.Thread]

    def __init__(self, component: Component) -> None:
        super().__init__()

        self._component = component

        self._send_queue = queue.Queue()
        self._receive_queue = queue.Queue()

    @property
    def worker_running(self) -> bool:
        return self._worker_thread and self._worker_thread.is_alive()

    def run(self) -> None:
        self._start_worker()

        try:
            self.cmdloop()
        finally:
            self._stop_worker()

    def _start_worker(self) -> None:
        thread = threading.Thread(
            name="Shell worker",
            target=worker,
            args=(self._component, self._send_queue, self._receive_queue)
        )

        self._worker_thread = thread
        self._worker_thread.start()

    def _stop_worker(self) -> None:
        if self.worker_running:
            self._send_queue.put(STOP_SIGNAL)
            self._worker_thread.join(timeout=20)

    def do_exit(self, _) -> bool:
        """Exit the shell."""
        print("Goodbye")
        return True

    def default(self, line: str) -> None:
        args = split_function_style(line)
        if args:
            args, kwargs = parse_args(args)
            self._call(args, kwargs)
        else:
            super().default(line)

    def _call(self, args, kwargs) -> None:
        _ready_uri(args)

        task = Task("call", args, kwargs)
        self._send_queue.put_nowait(task)

    def do_call(self, arg: str) -> None:
        """Call a procedure."""
        args, kwargs = parse_args(arg)
        self._call(args, kwargs)

    def complete_call(self, text: str, line: str, begidx: int, endidx: int) -> List[str]:
        print(text, line, begidx, endidx)
        return []

    def do_publish(self, arg: str):
        """Publish to a topic."""
        args, kwargs = parse_args(arg)
        _ready_uri(args)

        task = Task("publish", args, kwargs)
        self._send_queue.put_nowait(task)


def _ready_uri(args: MutableSequence[Any]) -> None:
    try:
        uri = args[0]
    except IndexError:
        raise IndexError("Please provide a URI")

    if not isinstance(uri, str):
        raise TypeError("URI must be a string")

    args[0] = uri
