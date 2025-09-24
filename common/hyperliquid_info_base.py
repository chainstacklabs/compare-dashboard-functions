"""Base class for Hyperliquid /info endpoint metrics."""

from abc import abstractmethod
from typing import Any

import aiohttp

from common.http_timing import make_json_rpc_request
from common.metric_config import MetricConfig, MetricLabelKey, MetricLabels
from common.metric_types import HttpMetric
from common.metrics_handler import MetricsHandler


class HyperliquidInfoMetricBase(HttpMetric):
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
        state_data = kwargs.get("state_data", {})
        if not self.validate_state(state_data):
            raise ValueError(f"Invalid state data for {self.method}")

        super().__init__(
            handler=handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
        )

        params: dict[str, str] = self.get_params_from_state(state_data)
        self.user_address: str = params["user"]
        self.labels.update_label(MetricLabelKey.API_METHOD, self.method)
        self.request_payload = self._build_request_payload()

    def _build_request_payload(self) -> dict[str, Any]:
        """Build the Hyperliquid info API request payload."""
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
        base_endpoint: str = self.get_endpoint()

        if base_endpoint.endswith("/evm"):
            return base_endpoint.replace("/evm", "/info")
        else:
            # Handle cases where endpoint doesn't end with /evm
            if base_endpoint.endswith("/"):
                return base_endpoint + "info"
            else:
                return base_endpoint + "/info"

    async def fetch_data(self) -> float:
        """Measure single request latency for Hyperliquid info API."""
        endpoint: str = self.get_info_endpoint()

        async with aiohttp.ClientSession() as session:
            response_time, _response_data = await make_json_rpc_request(
                session=session,
                url=endpoint,
                request_payload=self.request_payload,
                exclude_connection_time=True,
            )
            return response_time

    def process_data(self, value: float) -> float:
        """Process raw latency measurement."""
        return value
