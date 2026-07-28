import pytest

from app.v2.domain.state_machine import (
    InvalidStateTransition,
    RunStatus,
    StepStatus,
    transition_run,
    transition_step,
)


def test_run_happy_path_reaches_completed():
    status = transition_run(RunStatus.QUEUED, RunStatus.RUNNING)
    assert transition_run(status, RunStatus.COMPLETED) is RunStatus.COMPLETED


@pytest.mark.parametrize("start", [RunStatus.QUEUED, RunStatus.RUNNING])
def test_active_run_can_be_cancelled(start):
    assert transition_run(start, RunStatus.CANCELLED) is RunStatus.CANCELLED


def test_running_run_can_fail():
    assert transition_run(RunStatus.RUNNING, RunStatus.FAILED) is RunStatus.FAILED


@pytest.mark.parametrize(
    "terminal",
    [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED],
)
def test_terminal_run_cannot_transition(terminal):
    with pytest.raises(InvalidStateTransition):
        transition_run(terminal, RunStatus.RUNNING)


def test_step_state_machine_enforces_terminal_states():
    running = transition_step(StepStatus.PENDING, StepStatus.RUNNING)
    assert transition_step(running, StepStatus.COMPLETED) is StepStatus.COMPLETED
    with pytest.raises(InvalidStateTransition):
        transition_step(StepStatus.COMPLETED, StepStatus.RUNNING)
