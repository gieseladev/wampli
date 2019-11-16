"""Interactive Shell for WAMPli.

Provides a worker thread which runs the `libwampli.Connection` in the
background while the actual shell runs in the foreground.
"""

import asyncio
import cmd
import dataclasses
import queue
import textwrap
import threading
from typing import Any, Dict, Iterable, Mapping, NoReturn, Optional

import aiowamp

import libwampli

__all__ = ["Task", "STOP_SIGNAL", "worker",
           "Shell"]

# special signal to indicate that the worker thread should stop
STOP_SIGNAL = object()


@dataclasses.dataclass()
class Task:
    """Task to be executed by a `worker`.

    Meaning of `args` and `kwargs` depend on the `action`.

    Attributes:
        action (str): Action to perform.
        args (Iterable[Any]): Arguments for the action.
        kwargs (Mapping[str, Any]): Keyword arguments for the action.
    """
    action: str
    args: Iterable[Any] = dataclasses.field(default_factory=list)
    kwargs: Dict[str, Any] = dataclasses.field(default_factory=dict)


def worker(config: libwampli.ConnectionConfig, receive: queue.Queue) -> None:
    """Thread worker which performs async tasks.

    You can send `STOP_SIGNAL` to the `receive` queue to stop the worker.

    Tasks:
        call: args and kwargs are passed to `autobahn.wamp.ISession.call`.
        publish: args and kwargs are passed to `autobahn.wamp.ISession.publish`.
        subscribe: subscribe to a topic. The first item in args is used as the
            topic.
        unsubscribe: Unsubscribe from a topic. The first item in args is used as
            the topic.

    Args:
        config: Connection config to create the connection from
        receive: Queue to get new tasks from.
            As soon as the worker is running it will pull `Task` instances
            from the queue and execute them. Each time a task is finished
            `queue.Queue.task_done()` is called.
            The special "task" `STOP_SIGNAL` stops the worker.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    client: Optional[aiowamp.ClientABC] = None
    client_task = loop.create_task(aiowamp.connect(config.endpoint, realm=config.realm))

    async def on_subscription_event(event: aiowamp.SubscriptionEventABC) -> None:
        print(f"received event:\n{libwampli.format_args_mixin(event)}")

    async def handle_task(task: Task) -> None:
        nonlocal client
        assert client

        if task.action == "call":
            try:
                result = await client.call(*task.args, kwargs=task.kwargs)
            except aiowamp.ErrorResponse as e:
                print(e)
            else:
                print(libwampli.human_result(result))
        elif task.action == "publish":
            ack = client.publish(*task.args, kwargs=task.kwargs)
            if ack is not None:
                await ack

            print("done")
        elif task.action == "subscribe":
            try:
                topic = next(iter(task.args))
            except StopIteration:
                print("no topic provided")
            else:
                await client.subscribe(topic, on_subscription_event)
        elif task.action == "unsubscribe":
            try:
                topic = next(iter(task.args))
            except StopIteration:
                print("no topic provided")
            else:
                await client.unsubscribe(topic)
        else:
            print(f"unknown task given to worker: {task}")

    async def runner() -> NoReturn:
        nonlocal client

        print("connecting...")
        client = await client_task
        print("connected")

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

        print("waiting for connection to close!")
        await client.close()

        this_task = asyncio.current_task()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            if task is not this_task:
                task.cancel()

    loop.run_until_complete(runner())
    loop.close()


# TODO alias uri

class Shell(cmd.Cmd):
    """Interactive shell for WAMP.

    Args:
        config: Config to use to create the `libwampli.Connection`.
    """
    intro = textwrap.dedent("""
        Type 'help' or '?' to list all commands. 
        Use 'exit' to exit the shell.
    """).strip()

    prompt = "(WAMPli) "

    _connection_config: libwampli.ConnectionConfig

    _send_queue: queue.Queue
    _receive_queue: queue.Queue
    _worker_thread: Optional[threading.Thread]

    def __init__(self, config: libwampli.ConnectionConfig) -> None:
        super().__init__()

        self._connection_config = config

        self._send_queue = queue.Queue()
        self._receive_queue = queue.Queue()

    @property
    def worker_running(self) -> bool:
        """Whether the worker thread is running."""
        return self._worker_thread and self._worker_thread.is_alive()

    def run(self) -> None:
        """Run the shell..

        This means starting the worker thread and entering
        the shell loop until the user exits.
        This function blocks until the shell loop is completed.
        """
        self._start_worker()

        try:
            self.cmdloop()
        finally:
            self._stop_worker()

    def _start_worker(self) -> None:
        thread = threading.Thread(
            name="Shell worker",
            target=worker,
            args=(self._connection_config, self._send_queue),
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
        """Default command used when no other command matches.

        This detects special function style calls which are then treated
        as if they were call commands.
        Otherwise the base class' method is used.
        """
        args = libwampli.split_function_style(line)
        if args:
            args, kwargs = libwampli.parse_args(args)
            self._call(args, kwargs)
        else:
            super().default(line)

    def _call(self, args, kwargs) -> None:
        libwampli.ready_uri(args)

        task = Task("call", args, kwargs)
        self._send_queue.put_nowait(task)

    def do_call(self, arg: str) -> None:
        """Call a procedure."""
        args, kwargs = libwampli.parse_args(arg)
        self._call(args, kwargs)

    def do_publish(self, arg: str) -> None:
        """Publish to a topic."""
        args, kwargs = libwampli.parse_args(arg)
        libwampli.ready_uri(args)

        task = Task("publish", args, kwargs)
        self._send_queue.put_nowait(task)

    def do_subscribe(self, arg: str) -> None:
        """Subscribe to a topic"""
        args = [arg]
        libwampli.ready_uri(args)

        task = Task("subscribe", args)
        self._send_queue.put_nowait(task)

    def do_unsubscribe(self, arg: str) -> None:
        """Unsubscribe from a topic"""
        args = [arg]
        libwampli.ready_uri(args)

        task = Task("unsubscribe", args)
        self._send_queue.put_nowait(task)
