"""Phase 6 WebSocket console smoke test.

Usage (inside backend container):
    python scripts/test_ws.py <server_id>
"""

import asyncio
import sys

import websockets


async def main(server_id: str) -> None:
    uri = f"ws://localhost:8000/api/servers/{server_id}/console"
    async with websockets.connect(uri) as ws:
        print(f"connected to {uri}")
        # Send a test command to the server's stdin (best-effort).
        await ws.send("status")
        received = 0
        try:
            while received < 5:
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                for line in msg.splitlines():
                    if line.strip():
                        print("  <<", line.strip())
                        received += 1
        except TimeoutError:
            print("  (no more messages within timeout)")
    print("\nPHASE 6 OK" if received else "\nPHASE 6: no log lines received")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
