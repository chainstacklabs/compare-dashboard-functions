"""Shared HTTP request timing utilities for metric collection."""

import asyncio
import time
from typing import Any, Optional

import aiohttp

MAX_RETRIES = 2


class HttpTimingCollector:
    """Utility class for measuring HTTP request timing with detailed breakdown."""

    def __init__(self) -> None:
        self.timing: dict[str, float] = {}

    def create_trace_config(self) -> aiohttp.TraceConfig:
        """Create aiohttp trace configuration for detailed timing measurement."""
        trace_config = aiohttp.TraceConfig()

        async def on_request_start(_session: Any, _context: Any, _params: Any) -> None:
            self.timing["start"] = time.monotonic()

        async def on_connection_create_start(_session: Any, _context: Any, _params: Any) -> None:
            self.timing["conn_start"] = time.monotonic()

        async def on_connection_create_end(_session: Any, _context: Any, _params: Any) -> None:
            self.timing["conn_end"] = time.monotonic()

        async def on_request_end(_session: Any, _context: Any, _params: Any) -> None:
            self.timing["end"] = time.monotonic()

        trace_config.on_request_start.append(on_request_start)
        trace_config.on_connection_create_start.append(on_connection_create_start)
        trace_config.on_connection_create_end.append(on_connection_create_end)
        trace_config.on_request_end.append(on_request_end)

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
        exclude_connection_time: If True, exclude connection establishment time
                               from the returned timing to measure pure API response time

    Returns:
        tuple: (response_time_seconds, response)
    """
    timing_collector = HttpTimingCollector()
    trace_config: aiohttp.TraceConfig = timing_collector.create_trace_config()

    # Add timing trace to session temporarily
    session._trace_configs.append(trace_config)

    try:
        response = None

        for retry_count in range(MAX_RETRIES):
            # Reset timing for each retry
            timing_collector.timing.clear()

            # Send request
            # Prepare kwargs for any HTTP method, including optional JSON payload
            request_kwargs: dict[str, Any] = {"headers": headers}
            if json_data is not None:
                request_kwargs["json"] = json_data

            if method.upper() == "POST":
                response = await session.post(
                        url, headers=headers, json=json_data
                    )

            else:
                response = await session.request(method.upper(), url, **request_kwargs)

            # Handle rate limiting
            if response.status == 429 and retry_count < MAX_RETRIES - 1:
                wait_time = int(response.headers.get("Retry-After", 3))
                await response.release()
                await asyncio.sleep(wait_time)
                continue

            break

        if not response:
            raise ValueError("No response received")

        # Calculate response time based on exclusion setting
        total_time: float = timing_collector.get_total_time()

        if exclude_connection_time:
            connection_time: float = timing_collector.get_connection_time()
            response_time: float = max(0.0, total_time - connection_time)
        else:
            response_time = total_time

        return response_time, response

    finally:
        # Remove trace config to avoid affecting other requests
        if trace_config in session._trace_configs:
            session._trace_configs.remove(trace_config)
