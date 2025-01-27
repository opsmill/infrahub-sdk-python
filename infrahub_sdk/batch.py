from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .node import InfrahubNode, InfrahubNodeSync


@dataclass
class BatchTask:
    task: Callable[[Any], Awaitable[Any]]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    node: Any | None = None


@dataclass
class BatchTaskSync:
    task: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    node: InfrahubNodeSync | None = None

    def execute(self, return_exceptions: bool = False) -> tuple[InfrahubNodeSync | None, Any]:
        """Executes the stored task."""
        result = None
        try:
            result = self.task(*self.args, **self.kwargs)
        except Exception as exc:
            if return_exceptions:
                return self.node, exc
            raise exc

        return self.node, result


async def execute_batch_task_in_pool(
    task: BatchTask, semaphore: asyncio.Semaphore, return_exceptions: bool = False
) -> tuple[InfrahubNode | None, Any]:
    async with semaphore:
        try:
            result = await task.task(*task.args, **task.kwargs)
        except Exception as exc:
            if return_exceptions:
                return (task.node, exc)
            raise exc

        return (task.node, result)


class InfrahubBatch:
    def __init__(
        self,
        semaphore: asyncio.Semaphore | None = None,
        max_concurrent_execution: int = 5,
        return_exceptions: bool = False,
    ):
        self._tasks: list[BatchTask] = []
        self.semaphore = semaphore or asyncio.Semaphore(value=max_concurrent_execution)
        self.return_exceptions = return_exceptions

    @property
    def num_tasks(self) -> int:
        return len(self._tasks)

    def add(self, *args: Any, task: Callable, node: Any | None = None, **kwargs: Any) -> None:
        self._tasks.append(BatchTask(task=task, node=node, args=args, kwargs=kwargs))

    async def execute(self) -> AsyncGenerator:
        tasks = []

        for batch_task in self._tasks:
            tasks.append(
                asyncio.create_task(
                    execute_batch_task_in_pool(
                        task=batch_task, semaphore=self.semaphore, return_exceptions=self.return_exceptions
                    )
                )
            )

        for completed_task in asyncio.as_completed(tasks):
            node, result = await completed_task
            if isinstance(result, Exception) and not self.return_exceptions:
                raise result
            yield node, result


class InfrahubBatchSync:
    def __init__(self, max_concurrent_execution: int = 5, return_exceptions: bool = False):
        self._tasks: list[BatchTaskSync] = []
        self.max_concurrent_execution = max_concurrent_execution
        self.return_exceptions = return_exceptions

    @property
    def num_tasks(self) -> int:
        return len(self._tasks)

    def add(self, *args: Any, task: Callable[..., Any], node: Any | None = None, **kwargs: Any) -> None:
        self._tasks.append(BatchTaskSync(task=task, node=node, args=args, kwargs=kwargs))

    def execute(self) -> Generator[tuple[InfrahubNodeSync | None, Any], None, None]:
        with ThreadPoolExecutor(max_workers=self.max_concurrent_execution) as executor:
            futures = [executor.submit(task.execute, return_exceptions=self.return_exceptions) for task in self._tasks]
            for future in futures:
                node, result = future.result()
                if isinstance(result, Exception) and not self.return_exceptions:
                    raise result
                yield node, result
