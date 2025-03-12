"""Configuration classes for metrics."""

import logging
from enum import Enum
from typing import Any, Optional


class MetricLabelKey(Enum):
    """Standard label keys for metric identification."""

    SOURCE_REGION = "source_region"
    TARGET_REGION = "target_region"
    BLOCKCHAIN = "blockchain"
    PROVIDER = "provider"
    API_METHOD = "api_method"
    RESPONSE_STATUS = "response_status"


class EndpointConfig:
    """Configuration for RPC endpoints."""

    def __init__(
        self,
        main_endpoint: Optional[str] = None,
        tx_endpoint: Optional[str] = None,
        ws_endpoint: Optional[str] = None,
    ) -> None:
        self.main_endpoint: str | None = main_endpoint
        self.tx_endpoint: str | None = tx_endpoint
        self.ws_endpoint: str | None = ws_endpoint

    def get_endpoint(self) -> Optional[str]:
        """Returns appropriate endpoint based on method."""
        return self.main_endpoint


class MetricConfig:
    """Configuration settings for metric collection."""

    def __init__(
        self,
        timeout: int,
        max_latency: int,
        extra_params: Optional[dict[str, Any]] = None,
        endpoints: Optional[EndpointConfig] = None,
    ) -> None:
        self.timeout: int = timeout
        self.max_latency: int = max_latency
        self.endpoints: EndpointConfig = endpoints or EndpointConfig()
        self.extra_params: dict[str, Any] = extra_params or {}


class MetricLabel:
    """Single metric label container."""

    def __init__(self, key: MetricLabelKey, value: str) -> None:
        if not isinstance(key, MetricLabelKey):
            raise ValueError(
                f"Invalid key, must be an instance of MetricLabelKey Enum: {key}"
            )
        self.key: MetricLabelKey = key
        self.value: str = value


class MetricLabels:
    """Collection of metric labels."""

    def __init__(
        self,
        source_region: str,
        target_region: str,
        blockchain: str,
        provider: str,
        api_method: str = "default",
        response_status: str = "pending",
    ) -> None:
        self.labels: list[MetricLabel] = [
            MetricLabel(MetricLabelKey.SOURCE_REGION, source_region),
            MetricLabel(MetricLabelKey.TARGET_REGION, target_region),
            MetricLabel(MetricLabelKey.BLOCKCHAIN, blockchain),
            MetricLabel(MetricLabelKey.PROVIDER, provider),
            MetricLabel(MetricLabelKey.API_METHOD, api_method),
            MetricLabel(MetricLabelKey.RESPONSE_STATUS, response_status),
        ]

    def get_prometheus_labels(self) -> str:
        """Returns Prometheus formatted labels."""
        return ",".join(f'{label.key.value}="{label.value}"' for label in self.labels)

    def update_label(self, label_name: MetricLabelKey, new_value: str) -> None:
        """Updates existing label value."""
        for label in self.labels:
            if label.key == label_name:
                label.value = new_value
                return
        logging.warning(f"Label '{label_name.value}' not found!")

    def add_label(self, label_name: MetricLabelKey, label_value: str) -> None:
        """Adds new label or updates existing."""
        for label in self.labels:
            if label.key == label_name:
                self.update_label(label_name, label_value)
                return
        self.labels.append(MetricLabel(label_name, label_value))

    def get_label(self, label_name: MetricLabelKey) -> Optional[str]:
        """Returns label value by key."""
        for label in self.labels:
            if label.key == label_name:
                return label.value
        return None
