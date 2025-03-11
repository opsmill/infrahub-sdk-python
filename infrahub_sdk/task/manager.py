from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ..graphql import Query
from .constants import FINAL_STATES
from .exceptions import TaskNotCompletedError, TaskNotFoundError, TooManyTasksError
from .models import Task, TaskFilter

if TYPE_CHECKING:
    from ..client import InfrahubClient, InfrahubClientSync


class InfraHubTaskManagerBase:
    @classmethod
    def _generate_query(
        cls,
        filters: TaskFilter | None = None,
        include_logs: bool = False,
        include_related_nodes: bool = False,
        offset: int | None = None,
        limit: int | None = None,
        count: bool = False,
    ) -> Query:
        query: dict[str, Any] = {
            "InfrahubTask": {
                "edges": {
                    "node": {
                        "id": None,
                        "title": None,
                        "state": None,
                        "progress": None,
                        "workflow": None,
                        "branch": None,
                        "created_at": None,
                        "updated_at": None,
                    }
                }
            }
        }

        if not filters and (offset or limit):
            filters = TaskFilter(offset=offset, limit=limit)
        elif filters and offset:
            filters.offset = offset
        elif filters and limit:
            filters.limit = limit

        if filters:
            query["InfrahubTask"]["@filters"] = filters.to_dict()

        if count:
            query["InfrahubTask"]["count"] = None

        if include_logs:
            query["InfrahubTask"]["edges"]["node"]["logs"] = {
                "edges": {
                    "node": {
                        "message": None,
                        "severity": None,
                        "timestamp": None,
                    }
                }
            }

        if include_related_nodes:
            query["InfrahubTask"]["edges"]["node"]["related_nodes"] = {"id": None, "kind": None}

        return Query(query=query)

    @classmethod
    def _generate_count_query(cls, filters: TaskFilter | None = None) -> Query:
        query: dict[str, Any] = {
            "InfrahubTask": {
                "count": None,
            }
        }
        if filters:
            query["InfrahubTask"]["@filters"] = filters.to_dict()

        return Query(query=query)


class InfrahubTaskManager(InfraHubTaskManagerBase):
    client: InfrahubClient

    def __init__(self, client: InfrahubClient):
        self.client = client

    async def count(self, filters: TaskFilter | None = None) -> int:
        """Count the number of tasks.

        Args:
            filters: The filter to apply to the tasks. Defaults to None.

        Returns:
            The number of tasks.
        """

        query = self._generate_count_query(filters=filters)
        response = await self.client.execute_graphql(
            query=query.render(convert_enum=False), tracker="query-tasks-count"
        )
        return int(response["InfrahubTask"]["count"])

    async def all(
        self,
        limit: int | None = None,
        offset: int | None = None,
        timeout: int | None = None,
        parallel: bool = False,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Get all tasks.

        Args:
            limit: The maximum number of tasks to return. Defaults to None.
            offset: The offset to start the tasks from. Defaults to None.
            timeout: The timeout to wait for the tasks to complete. Defaults to None.
            parallel: Whether to query the tasks in parallel. Defaults to False.
            include_logs: Whether to include the logs in the tasks. Defaults to False.
            include_related_nodes: Whether to include the related nodes in the tasks. Defaults to False.

        Returns:
            A list of tasks.
        """

        return await self.filter(
            limit=limit,
            offset=offset,
            timeout=timeout,
            parallel=parallel,
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
        )

    async def filter(
        self,
        filter: TaskFilter | None = None,
        limit: int | None = None,
        offset: int | None = None,
        timeout: int | None = None,
        parallel: bool = False,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Filter tasks.

        Args:
            filter: The filter to apply to the tasks. Defaults to None.
            limit: The maximum number of tasks to return. Defaults to None.
            offset: The offset to start the tasks from. Defaults to None.
            timeout: The timeout to wait for the tasks to complete. Defaults to None.
            parallel: Whether to query the tasks in parallel. Defaults to False.
            include_logs: Whether to include the logs in the tasks. Defaults to False.
            include_related_nodes: Whether to include the related nodes in the tasks. Defaults to False.

        Returns:
            A list of tasks.
        """
        if filter is None:
            filter = TaskFilter()

        if limit:
            tasks, _ = await self.process_page(
                self.client, self._generate_query(filters=filter, offset=offset, limit=limit, count=False), 1, timeout
            )
            return tasks

        if parallel:
            return await self.process_batch(
                filters=filter,
                timeout=timeout,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
            )

        return await self.process_non_batch(
            filters=filter,
            offset=offset,
            limit=limit,
            timeout=timeout,
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
        )

    async def get(self, id: str, include_logs: bool = False, include_related_nodes: bool = False) -> Task:
        tasks = await self.filter(
            filter=TaskFilter(ids=[id]),
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
            parallel=False,
        )
        if not tasks:
            raise TaskNotFoundError(id=id)

        if len(tasks) != 1:
            raise TooManyTasksError(expected_id=id, received_ids=[task.id for task in tasks])

        return tasks[0]

    async def wait_for_completion(self, id: str, interval: int = 1, timeout: int = 60) -> Task:
        """Wait for a task to complete.

        Args:
            id: The id of the task to wait for.
            interval: The interval to check the task state. Defaults to 1.
            timeout: The timeout to wait for the task to complete. Defaults to 60.

        Raises:
            TaskNotCompletedError: The task did not complete in the given timeout.

        Returns:
            The task object.
        """
        for _ in range(timeout // interval):
            task = await self.get(id=id)
            if task.state in FINAL_STATES:
                return task
            await asyncio.sleep(interval)
        raise TaskNotCompletedError(id=id, message=f"Task {id} did not complete in {timeout} seconds")

    @staticmethod
    async def process_page(
        client: InfrahubClient, query: Query, page_number: int, timeout: int | None = None
    ) -> tuple[list[Task], int | None]:
        """Process a single page of results.

        Args:
            client: The client to use to execute the query.
            query: The query to execute.
            page_number: The page number to process.
            timeout: The timeout to wait for the query to complete. Defaults to None.

        Returns:
            A tuple containing a list of tasks and the count of tasks.
        """

        response = await client.execute_graphql(
            query=query.render(convert_enum=False),
            tracker=f"query-tasks-page{page_number}",
            timeout=timeout,
        )
        count = response["InfrahubTask"].get("count", None)
        return [Task.from_graphql(task["node"]) for task in response["InfrahubTask"]["edges"]], count

    async def process_batch(
        self,
        filters: TaskFilter | None = None,
        timeout: int | None = None,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Process queries in parallel mode."""
        pagination_size = self.client.pagination_size
        tasks = []
        batch_process = await self.client.create_batch()
        count = await self.count(filters=filters)
        total_pages = (count + pagination_size - 1) // pagination_size

        for page_number in range(1, total_pages + 1):
            page_offset = (page_number - 1) * pagination_size
            query = self._generate_query(
                filters=filters,
                offset=page_offset,
                limit=pagination_size,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
                count=False,
            )
            batch_process.add(
                task=self.process_page, client=self.client, query=query, page_number=page_number, timeout=timeout
            )

        async for _, (new_tasks, _) in batch_process.execute():
            tasks.extend(new_tasks)

        return tasks

    async def process_non_batch(
        self,
        filters: TaskFilter | None = None,
        offset: int | None = None,
        limit: int | None = None,
        timeout: int | None = None,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Process queries without parallel mode."""
        tasks = []
        has_remaining_items = True
        page_number = 1

        while has_remaining_items:
            page_offset = (page_number - 1) * self.client.pagination_size
            query = self._generate_query(
                filters=filters,
                offset=page_offset,
                limit=self.client.pagination_size,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
                count=True,
            )
            new_tasks, count = await self.process_page(
                client=self.client, query=query, page_number=page_number, timeout=timeout
            )
            if count is None:
                raise ValueError("Count is None, a value must be retrieve from the query")

            tasks.extend(new_tasks)
            remaining_items = count - (page_offset + self.client.pagination_size)
            if remaining_items < 0 or offset is not None or limit is not None:
                has_remaining_items = False
            page_number += 1
        return tasks


class InfrahubTaskManagerSync(InfraHubTaskManagerBase):
    client: InfrahubClientSync

    def __init__(self, client: InfrahubClientSync):
        self.client = client

    def count(self, filters: TaskFilter | None = None) -> int:
        """Count the number of tasks.

        Args:
            filters: The filter to apply to the tasks. Defaults to None.

        Returns:
            The number of tasks.
        """

        query = self._generate_count_query(filters=filters)
        response = self.client.execute_graphql(query=query.render(convert_enum=False), tracker="query-tasks-count")
        return int(response["InfrahubTask"]["count"])

    def all(
        self,
        limit: int | None = None,
        offset: int | None = None,
        timeout: int | None = None,
        parallel: bool = False,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Get all tasks.

        Args:
            limit: The maximum number of tasks to return. Defaults to None.
            offset: The offset to start the tasks from. Defaults to None.
            timeout: The timeout to wait for the tasks to complete. Defaults to None.
            parallel: Whether to query the tasks in parallel. Defaults to False.
            include_logs: Whether to include the logs in the tasks. Defaults to False.
            include_related_nodes: Whether to include the related nodes in the tasks. Defaults to False.

        Returns:
            A list of tasks.
        """

        return self.filter(
            limit=limit,
            offset=offset,
            timeout=timeout,
            parallel=parallel,
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
        )

    def filter(
        self,
        filter: TaskFilter | None = None,
        limit: int | None = None,
        offset: int | None = None,
        timeout: int | None = None,
        parallel: bool = False,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Filter tasks.

        Args:
            filter: The filter to apply to the tasks. Defaults to None.
            limit: The maximum number of tasks to return. Defaults to None.
            offset: The offset to start the tasks from. Defaults to None.
            timeout: The timeout to wait for the tasks to complete. Defaults to None.
            parallel: Whether to query the tasks in parallel. Defaults to False.
            include_logs: Whether to include the logs in the tasks. Defaults to False.
            include_related_nodes: Whether to include the related nodes in the tasks. Defaults to False.

        Returns:
            A list of tasks.
        """
        if filter is None:
            filter = TaskFilter()

        if limit:
            tasks, _ = self.process_page(
                self.client, self._generate_query(filters=filter, offset=offset, limit=limit, count=False), 1, timeout
            )
            return tasks

        if parallel:
            return self.process_batch(
                filters=filter,
                timeout=timeout,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
            )

        return self.process_non_batch(
            filters=filter,
            offset=offset,
            limit=limit,
            timeout=timeout,
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
        )

    def get(self, id: str, include_logs: bool = False, include_related_nodes: bool = False) -> Task:
        tasks = self.filter(
            filter=TaskFilter(ids=[id]),
            include_logs=include_logs,
            include_related_nodes=include_related_nodes,
            parallel=False,
        )
        if not tasks:
            raise TaskNotFoundError(id=id)

        if len(tasks) != 1:
            raise TooManyTasksError(expected_id=id, received_ids=[task.id for task in tasks])

        return tasks[0]

    def wait_for_completion(self, id: str, interval: int = 1, timeout: int = 60) -> Task:
        """Wait for a task to complete.

        Args:
            id: The id of the task to wait for.
            interval: The interval to check the task state. Defaults to 1.
            timeout: The timeout to wait for the task to complete. Defaults to 60.

        Raises:
            TaskNotCompletedError: The task did not complete in the given timeout.

        Returns:
            The task object.
        """
        for _ in range(timeout // interval):
            task = self.get(id=id)
            if task.state in FINAL_STATES:
                return task
            time.sleep(interval)
        raise TaskNotCompletedError(id=id, message=f"Task {id} did not complete in {timeout} seconds")

    @staticmethod
    def process_page(
        client: InfrahubClientSync, query: Query, page_number: int, timeout: int | None = None
    ) -> tuple[list[Task], int | None]:
        """Process a single page of results.

        Args:
            client: The client to use to execute the query.
            query: The query to execute.
            page_number: The page number to process.
            timeout: The timeout to wait for the query to complete. Defaults to None.

        Returns:
            A tuple containing a list of tasks and the count of tasks.
        """

        response = client.execute_graphql(
            query=query.render(convert_enum=False),
            tracker=f"query-tasks-page{page_number}",
            timeout=timeout,
        )
        count = response["InfrahubTask"].get("count", None)
        return [Task.from_graphql(task["node"]) for task in response["InfrahubTask"]["edges"]], count

    def process_batch(
        self,
        filters: TaskFilter | None = None,
        timeout: int | None = None,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Process queries in parallel mode."""
        pagination_size = self.client.pagination_size
        tasks = []
        batch_process = self.client.create_batch()
        count = self.count(filters=filters)
        total_pages = (count + pagination_size - 1) // pagination_size

        for page_number in range(1, total_pages + 1):
            page_offset = (page_number - 1) * pagination_size
            query = self._generate_query(
                filters=filters,
                offset=page_offset,
                limit=pagination_size,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
                count=False,
            )
            batch_process.add(
                task=self.process_page, client=self.client, query=query, page_number=page_number, timeout=timeout
            )

        for _, (new_tasks, _) in batch_process.execute():
            tasks.extend(new_tasks)

        return tasks

    def process_non_batch(
        self,
        filters: TaskFilter | None = None,
        offset: int | None = None,
        limit: int | None = None,
        timeout: int | None = None,
        include_logs: bool = False,
        include_related_nodes: bool = False,
    ) -> list[Task]:
        """Process queries without parallel mode."""
        tasks = []
        has_remaining_items = True
        page_number = 1

        while has_remaining_items:
            page_offset = (page_number - 1) * self.client.pagination_size
            query = self._generate_query(
                filters=filters,
                offset=page_offset,
                limit=self.client.pagination_size,
                include_logs=include_logs,
                include_related_nodes=include_related_nodes,
                count=True,
            )
            new_tasks, count = self.process_page(
                client=self.client, query=query, page_number=page_number, timeout=timeout
            )
            if count is None:
                raise ValueError("Count is None, a value must be retrieve from the query")

            tasks.extend(new_tasks)
            remaining_items = count - (page_offset + self.client.pagination_size)
            if remaining_items < 0 or offset is not None or limit is not None:
                has_remaining_items = False
            page_number += 1
        return tasks
