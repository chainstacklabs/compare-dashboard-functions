"""Verifier function: emits balance_verified + verifier_status for EVM chains.

Per cron round (fra1-only, every 15 min, offset 5 min from update_state):
- Read OLD_BLOCK from shared blob storage (set by update_state).
- For each chain in [Ethereum, Base, Arbitrum, BNB]:
  - Multi-provider stateRoot quorum at OLD_BLOCK.
  - eth_getProof from Chainstack for the chain's probe address.
  - Local MPT verification against the agreed stateRoot.
  - Emit balance_verified (hashed) on success, verifier_status code on any failure.

See ``spec-verified-correctness-v2.md`` (local design doc).
"""

import asyncio
import logging
import os
import time
from http.server import BaseHTTPRequestHandler
from typing import Any

import aiohttp

from common.balance_hash import hash_balance_to_float
from common.state.blockchain_state import BlockchainState
from common.verify import (
    AnchorDisagreementError,
    AnchorPartialResponseError,
    ProofError,
    all_providers_for,
    chainstack_endpoint_for,
    fetch_account_proof,
    fetch_agreed_anchor,
    verify_account_proof,
)
from config.defaults import MetricsServiceConfig

ALLOWED_REGIONS: set[str] = {"fra1"}

# Probe addresses match v1's HTTPAccBalanceLatencyMetric.probe_address per chain.
PROBE_ADDRESSES: dict[str, str] = {
    "Ethereum": "0x690B9A9E9aa1C9dB991C7721a92d351Db4FaC990",
    "Base": "0xF977814e90dA44bFA03b6295A0616a897441aceC",
    "Arbitrum": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
    "BNB": "0x6807dc923806fE8Fd134338EABCA509979a7e0cB",
}

METRIC_NAME = f"{MetricsServiceConfig.METRIC_PREFIX}response_latency_seconds"

# Verifier status codes (per spec).
STATUS_OK = 0
STATUS_STATEROOT_DISAGREEMENT = 1
STATUS_PROOF_MATH_INVALID = 2
STATUS_ANCHOR_UNAVAILABLE = 3
STATUS_PROOF_UNAVAILABLE = 4


def _format_balance_verified_line(
    chain: str, block_hex: str, hash_value: float, ts_ns: int
) -> str:
    """Format an Influx line for ``metric_type=balance_verified``."""
    return (
        f"{METRIC_NAME},"
        f"source_region=fra1,target_region=default,blockchain={chain},"
        f"api_method=eth_getBalance,response_status=success,"
        f"metric_type=balance_verified,block_number={block_hex} "
        f"value={hash_value} {ts_ns}"
    )


def _format_verifier_status_line(chain: str, code: int, ts_ns: int) -> str:
    """Format an Influx line for ``metric_type=verifier_status``."""
    return (
        f"{METRIC_NAME},"
        f"source_region=fra1,blockchain={chain},"
        f"metric_type=verifier_status "
        f"value={code} {ts_ns}"
    )


async def _verify_chain(
    session: aiohttp.ClientSession,
    chain: str,
    state_data: dict[str, Any],
) -> list[str]:
    """Run one verifier round for a chain. Returns Influx-format lines to emit."""
    chain_lower = chain.lower()
    chain_state = state_data.get(chain_lower)
    if not chain_state or not chain_state.get("old_block"):
        logging.warning(f"verify_state: no old_block for {chain}, skipping")
        return []

    block_hex = chain_state["old_block"]
    addr_hex = PROBE_ADDRESSES[chain]
    addr_bytes = bytes.fromhex(addr_hex.removeprefix("0x"))
    ts_ns = time.time_ns()

    providers = all_providers_for(chain)
    chainstack_url = chainstack_endpoint_for(chain)

    if not providers or not chainstack_url:
        logging.warning(f"verify_state: missing endpoints for {chain}")
        return [_format_verifier_status_line(chain, STATUS_ANCHOR_UNAVAILABLE, ts_ns)]

    # 1. Anchor — multi-provider stateRoot quorum.
    try:
        anchor = await fetch_agreed_anchor(session, block_hex, providers)
    except AnchorDisagreementError:
        logging.warning(f"verify_state: stateRoot disagreement for {chain}")
        return [
            _format_verifier_status_line(chain, STATUS_STATEROOT_DISAGREEMENT, ts_ns)
        ]
    except AnchorPartialResponseError as e:
        logging.warning(f"verify_state: anchor partial for {chain}: {e}")
        return [_format_verifier_status_line(chain, STATUS_ANCHOR_UNAVAILABLE, ts_ns)]

    # 2. Proof from Chainstack.
    try:
        proof = await fetch_account_proof(session, chainstack_url, addr_hex, block_hex)
    except Exception as e:
        logging.warning(f"verify_state: proof fetch failed for {chain}: {e}")
        return [_format_verifier_status_line(chain, STATUS_PROOF_UNAVAILABLE, ts_ns)]

    # 3. Local MPT verification.
    try:
        balance = verify_account_proof(addr_bytes, proof, anchor)
    except ProofError as e:
        logging.error(f"verify_state: proof math invalid for {chain}: {e}")
        return [_format_verifier_status_line(chain, STATUS_PROOF_MATH_INVALID, ts_ns)]

    if balance is None:
        # Probe address has no state at OLD_BLOCK — unexpected for our funded probes.
        logging.error(
            f"verify_state: exclusion proof for {chain} "
            f"address={addr_hex} block={block_hex}"
        )
        return [_format_verifier_status_line(chain, STATUS_PROOF_MATH_INVALID, ts_ns)]

    # 4. Emit balance_verified + verifier_status=0.
    return [
        _format_balance_verified_line(
            chain, block_hex, hash_balance_to_float(balance), ts_ns
        ),
        _format_verifier_status_line(chain, STATUS_OK, ts_ns),
    ]


async def _gather_state_data() -> dict[str, dict[str, Any]]:
    """Read OLD_BLOCK + other state for each in-scope chain from blob storage."""
    out: dict[str, dict[str, Any]] = {}
    for chain in PROBE_ADDRESSES:
        try:
            chain_state = await BlockchainState.get_data(chain.lower())
            if chain_state:
                out[chain.lower()] = chain_state
        except Exception:
            logging.exception(f"verify_state: failed to read state for {chain}")
    return out


async def _verify_all() -> str:
    """Run the verifier across all in-scope chains. Returns Influx text."""
    state_data = await _gather_state_data()

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_verify_chain(session, chain, state_data) for chain in PROBE_ADDRESSES],
            return_exceptions=True,
        )

    lines: list[str] = []
    for r in results:
        if isinstance(r, list):
            lines.extend(r)
        else:
            logging.exception("verify_state: chain task raised", exc_info=r)
    return "\n".join(lines)


async def _push_to_grafana(metrics_text: str) -> None:
    """Push metrics in Influx line protocol to Grafana Cloud.

    Mirrors ``MetricsHandler.push_to_grafana`` so this verifier function is
    self-contained — refactoring the push helper into a shared util is a separate
    concern.
    """
    if not metrics_text:
        return

    url = os.environ.get("GRAFANA_URL")
    user = os.environ.get("GRAFANA_USER")
    api_key = os.environ.get("GRAFANA_API_KEY")
    if not url or not user or not api_key:
        logging.warning("verify_state: Grafana env not set, skipping push")
        return

    timeout = aiohttp.ClientTimeout(total=MetricsServiceConfig.GRAFANA_PUSH_TIMEOUT)
    for attempt in range(1, MetricsServiceConfig.GRAFANA_PUSH_MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers={"Content-Type": "text/plain"},
                    data=metrics_text,
                    auth=aiohttp.BasicAuth(user, api_key),
                    timeout=timeout,
                ) as response:
                    if response.status in (200, 204):
                        return
                    logging.warning(
                        f"verify_state: Grafana push got {response.status} "
                        f"on attempt {attempt}"
                    )
        except Exception:
            logging.exception(
                f"verify_state: Grafana push exception on attempt {attempt}"
            )
        if attempt < MetricsServiceConfig.GRAFANA_PUSH_MAX_RETRIES:
            await asyncio.sleep(MetricsServiceConfig.GRAFANA_PUSH_RETRY_DELAY)


class handler(BaseHTTPRequestHandler):
    """Vercel HTTP handler for the verifier cron."""

    def _check_auth(self) -> bool:
        if os.getenv("SKIP_AUTH", "").lower() == "true":
            return True
        token = self.headers.get("Authorization", "")
        return token == f"Bearer {os.getenv('CRON_SECRET', '')}"

    def do_GET(self) -> None:
        """Authenticate, gate by region, run verifier, push metrics."""
        if not self._check_auth():
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        if os.getenv("VERCEL_REGION") not in ALLOWED_REGIONS:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Skipped (wrong region)")
            return

        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            metrics_text: str = loop.run_until_complete(_verify_all())
            if metrics_text:
                loop.run_until_complete(_push_to_grafana(metrics_text))

            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            response_body = (
                f"verify_state completed\n\nMetrics:\n{metrics_text}".encode()
            )
            self.wfile.write(response_body)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(str(e).encode())
        finally:
            loop.close()
