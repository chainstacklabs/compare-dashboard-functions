"""Verifier function: emits balance_verified + verifier_status for EVM chains.

Per cron round (fra1-only, every 15 min). For each chain in
[Ethereum, Arbitrum, BNB, Robinhood]:
  - Compute VERIFY_BLOCK = latest_head - random(VERIFY_BLOCK_OFFSET_RANGES[chain]).
    Self-contained: no blob coordination with update_state.
  - Multi-provider stateRoot quorum at VERIFY_BLOCK.
  - eth_getProof from Chainstack for the chain's probe address.
  - Local MPT verification against the agreed stateRoot.
  - Probe each provider's eth_getBalance at VERIFY_BLOCK (per-provider
    balance_observed_verified emission, hashed identically to balance_verified
    so dashboards can join the two on block_number and compare per-provider
    reporting against the proof-anchored truth).

The per-chain offsets are sized to fit Chainstack's empirically-measured
proof-retention window — proofs are MPT trie nodes, pruned ~128 blocks deep
on geth-family clients, much shallower than the snapshot-served balance
window. See ``config/defaults.py:VERIFY_BLOCK_OFFSET_RANGES``.

See ``spec-verified-correctness-v2.md`` (local design doc).
"""

import asyncio
import hmac
import logging
import os
import random
import time
from http.server import BaseHTTPRequestHandler
from typing import Optional

import aiohttp

from common.balance_hash import hash_balance_to_float
from common.verify import (
    AnchorDisagreementError,
    AnchorPartialResponseError,
    ProofError,
    all_provider_entries_for,
    chainstack_endpoint_for,
    fetch_account_proof,
    fetch_agreed_anchor,
    fetch_balance_at,
    fetch_latest_block,
    verify_account_proof,
)
from config.defaults import MetricsServiceConfig

ALLOWED_REGIONS: set[str] = {"fra1"}

# Probe addresses: canonical wrap contracts on each chain (WETH / WBNB).
# Held balances are high and change on every wrap/unwrap, so successive
# rounds sample meaningfully different values at VERIFY_BLOCK.
PROBE_ADDRESSES: dict[str, str] = {
    "Ethereum": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH9
    # Base is deferred: eth_getProof is not currently available at a usable
    # VERIFY_BLOCK depth for this chain, so v2 verification can't run. Base keeps
    # its v1 balance_observed + latency metrics; re-add here once historical
    # proofs are available. (Same shape as the Robinhood v2 deferral.)
    "Arbitrum": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",  # WETH
    "BNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
    # WETH on Robinhood — same address as the v1 balance probe
    # (metrics/robinhood.py) so the observed↔verified dashboard join lines up.
    "Robinhood": "0x0bd7d308f8e1639fab988df18a8011f41eacad73",
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


def _format_balance_observed_verified_line(
    chain: str,
    provider_name: str,
    block_hex: str,
    hash_value: float,
    ts_ns: int,
) -> str:
    """Format an Influx line for per-provider ``balance_observed_verified``.

    Distinct from v1's ``balance_observed`` (which is emitted at v1's deep
    OLD_BLOCK alongside the latency cron) so dashboards can pair each
    provider's report at VERIFY_BLOCK with the proof-anchored truth at the
    same block without colliding on the legacy v1 series.
    """
    return (
        f"{METRIC_NAME},"
        f"source_region=fra1,target_region=default,blockchain={chain},"
        f"provider={provider_name},api_method=eth_getBalance,"
        f"response_status=success,metric_type=balance_observed_verified,"
        f"block_number={block_hex} "
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


def _pick_verify_block(chain: str, head: int) -> Optional[int]:
    """Compute VERIFY_BLOCK for a chain, or None if no offset configured."""
    offset_range = MetricsServiceConfig.VERIFY_BLOCK_OFFSET_RANGES.get(chain.lower())
    if not offset_range:
        return None
    lo, hi = offset_range
    return head - random.randint(lo, hi)


async def _probe_observed_balances(
    session: aiohttp.ClientSession,
    chain: str,
    provider_entries: list[tuple[str, str]],
    addr_hex: str,
    block_hex: str,
    ts_ns: int,
) -> list[str]:
    """Probe each provider's eth_getBalance at VERIFY_BLOCK in parallel.

    Returns Influx lines for providers that responded successfully. Failures
    (timeout, RPC error, malformed) are silently skipped — dashboards show
    a clean gap, which is the right shape for a transient provider blip.
    Quorum/proof emission has already happened by the time this runs, so a
    per-provider balance failure is informational, not a verifier failure.
    """
    tasks = [
        fetch_balance_at(session, url, addr_hex, block_hex)
        for _, url in provider_entries
    ]
    balances = await asyncio.gather(*tasks, return_exceptions=True)

    lines: list[str] = []
    for (name, _url), balance in zip(provider_entries, balances):
        if isinstance(balance, BaseException) or balance is None:
            continue
        if not isinstance(balance, int) or balance < 0:
            continue
        lines.append(
            _format_balance_observed_verified_line(
                chain, name, block_hex, hash_balance_to_float(balance), ts_ns
            )
        )
    return lines


async def _verify_chain(
    session: aiohttp.ClientSession,
    chain: str,
) -> list[str]:
    """Run one verifier round for a chain. Returns Influx-format lines to emit.

    Always emits at least one ``verifier_status`` line so dashboards can tell
    "verifier round happened" from "no sample" — never returns an empty list.
    """
    ts_ns = time.time_ns()
    addr_hex = PROBE_ADDRESSES[chain]
    addr_bytes = bytes.fromhex(addr_hex.removeprefix("0x"))

    provider_entries = all_provider_entries_for(chain)
    providers = [url for _, url in provider_entries]
    chainstack_url = chainstack_endpoint_for(chain)

    if not providers:
        logging.warning(f"verify_state: no anchor providers configured for {chain}")
        return [_format_verifier_status_line(chain, STATUS_ANCHOR_UNAVAILABLE, ts_ns)]
    if not chainstack_url:
        logging.warning(f"verify_state: no Chainstack endpoint configured for {chain}")
        return [_format_verifier_status_line(chain, STATUS_PROOF_UNAVAILABLE, ts_ns)]

    # 0. Compute VERIFY_BLOCK from current head. We sample head from Chainstack
    #    because Chainstack also serves the proof — its head determines whether
    #    the chosen block falls inside the proof window. Other providers can be
    #    a few blocks behind without breaking anything (offsets are large enough
    #    to absorb normal cross-provider lag).
    head = await fetch_latest_block(session, chainstack_url)
    if head is None:
        logging.warning(f"verify_state: failed to fetch latest block for {chain}")
        return [_format_verifier_status_line(chain, STATUS_ANCHOR_UNAVAILABLE, ts_ns)]

    verify_block = _pick_verify_block(chain, head)
    if verify_block is None:
        logging.warning(f"verify_state: no VERIFY_BLOCK_OFFSET_RANGES for {chain}")
        return [_format_verifier_status_line(chain, STATUS_ANCHOR_UNAVAILABLE, ts_ns)]
    block_hex = hex(verify_block)

    # 1. Anchor — multi-provider stateRoot quorum at VERIFY_BLOCK.
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
        # Use type(e).__name__ + repr so silent failures like
        # asyncio.TimeoutError (which has an empty str()) are visible.
        logging.warning(
            f"verify_state: proof fetch failed for {chain}: "
            f"{type(e).__name__}: {e!r}"
        )
        return [_format_verifier_status_line(chain, STATUS_PROOF_UNAVAILABLE, ts_ns)]

    # 3. Local MPT verification.
    try:
        balance = verify_account_proof(addr_bytes, proof, anchor)
    except ProofError:
        logging.exception(f"verify_state: proof math invalid for {chain}")
        return [_format_verifier_status_line(chain, STATUS_PROOF_MATH_INVALID, ts_ns)]

    if balance is None:
        # Cryptographically valid exclusion proof for our funded probe address —
        # not a math failure. Most likely root causes: wrong probe address, or
        # chain reorg deeper than VERIFY_BLOCK_OFFSET_RANGES (very unlikely on
        # post-finality blocks; possible at L2 sequencer-settle depth).
        logging.error(
            f"verify_state: unexpected exclusion proof for {chain} "
            f"address={addr_hex} block={block_hex}"
        )
        return [_format_verifier_status_line(chain, STATUS_PROOF_UNAVAILABLE, ts_ns)]

    # 4. Probe per-provider balances at VERIFY_BLOCK in parallel. Failures
    #    here don't change verifier_status — proof+quorum already succeeded.
    observed_lines = await _probe_observed_balances(
        session, chain, provider_entries, addr_hex, block_hex, ts_ns
    )

    # 5. Emit balance_verified + verifier_status=0 + per-provider observations.
    return [
        _format_balance_verified_line(
            chain, block_hex, hash_balance_to_float(balance), ts_ns
        ),
        _format_verifier_status_line(chain, STATUS_OK, ts_ns),
        *observed_lines,
    ]


async def _verify_all() -> str:
    """Run the verifier across all in-scope chains. Returns Influx text.

    If a per-chain task raises an unexpected exception (i.e. something not
    handled inside ``_verify_chain``), emit ``verifier_status=4`` for that
    chain so the failure is visible in dashboards rather than silently dropped.
    """
    chains = list(PROBE_ADDRESSES)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[_verify_chain(session, chain) for chain in chains],
            return_exceptions=True,
        )

    lines: list[str] = []
    fallback_ts_ns = time.time_ns()
    for chain, r in zip(chains, results):
        if isinstance(r, list):
            lines.extend(r)
        else:
            logging.error(
                f"verify_state: chain task raised for {chain}",
                exc_info=r if isinstance(r, BaseException) else None,
            )
            # Catch-all for unexpected exceptions (network blips, bugs, etc.) —
            # these are infra failures, not cryptographic invalidity, so map to
            # STATUS_PROOF_UNAVAILABLE rather than STATUS_PROOF_MATH_INVALID.
            lines.append(
                _format_verifier_status_line(
                    chain, STATUS_PROOF_UNAVAILABLE, fallback_ts_ns
                )
            )
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
                    if response.status in MetricsServiceConfig.IGNORED_HTTP_ERRORS:
                        # Silent per project convention (CLAUDE.md): plan
                        # restrictions and rate limits are not retried or logged.
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
        secret = os.getenv("CRON_SECRET", "")
        if not secret:
            logging.error("verify_state: CRON_SECRET not set; rejecting request")
            return False
        token = self.headers.get("Authorization", "")
        return hmac.compare_digest(token, f"Bearer {secret}")

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
        except Exception:
            logging.exception("verify_state: unhandled exception")
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Internal Server Error")
        finally:
            loop.close()
