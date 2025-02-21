from __future__ import annotations


class TaskError(Exception):
    def __init__(self, message: str | None = None):
        self.message = message
        super().__init__(self.message)


class TaskNotFoundError(TaskError):
    def __init__(self, id: str):
        self.message = f"Task with id {id} not found"
        super().__init__(self.message)


class TooManyTasksError(TaskError):
    def __init__(self, expected_id: str, received_ids: list[str]):
        self.message = f"Expected 1 task with id {expected_id}, but got {len(received_ids)}"
        super().__init__(self.message)


class TaskNotCompletedError(TaskError):
    def __init__(self, id: str, message: str | None = None):
        self.message = message or f"Task with id {id} is not completed"
        super().__init__(self.message)
