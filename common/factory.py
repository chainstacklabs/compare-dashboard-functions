"""Factory for creating blockchain-specific metric instances."""

import copy
from dataclasses import dataclass

from common.base_metric import BaseMetric
from common.metric_config import EndpointConfig, MetricConfig, MetricLabels


@dataclass
class MetricRegistration:
    """Stores metadata for registering a metric, including its class and name."""

    metric_class: type[BaseMetric]
    metric_name: str


class MetricFactory:
    """Creates metric instances for blockchains.

    For SolanaLandingMetric, a special logic is applied where both the default http endpoint
    and an enhanced transaction endpoint (if available) are used to create separate metric
    instances, allowing for differentiated provider names and richer data collection.
    """

    _registry: dict[str, list[MetricRegistration]] = {}

    @classmethod
    def register(
        cls, blockchain_metrics: dict[str, list[tuple[type[BaseMetric], str]]]
    ) -> None:
        """Registers metric classes for blockchains."""
        for blockchain_name, metrics in blockchain_metrics.items():
            if blockchain_name not in cls._registry:
                cls._registry[blockchain_name] = []
            for metric in metrics:
                if isinstance(metric, tuple) and len(metric) == 2:
                    metric_class, metric_name = metric
                    cls._registry[blockchain_name].append(
                        MetricRegistration(metric_class, metric_name)
                    )
                else:
                    raise ValueError(
                        "Each metric must be a tuple (metric_class, metric_name)"
                    )

    @classmethod
    def create_metrics(
        cls,
        blockchain_name: str,
        metrics_handler: "MetricsHandler",  # type: ignore  # noqa: F821
        config: MetricConfig,
        **kwargs: dict,
    ) -> list[BaseMetric]:
        """Creates metric instances for a specific blockchain."""
        if blockchain_name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"No metric classes registered for blockchain '{blockchain_name}'. Available blockchains: {available}"
            )

        cls._setup_endpoint_config(config, kwargs)

        source_region: str = str(kwargs.get("source_region", "default"))
        target_region: str = str(kwargs.get("target_region", "default"))
        provider: str = str(kwargs.get("provider", "default"))

        metrics = []
        for registration in cls._registry[blockchain_name]:
            if registration.metric_class.__name__ == "SolanaLandingMetric":
                metrics.extend(
                    cls._create_solana_metrics(
                        blockchain_name,
                        registration.metric_class,
                        registration.metric_name,
                        metrics_handler,
                        config,
                        kwargs,
                        source_region,
                        target_region,
                        provider,
                    )
                )
            else:
                metrics.append(
                    cls._create_single_metric(
                        blockchain_name,
                        registration.metric_class,
                        registration.metric_name,
                        metrics_handler,
                        config,
                        kwargs,
                        source_region,
                        target_region,
                        provider,
                    )
                )

        return metrics

    @staticmethod
    def _setup_endpoint_config(config: MetricConfig, kwargs: dict) -> None:
        """Sets up endpoint configuration from kwargs."""
        config.endpoints = EndpointConfig(
            main_endpoint=kwargs.get("http_endpoint"),
            ws_endpoint=kwargs.get("ws_endpoint"),
        )

    @staticmethod
    def _create_solana_metrics(
        blockchain_name: str,
        metric_class: type[BaseMetric],
        metric_name: str,
        metrics_handler: "MetricsHandler",  # noqa: F821 # type: ignore
        config: MetricConfig,
        kwargs: dict,
        source_region: str,
        target_region: str,
        provider: str,
    ) -> list[BaseMetric]:
        """Creates SolanaLandingMetric-specific instances."""
        metrics = []

        # First instance using http_endpoint as main endpoint (already set)
        metrics.append(
            MetricFactory._create_single_metric(
                blockchain_name,
                metric_class,
                metric_name,
                metrics_handler,
                config,
                kwargs,
                source_region,
                target_region,
                provider,
            )
        )

        # Second instance using tx_endpoint as main endpoint and updated provider name
        if kwargs.get("tx_endpoint"):
            config_copy: MetricConfig = copy.deepcopy(config)
            config_copy.endpoints.main_endpoint = kwargs.get("tx_endpoint")
            metrics.append(
                MetricFactory._create_single_metric(
                    blockchain_name,
                    metric_class,
                    metric_name,
                    metrics_handler,
                    config_copy,
                    kwargs,
                    source_region,
                    target_region,
                    f"{provider}_tx",  # Modify provider name to differentiate
                )
            )

        return metrics

    @staticmethod
    def _create_single_metric(
        blockchain_name: str,
        metric_class: type[BaseMetric],
        metric_name: str,
        metrics_handler: "MetricsHandler",  # noqa: F821 # type: ignore
        config: MetricConfig,
        kwargs: dict,
        source_region: str,
        target_region: str,
        provider: str,
    ) -> BaseMetric:
        """Creates a single metric instance."""
        labels = MetricLabels(
            source_region=source_region,
            target_region=target_region,
            blockchain=blockchain_name,
            provider=provider,
        )

        metric_instance = metric_class(
            handler=metrics_handler,
            metric_name=metric_name,
            labels=labels,
            config=config,
            **kwargs.copy(),  # Modified: Added defensive copy
        )
        return metric_instance
