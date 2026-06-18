"""Manual Phase 3 smoke test for the Docker orchestrator (no UI, no DB).

Run inside the backend container:
    docker compose exec backend python scripts/test_orchestrator.py
"""

import time

from app.services.docker_orchestrator import orchestrator

SID = "smoketest"


def main() -> None:
    print("ping:", orchestrator.ping().get("Version"))

    # A trivial long-running "server" so we don't need a real game install.
    env = {"STARTUP_CMD": "i=0; while true; do echo tick-$i; i=$((i+1)); sleep 1; done"}

    print("create...")
    cid = orchestrator.create_server_container(SID, env=env, port_bindings={})
    print("  created", cid[:12])
    assert orchestrator.state(SID).status == "created"

    print("start...")
    orchestrator.start(SID)
    time.sleep(3)
    st = orchestrator.state(SID)
    print("  status:", st.status)
    assert st.status == "running"

    logs = orchestrator.recent_logs(SID, tail=5)
    print("  logs:", logs.strip().replace("\n", " | "))
    assert "tick-" in logs

    print("restart...")
    orchestrator.restart(SID, timeout=5)
    time.sleep(2)
    assert orchestrator.state(SID).status == "running"

    print("stop...")
    orchestrator.stop(SID, timeout=5)
    assert orchestrator.state(SID).status == "exited"
    print("  status:", orchestrator.state(SID).status)

    print("remove (with data volume)...")
    orchestrator.remove(SID, remove_data=True)
    assert orchestrator.state(SID).status == "absent"
    print("  status:", orchestrator.state(SID).status)

    print("\nPHASE 3 OK")


if __name__ == "__main__":
    main()
