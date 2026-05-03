"""Multi-provider stateRoot quorum + Chainstack proof fetch.

The quorum policy is "all or none" per spec: if any provider in fra1 fails to
return a valid stateRoot, raise ``AnchorPartialResponse``. If all respond but
not all agree, raise ``AnchorDisagreement``. The orchestration code in
``api/support/verify_state.py`` maps these to the correct ``verifier_status``
codes (3 and 1 respectively).
"""

import asyncio
import json
from typing import Any, Optional

import aiohttp

_RPC_TIMEOUT = aiohttp.ClientTimeout(total=15)
_PROOF_TIMEOUT = aiohttp.ClientTimeout(total=25)


class AnchorError(Exception):
    """Base exception for anchor-fetch failures."""


class AnchorPartialResponseError(AnchorError):
    """Raised when one or more providers didn't return a valid stateRoot."""


class AnchorDisagreementError(AnchorError):
    """Raised when providers all responded but didn't all return the same stateRoot."""


async def fetch_agreed_anchor(
    session: aiohttp.ClientSession,
    block_hex: str,
    providers: list[str],
) -> bytes:
    """Fetch stateRoot from each provider in parallel; require unanimous agreement.

    Args:
        session: Shared aiohttp session.
        block_hex: Block number as a lowercase hex string (e.g. ``"0x14a2b3c"``).
        providers: List of HTTP RPC endpoints to query.

    Returns:
        The 32-byte agreed stateRoot.

    Raises:
        AnchorPartialResponseError: If any provider failed (HTTP error, RPC error,
            malformed response, or no providers configured).
        AnchorDisagreementError: If providers responded but returned different
            stateRoots.
    """
    if not providers:
        raise AnchorPartialResponseError("no providers configured")

    tasks = [_fetch_state_root(session, url, block_hex) for url in providers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    state_roots: set[bytes] = set()
    for result in results:
        if isinstance(result, BaseException):
            raise AnchorPartialResponseError(f"provider call failed: {result!r}")
        if result is None:
            raise AnchorPartialResponseError("provider returned no stateRoot")
        state_roots.add(result)

    if len(state_roots) > 1:
        raise AnchorDisagreementError(
            "providers disagreed on stateRoot: "
            + ", ".join(sorted(r.hex() for r in state_roots))
        )

    return next(iter(state_roots))


async def _fetch_state_root(
    session: aiohttp.ClientSession, url: str, block_hex: str
) -> Optional[bytes]:
    """Call ``eth_getBlockByNumber`` and extract ``stateRoot``.

    Returns:
        32-byte stateRoot on success, or ``None`` on any non-success path
        (HTTP error, RPC error, missing fields). Wrapped in caller's exception
        handling.
    """
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getBlockByNumber",
        "params": [block_hex, False],
    }
    async with session.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=_RPC_TIMEOUT,
    ) as response:
        if response.status != 200:
            return None
        body = await response.json()
        if not isinstance(body, dict) or "error" in body:
            return None
        block = body.get("result")
        if not isinstance(block, dict):
            return None
        state_root_hex = block.get("stateRoot")
        if not isinstance(state_root_hex, str):
            return None
        try:
            return bytes.fromhex(state_root_hex.removeprefix("0x"))
        except ValueError:
            return None


async def fetch_account_proof(
    session: aiohttp.ClientSession,
    url: str,
    address_hex: str,
    block_hex: str,
) -> list[bytes]:
    """Call ``eth_getProof`` on the given endpoint and return the accountProof.

    Args:
        session: Shared aiohttp session.
        url: Chainstack HTTP endpoint for the chain.
        address_hex: Probe address as a hex string with ``0x`` prefix.
        block_hex: Block number as a lowercase hex string.

    Returns:
        The accountProof: a list of RLP-encoded MPT nodes.

    Raises:
        RuntimeError: On HTTP error, RPC error, or malformed response.
    """
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_getProof",
        "params": [address_hex, [], block_hex],
    }
    async with session.post(
        url,
        headers={"Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=_PROOF_TIMEOUT,
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"eth_getProof HTTP {response.status}")
        body = await response.json()
        if not isinstance(body, dict):
            raise RuntimeError("eth_getProof returned non-object")
        if "error" in body:
            raise RuntimeError(f"eth_getProof error: {body['error']}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("eth_getProof result is not an object")
        account_proof = result.get("accountProof")
        if not isinstance(account_proof, list):
            raise RuntimeError("eth_getProof accountProof is not a list")
        try:
            return [
                bytes.fromhex(node.removeprefix("0x"))
                for node in account_proof
                if isinstance(node, str)
            ]
        except ValueError as e:
            raise RuntimeError(f"eth_getProof accountProof has invalid hex: {e}") from e
