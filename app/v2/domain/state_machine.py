from enum import Enum


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class InvalidStateTransition(ValueError):
    pass


RUN_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED},
    RunStatus.RUNNING: {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED},
    RunStatus.COMPLETED: set(),
    RunStatus.FAILED: set(),
    RunStatus.CANCELLED: set(),
}

STEP_TRANSITIONS = {
    StepStatus.PENDING: {StepStatus.RUNNING, StepStatus.CANCELLED},
    StepStatus.RUNNING: {StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.COMPLETED: set(),
    StepStatus.FAILED: set(),
    StepStatus.CANCELLED: set(),
}


def _transition(current, target, allowed):
    if current == target and current in {
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        StepStatus.COMPLETED,
        StepStatus.FAILED,
        StepStatus.CANCELLED,
    }:
        return current
    if target not in allowed[current]:
        raise InvalidStateTransition(f"invalid transition: {current.value} -> {target.value}")
    return target


def transition_run(current: RunStatus, target: RunStatus) -> RunStatus:
    return _transition(current, target, RUN_TRANSITIONS)


def transition_step(current: StepStatus, target: StepStatus) -> StepStatus:
    return _transition(current, target, STEP_TRANSITIONS)
