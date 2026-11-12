import pytest

from backend import call_engine


def test_simulated_call_lifecycle():
    call_engine.reset_calls()
    created = call_engine.create_call("1001", "1002")
    assert created["state"] == "RINGING"
    assert created["media"]["mode"] == "SIMULATED"

    answered = call_engine.answer_call(created["call_id"])
    assert answered["state"] == "ESTABLISHED"
    assert answered["answered_at"] is not None

    ended = call_engine.hangup_call(created["call_id"])
    assert ended["state"] == "ENDED"
    assert ended["ended_at"] is not None

    events = call_engine.get_events(created["call_id"])
    assert [event["event"] for event in events] == [
        "CALL_CREATED", "CALL_ANSWERED", "CALL_ENDED"
    ]
    call_engine.reset_calls()


def test_simulated_call_media_boundary():
    call_engine.reset_calls()
    created = call_engine.create_call("1001", "1002")
    assert created["state"] == "RINGING"
    assert created["media"]["mode"] == "SIMULATED"
    assert created["media"]["rtp_detected"] is False
    assert "No RTP packets or audio" in created["media"]["note"]
    call_engine.reset_calls()


def test_rejects_invalid_endpoints():
    call_engine.reset_calls()
    for from_extension, to_extension in [
        ("9999", "1002"),
        ("1001", "9999"),
        ("1001", "1001"),
    ]:
        with pytest.raises(ValueError):
            call_engine.create_call(from_extension, to_extension)
    assert call_engine.list_calls() == []


def test_rejects_invalid_call_state_transitions():
    call_engine.reset_calls()
    created = call_engine.create_call("1001", "1002")
    answered = call_engine.answer_call(created["call_id"])
    with pytest.raises(ValueError, match="Cannot answer call in state ESTABLISHED"):
        call_engine.answer_call(created["call_id"])

    call_engine.hangup_call(created["call_id"])
    with pytest.raises(ValueError, match="Cannot answer call in state ENDED"):
        call_engine.answer_call(created["call_id"])
    with pytest.raises(ValueError, match="already ended"):
        call_engine.hangup_call(created["call_id"])
    assert answered["state"] == "ESTABLISHED"
    call_engine.reset_calls()
