"""Self-check for peer IP capture: python tests/test_peer_ip.py

Fails if ``PeerAddressRecorder`` stops reporting the connected address, with
the connection kept alive or closed by the server after the response.
"""

import asyncio
import sys
from pathlib import Path

import aiohttp
from aiohttp import web

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.metric_types import PeerAddressRecorder


async def _rpc(request: web.Request) -> web.Response:
    return web.json_response({"jsonrpc": "2.0", "id": 1, "result": "0x1"})


async def _rpc_close(request: web.Request) -> web.Response:
    response = await _rpc(request)
    response.force_close()
    return response


async def _peer_for(url: str) -> str | None:
    peer = PeerAddressRecorder()
    trace_config = aiohttp.TraceConfig()
    trace_config.on_connection_create_end.append(peer.on_connection_created)
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(socket_factory=peer.socket_factory),
        trace_configs=[trace_config],
    ) as session:
        response = await session.post(url, json={})
        response.release()
    return peer.ip


async def main() -> None:
    app = web.Application()
    app.router.add_post("/", _rpc)
    app.router.add_post("/close", _rpc_close)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = runner.addresses[0][1]
    try:
        for path in ("/", "/close"):
            ip = await _peer_for(f"http://127.0.0.1:{port}{path}")
            assert ip == "127.0.0.1", f"{path}: peer address was {ip!r}"
    finally:
        await runner.cleanup()

    print("OK: peer address recorded with keep-alive and with Connection: close")


if __name__ == "__main__":
    asyncio.run(main())
