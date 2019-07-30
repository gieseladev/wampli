import asyncio
import cmd
import dataclasses
import queue
import textwrap
import threading
from typing import Any, Iterable, Mapping, NoReturn, Optional

import txaio
from autobahn.wamp import ApplicationError

import libwampli

__all__ = ["Shell"]

# special signal to indicate that the worker thread should stop
STOP_SIGNAL = object()


@dataclasses.dataclass()
class Task:
    action: str
    args: Iterable[Any] = dataclasses.field(default_factory=list)
    kwargs: Mapping[str, Any] = dataclasses.field(default_factory=dict)


def worker(config: libwampli.ConnectionConfig, receive: queue.Queue) -> None:
    """Thread worker which performs async tasks.

    You can send `STOP_SIGNAL` to the `receive` queue to stop the worker.

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
    txaio.config.loop = loop

    connection = libwampli.Connection(config)

    async def on_subscription_event(event: libwampli.SubscriptionEvent) -> None:
        print(f"received event: {event}")

    connection.on(libwampli.SubscriptionEvent, on_subscription_event)

    async def handle_task(task: Task) -> None:
        session = await connection.session

        if task.action == "call":
            try:
                result = await session.call(*task.args, **task.kwargs)
            except ApplicationError as e:
                print(e.error_message())
            else:
                print(libwampli.human_result(result))
        elif task.action == "publish":
            ack = session.publish(*task.args, **task.kwargs)
            if ack is not None:
                await ack

            print("done")
        elif task.action == "subscribe":
            try:
                topic = next(iter(task.args))
            except StopIteration:
                print("no topic provided")
            else:
                if connection.has_subscription(topic):
                    print(f"already subscribed to {topic}")
                else:
                    await connection.add_subscription(topic)
        elif task.action == "unsubscribe":
            try:
                topic = next(iter(task.args))
            except StopIteration:
                print("no topic provided")
            else:
                if not connection.has_subscription(topic):
                    print(f"not subscribed to {topic}")
                else:
                    await connection.remove_subscription(topic)
        else:
            print(f"unknown task given to worker: {task}")

    async def runner() -> NoReturn:
        print("connecting...")
        await connection.open()
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
        await connection.close()

        this_task = asyncio.current_task()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            if task is not this_task:
                task.cancel()

    loop.run_until_complete(runner())
    loop.close()


# TODO alias uri

class Shell(cmd.Cmd):
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
