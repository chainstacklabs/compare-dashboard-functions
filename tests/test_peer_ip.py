"""Self-check for peer IP capture: python tests/test_peer_ip.py

Fails if ``peer_ip`` stops returning the connected address, for example after
an aiohttp upgrade changes the private ``ClientResponse._protocol``.
"""

import asyncio
import sys
from pathlib import Path

from aiohttp import ClientSession, web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.metric_types import peer_ip


async def _rpc(request: web.Request) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": 1, "result": "0x1"})


async def main() -> None:
    app = web.Application()
    app.router.add_post("/", _rpc)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        async with ClientSession() as session:
            response = await session.post(f"http://127.0.0.1:{port}/", json={})
            ip = peer_ip(response)
            response.release()
    finally:
        await runner.cleanup()

    assert ip == "127.0.0.1", f"peer_ip returned {ip!r}"
    print("OK: peer_ip reads the connected address")


if __name__ == "__main__":
    asyncio.run(main())
