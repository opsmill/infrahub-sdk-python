from .models import TaskState

FINAL_STATES = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED, TaskState.CRASHED]
