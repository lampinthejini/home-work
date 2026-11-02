import pytest

from app.domain import status as st


def test_allowedTransitions():
    assert st.transition(st.READY, st.INTERVIEWING) == st.INTERVIEWING
    assert st.transition(st.INTERRUPTED, st.CODING) == st.CODING
    with pytest.raises(st.TransitionError):
        st.transition(st.COMPLETED, st.INTERVIEWING)
    with pytest.raises(st.TransitionError):
        st.transition(st.READY, st.COMPLETED)


def test_statusOnClose():
    assert st.statusOnClose(st.DRAFTING) == st.NOT_TAKEN_CLOSED
    assert st.statusOnClose(st.READY) == st.NOT_TAKEN_CLOSED
    assert st.statusOnClose(st.INTERVIEWING) == st.ENDED_CLOSED
    assert st.statusOnClose(st.INTERRUPTED) == st.ENDED_CLOSED
    assert st.statusOnClose(st.COMPLETED) is None


def test_judgeDisconnect():
    assert st.judgeDisconnect({"unload"}) == "not_fault"
    assert st.judgeDisconnect({"permission", "visibility"}) == "not_fault"
    assert st.judgeDisconnect(set()) == "fault"
    assert st.judgeDisconnect({"visibility"}) == "fault"


def test_nextAction():
    assert st.nextAction(st.READY, False) == "precheck"
    assert st.nextAction(st.INTERRUPTED, False) == "resume"
    assert st.nextAction(st.COMPLETED, False) is None
    assert st.nextAction(st.COMPLETED, True) == "view_result"
    assert st.nextAction(st.NOT_TAKEN_CLOSED, True) is None
