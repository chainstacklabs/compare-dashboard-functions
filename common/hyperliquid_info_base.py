"""Base class for Hyperliquid /info endpoint metrics."""

from abc import abstractmethod
from typing import Any

import aiohttp

from common.metric_config import MetricConfig, MetricLabels
from common.metric_types import HttpCallLatencyMetricBase
from common.metrics_handler import MetricsHandler


class HyperliquidInfoMetricBase(HttpCallLatencyMetricBase):
    """Base class for Hyperliquid /info endpoint latency metrics.

    Handles request configuration, state validation, and response time
    measurement for Hyperliquid info API endpoints.
    """

    @property
    @abstractmethod
    def method(self) -> str:
        """Info API method to be implemented by subclasses."""
        pass

    def __init__(
        self,
        handler: "MetricsHandler",
        metric_name: str,
        labels: MetricLabels,
        config: MetricConfig,
        **kwargs: Any,
    ) -> None:
        """Initialize Hyperliquid info metric with state-based parameters."""
        # Extract state data before passing to parent
        state_data = kwargs.get("state_data", {})
        params: dict[str, str] = self.get_params_from_state(state_data)
        self.user_address: str = params["user"]

        # Call parent constructor with method_params set to None since we
        # override _build_base_request
        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            method_params=None,
            **kwargs,
        )

    def _build_base_request(self) -> dict[str, Any]:
        """Override to build Hyperliquid-specific request payload."""
        return {"type": self.method, "user": self.user_address}

    @staticmethod
    def validate_state(state_data: dict[str, Any]) -> bool:
        """Validate state data. Override in subclasses if needed."""
        return True

    @staticmethod
    def get_params_from_state(state_data: dict[str, Any]) -> dict[str, str]:
        """Get parameters from state data. Override in subclasses if needed."""
        return {}

    def get_info_endpoint(self) -> str:
        """Transform EVM endpoint to info endpoint."""
        base_endpoint: str = self.get_endpoint().rstrip("/")

        if base_endpoint.endswith("/info"):
            return base_endpoint

        if base_endpoint.endswith("/evm"):
            base_endpoint = base_endpoint[:-4]

        return f"{base_endpoint}/info"

    async def _send_request(
        self, session: aiohttp.ClientSession, endpoint: str
    ) -> aiohttp.ClientResponse:
        """Override to use Hyperliquid info endpoint and request format."""
        info_endpoint: str = self.get_info_endpoint()
        return await session.post(
            info_endpoint,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json=self._base_request,
        )
