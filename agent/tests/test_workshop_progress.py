"""Parsing a running workshop download's logs + du output into progress."""

from __future__ import annotations

from app.orchestrator import parse_workshop_progress

LOGS = """[entrypoint] logging in anonymously
[entrypoint] downloading 4 workshop item(s) for app 108600: 111 222 333 444
[entrypoint] steamcmd attempt 1/6 for 4 item(s)
Downloading item 111 ...
Success. Downloaded item 111 to "/home/steam/Steam/steamapps/workshop/content/108600/111" (10 bytes)
Downloading item 222 ...
\x1b[0mERROR! Download item 222 failed (Timeout).\x1b[0m
[workshop-result] 111 ok
[entrypoint] 1 item(s) did not complete; resuming
[entrypoint] steamcmd attempt 2/6 for 3 item(s)
Downloading item 222 ...
Success. Downloaded item 222 to "/x" (5 bytes)
Downloading item 333 ...
"""


def test_parse_progress_states_and_bytes():
    du = "111 10\n222 4\n333 2\n444 0\n"
    p = parse_workshop_progress(LOGS, du)
    assert (p["running"], p["attempt"], p["max_attempts"]) == (True, 2, 6)
    assert p["items"] == {
        "111": {"bytes": 10 * 1024, "state": "ok"},
        "222": {"bytes": 4 * 1024, "state": "downloaded"},  # this attempt's success
        "333": {"bytes": 2 * 1024, "state": "downloading"},
        "444": {"bytes": 0, "state": "waiting"},
    }


def test_parse_progress_retrying_and_no_du():
    logs = LOGS.split("[workshop-result]")[0]  # mid attempt 1, du failed
    p = parse_workshop_progress(logs, "")
    assert p["attempt"] == 1
    assert p["items"]["222"] == {"bytes": 0, "state": "retrying"}
    assert p["items"]["111"]["state"] == "downloaded"
    assert set(p["items"]) == {"111", "222", "333", "444"}  # ids from the header line
