"""Console stream helpers: target selection and timestamped line splitting. No I/O."""

from __future__ import annotations

from app.services.console_stream import LineSplitter, pick_target, ts_to_unix
from app.services.docker_orchestrator import ContainerState

ABSENT = ContainerState(exists=False, status="absent")


def state(status: str, cid: str = "c1") -> ContainerState:
    return ContainerState(exists=True, status=status, id=cid, started_at="2026-10-18T10:00:00Z")


def test_running_install_wins_over_the_game_container():
    target = pick_target(state("exited", "game"), state("running", "inst"))
    assert target is not None and target[0] == "install"


def test_game_container_otherwise_even_when_stopped():
    assert pick_target(state("running", "game"), ABSENT)[0] == "server"
    assert pick_target(state("exited", "game"), state("exited", "inst"))[0] == "server"


def test_leftover_install_container_and_nothing():
    assert pick_target(ABSENT, state("exited", "inst"))[0] == "install"
    assert pick_target(ABSENT, ABSENT) is None


def test_lines_get_their_own_timestamp():
    s = LineSplitter()
    out = s.feed(b"2026-10-18T10:00:00.123456789Z hello\r\n2026-10-18T10:00:01.5Z world\r\n")
    assert out == [
        ("2026-10-18T10:00:00.123456789Z", "hello"),
        ("2026-10-18T10:00:01.5Z", "world"),
    ]


def test_partial_line_is_carried_to_the_next_chunk():
    s = LineSplitter()
    assert s.feed(b"2026-10-18T10:00:00Z Update state (0x61) downl") == []
    assert s.feed(b"oading, progress: 5.83 (1 / 2)\n") == [
        ("2026-10-18T10:00:00Z", "Update state (0x61) downloading, progress: 5.83 (1 / 2)")
    ]
    assert s.feed(b"2026-10-18T10:00:02Z tail without newline") == []
    assert s.flush() == [("2026-10-18T10:00:02Z", "tail without newline")]
    assert s.flush() == []


def test_line_without_prefix_inherits_the_last_timestamp_and_keeps_inner_cr():
    s = LineSplitter()
    s.feed(b"2026-10-18T10:00:00Z first\n")
    assert s.feed(b"no prefix\rredrawn\n") == [("2026-10-18T10:00:00Z", "no prefix\rredrawn")]


def test_ts_to_unix():
    assert ts_to_unix("1970-01-01T00:00:10.5Z") == 10.5
    assert ts_to_unix("1970-01-01T00:00:10.123456789Z") == 10.123456789
    assert ts_to_unix("0001-01-01T00:00:00Z") is None  # Docker's "never started"
    assert ts_to_unix(None) is None
    assert ts_to_unix("garbage") is None
