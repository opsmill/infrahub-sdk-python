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
    """Represents a single asynchronous task in a batch."""
    task: Callable[[Any], Awaitable[Any]]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    node: Any | None = None


@dataclass
class BatchTaskSync:
    """Represents a single synchronous task in a batch."""
    task: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    node: InfrahubNodeSync | None = None

    def execute(self, return_exceptions: bool = False) -> tuple[InfrahubNodeSync | None, Any]:
        """Executes the stored synchronous task.

        Args:
            return_exceptions: If True, exceptions are returned instead of raised.

        Returns:
            A tuple containing the task's node (if any) and the result or exception.

        Raises:
            Exception: If `return_exceptions` is False and the task raises an exception.
        """
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
    """Executes a BatchTask within a semaphore-controlled pool.

    Args:
        task: The BatchTask to execute.
        semaphore: An asyncio.Semaphore to limit concurrent executions.
        return_exceptions: If True, exceptions are returned instead of raised.

    Returns:
        A tuple containing the task's node (if any) and the result or exception.
    """
    async with semaphore:
        try:
            result = await task.task(*task.args, **task.kwargs)
        except Exception as exc:
            if return_exceptions:
                return (task.node, exc)
            raise exc

        return (task.node, result)


class InfrahubBatch:
    """Manages and executes a batch of asynchronous tasks concurrently."""
    def __init__(
        self,
        semaphore: asyncio.Semaphore | None = None,
        max_concurrent_execution: int = 5,
        return_exceptions: bool = False,
    ):
        """Initializes the InfrahubBatch.

        Args:
            semaphore: An asyncio.Semaphore to limit concurrent executions.
                       If None, a new one is created with `max_concurrent_execution`.
            max_concurrent_execution: The maximum number of tasks to run concurrently.
                                      Only used if `semaphore` is None.
            return_exceptions: If True, exceptions from tasks are returned instead of raised.
        """
        self._tasks: list[BatchTask] = []
        self.semaphore = semaphore or asyncio.Semaphore(value=max_concurrent_execution)
        self.return_exceptions = return_exceptions

    @property
    def num_tasks(self) -> int:
        """Returns the number of tasks currently in the batch."""
        return len(self._tasks)

    def add(self, *args: Any, task: Callable, node: Any | None = None, **kwargs: Any) -> None:
        """Adds a new task to the batch.

        Args:
            task: The callable to be executed.
            node: An optional node associated with this task.
            *args: Positional arguments to pass to the task.
            **kwargs: Keyword arguments to pass to the task.
        """
        self._tasks.append(BatchTask(task=task, node=node, args=args, kwargs=kwargs))

    async def execute(self) -> AsyncGenerator[tuple[InfrahubNode | None, Any], None, None]:
        """Executes all tasks in the batch concurrently.

        Yields:
            A tuple containing the task's node (if any) and the result or exception.

        Raises:
            Exception: If `return_exceptions` is False and a task raises an exception.
        """
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
    """Manages and executes a batch of synchronous tasks concurrently using a thread pool."""
    def __init__(self, max_concurrent_execution: int = 5, return_exceptions: bool = False):
        """Initializes the InfrahubBatchSync.

        Args:
            max_concurrent_execution: The maximum number of tasks to run concurrently in the thread pool.
            return_exceptions: If True, exceptions from tasks are returned instead of raised.
        """
        self._tasks: list[BatchTaskSync] = []
        self.max_concurrent_execution = max_concurrent_execution
        self.return_exceptions = return_exceptions

    @property
    def num_tasks(self) -> int:
        """Returns the number of tasks currently in the batch."""
        return len(self._tasks)

    def add(self, *args: Any, task: Callable[..., Any], node: Any | None = None, **kwargs: Any) -> None:
        """Adds a new synchronous task to the batch.

        Args:
            task: The callable to be executed.
            node: An optional node associated with this task.
            *args: Positional arguments to pass to the task.
            **kwargs: Keyword arguments to pass to the task.
        """
        self._tasks.append(BatchTaskSync(task=task, node=node, args=args, kwargs=kwargs))

    def execute(self) -> Generator[tuple[InfrahubNodeSync | None, Any], None, None]:
        """Executes all tasks in the batch concurrently using a ThreadPoolExecutor.

        Yields:
            A tuple containing the task's node (if any) and the result or exception.

        Raises:
            Exception: If `return_exceptions` is False and a task raises an exception.
        """
        with ThreadPoolExecutor(max_workers=self.max_concurrent_execution) as executor:
            futures = [executor.submit(task.execute, return_exceptions=self.return_exceptions) for task in self._tasks]
            for future in futures:
                node, result = future.result()
                if isinstance(result, Exception) and not self.return_exceptions:
                    raise result
                yield node, result
