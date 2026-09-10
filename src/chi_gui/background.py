"""Thread worker that communicates only through a thread-safe queue."""

from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    kind: str
    payload: Any = None


WorkerTarget = Callable[[Event, Callable[[Any], None]], Any]


class BackgroundRunner:
    """One cooperative worker; Tk code polls ``events`` on the main thread."""

    def __init__(self) -> None:
        self.events: Queue[WorkerEvent] = Queue()
        self._cancel = Event()
        self._thread: Thread | None = None
        self._lock = Lock()

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, target: WorkerTarget) -> None:
        with self._lock:
            if self.busy:
                raise RuntimeError("已有后台任务正在运行。")
            self._cancel.clear()
            self._thread = Thread(target=self._run, args=(target,), daemon=False)
            self._thread.start()

    def _run(self, target: WorkerTarget) -> None:
        self.events.put(WorkerEvent("started"))
        try:
            result = target(self._cancel, lambda value: self.events.put(WorkerEvent("progress", value)))
        except Exception as error:  # worker boundary must preserve GUI process
            self.events.put(WorkerEvent("error", error))
        else:
            self.events.put(WorkerEvent("result", result))
        finally:
            self.events.put(WorkerEvent("finished", self._cancel.is_set()))

    def request_cancel(self) -> None:
        self._cancel.set()

    def drain(self) -> tuple[WorkerEvent, ...]:
        drained = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except Empty:
                return tuple(drained)

    def join(self, timeout: float | None = None) -> bool:
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()
