"""Shared HTTP request timing utilities for metric collection."""

import asyncio
import time
from typing import Any, Optional

import aiohttp

# Configuration constants
MAX_RETRIES = 2
DEFAULT_RATE_LIMIT_WAIT = 3
DEFAULT_WEBSOCKET_TIMEOUT = 10


class HttpTimingCollector:
    """Utility class for measuring HTTP request timing with detailed breakdown."""

    def __init__(self) -> None:
        """Initialize HTTP timing collector."""
        self.timing: dict[str, float] = {}
        self._trace_config: Optional[aiohttp.TraceConfig] = None

    def create_trace_config(self) -> aiohttp.TraceConfig:
        """Create aiohttp trace configuration for detailed timing measurement."""
        trace_config = aiohttp.TraceConfig()

        async def on_request_start(
            _session: Any, _context: Any, _params: Any
        ) -> None:
            self.timing["start"] = time.monotonic()

        async def on_connection_create_start(
            _session: Any, _context: Any, _params: Any
        ) -> None:
            self.timing["conn_start"] = time.monotonic()

        async def on_connection_create_end(
            _session: Any, _context: Any, _params: Any
        ) -> None:
            self.timing["conn_end"] = time.monotonic()

        async def on_request_end(
            _session: Any, _context: Any, _params: Any
        ) -> None:
            self.timing["end"] = time.monotonic()

        trace_config.on_request_start.append(on_request_start)
        trace_config.on_connection_create_start.append(on_connection_create_start)
        trace_config.on_connection_create_end.append(on_connection_create_end)
        trace_config.on_request_end.append(on_request_end)

        self._trace_config = trace_config
        return trace_config

    def get_connection_time(self) -> float:
        """Get connection establishment time in seconds."""
        if "conn_start" in self.timing and "conn_end" in self.timing:
            return self.timing["conn_end"] - self.timing["conn_start"]
        return 0.0

    def get_total_time(self) -> float:
        """Get total request time in seconds."""
        if "start" in self.timing and "end" in self.timing:
            return self.timing["end"] - self.timing["start"]
        return 0.0

    def get_response_time(self, exclude_connection_time: bool = True) -> float:
        """Get response time, optionally excluding connection establishment."""
        total_time: float = self.get_total_time()
        if exclude_connection_time:
            connection_time: float = self.get_connection_time()
            return max(0.0, total_time - connection_time)
        return total_time

    def reset(self) -> None:
        """Reset timing data for reuse."""
        self.timing.clear()


async def measure_http_request_timing(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    headers: Optional[dict[str, str]] = None,
    json_data: Optional[dict[str, Any]] = None,
    exclude_connection_time: bool = True,
) -> tuple[float, aiohttp.ClientResponse]:
    """Measure HTTP request timing with retry logic and detailed breakdown.

    Args:
        session: The aiohttp client session to use for the request
        method: HTTP method (GET, POST, etc.)
        url: Target URL for the request
        headers: Optional HTTP headers dict
        json_data: Optional JSON payload for POST requests
        exclude_connection_time: If True, exclude connection establishment time
                               from the returned timing to measure pure API response time

    Returns:
        tuple: (response_time_seconds, response)
    """
    timing_collector = HttpTimingCollector()
    trace_config: aiohttp.TraceConfig = timing_collector.create_trace_config()

    # Freeze trace config before adding to session
    trace_config.freeze()
    # Add timing trace to session temporarily
    session._trace_configs.append(trace_config)

    try:
        response = None
        last_exception = None

        for retry_count in range(MAX_RETRIES):
            # Reset timing for each retry
            timing_collector.reset()

            try:
                # Prepare request arguments
                request_kwargs: dict[str, Any] = {"headers": headers}
                if json_data is not None:
                    request_kwargs["json"] = json_data

                # Send request with consistent method handling
                response = await session.request(method.upper(), url, **request_kwargs)

                # Handle rate limiting with exponential backoff
                if response.status == 429 and retry_count < MAX_RETRIES - 1:
                    wait_time = int(
                        response.headers.get("Retry-After", DEFAULT_RATE_LIMIT_WAIT)
                    )
                    await response.release()
                    # Exponential backoff
                    await asyncio.sleep(wait_time * (2 ** retry_count))
                    continue

                break

            except Exception as e:
                last_exception = e
                if retry_count < MAX_RETRIES - 1:
                    # Exponential backoff for connection errors
                    await asyncio.sleep(2 ** retry_count)
                    continue
                raise

        if not response:
            if last_exception:
                raise last_exception
            raise ValueError("No response received after retries")

        # Calculate response time using improved method
        response_time = timing_collector.get_response_time(
            exclude_connection_time
        )
        return response_time, response

    finally:
        # Remove trace config to avoid affecting other requests
        if trace_config in session._trace_configs:
            session._trace_configs.remove(trace_config)


async def make_json_rpc_request(
    session: aiohttp.ClientSession,
    url: str,
    request_payload: dict[str, Any],
    headers: Optional[dict[str, str]] = None,
    exclude_connection_time: bool = True,
) -> tuple[float, dict[str, Any]]:
    """Make a JSON-RPC request with timing measurement and validation.

    Args:
        session: The aiohttp client session
        url: Target endpoint URL
        request_payload: JSON-RPC request payload
        headers: Optional HTTP headers
        exclude_connection_time: Whether to exclude connection time from measurement

    Returns:
        tuple: (response_time_seconds, json_response)

    Raises:
        aiohttp.ClientResponseError: For non-200 status codes
        ValueError: For JSON-RPC errors or invalid responses
    """
    default_headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if headers:
        default_headers.update(headers)

    response_time, response = await measure_http_request_timing(
        session=session,
        method="POST",
        url=url,
        headers=default_headers,
        json_data=request_payload,
        exclude_connection_time=exclude_connection_time,
    )

    try:
        if response.status != 200:
            raise aiohttp.ClientResponseError(
                request_info=response.request_info,
                history=(),
                status=response.status,
                message=f"Status code: {response.status}",
                headers=response.headers,
            )

        json_response = await response.json()

        # Validate JSON-RPC response for errors
        if "error" in json_response:
            raise ValueError(f"JSON-RPC error: {json_response['error']}")

        return response_time, json_response
    finally:
        if response and not response.closed:
            await response.release()
