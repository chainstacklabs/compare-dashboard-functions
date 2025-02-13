"""Factory for creating blockchain-specific metric instances."""

import copy
from typing import Dict, List, Tuple, Type

from common.base_metric import BaseMetric
from common.metric_config import EndpointConfig, MetricConfig, MetricLabels


class MetricFactory:
    """Creates metric instances for blockchains."""

    _registry: Dict[str, List[Tuple[Type[BaseMetric], str]]] = {}

    @classmethod
    def register(
        cls, blockchain_metrics: Dict[str, List[Tuple[Type[BaseMetric], str]]]
    ):
        """Registers metric classes for blockchains."""
        for blockchain_name, metrics in blockchain_metrics.items():
            if blockchain_name not in cls._registry:
                cls._registry[blockchain_name] = []
            for metric in metrics:
                if isinstance(metric, tuple) and len(metric) == 2:
                    metric_class, metric_name = metric
                    cls._registry[blockchain_name].append((metric_class, metric_name))
                else:
                    raise ValueError(
                        "Each metric must be a tuple (metric_class, metric_name)"
                    )

    @classmethod
    def create_metrics(
        cls,
        blockchain_name: str,
        metrics_handler: "MetricsHandler",  # type: ignore
        config: MetricConfig,
        **kwargs,
    ) -> List[BaseMetric]:
        if blockchain_name not in cls._registry:
            available = list(cls._registry.keys())
            raise ValueError(
                f"No metric classes registered for blockchain '{blockchain_name}'. Available blockchains: {available}"
            )

        source_region = kwargs.get("source_region", "default")
        target_region = kwargs.get("target_region", "default")
        provider = kwargs.get("provider", "default")

        config.endpoints = EndpointConfig(
            main_endpoint=kwargs.get("http_endpoint"),
            # tx_endpoint=kwargs.get("tx_endpoint"),
            ws_endpoint=kwargs.get("ws_endpoint"),
        )
        metrics = []

        for metric_class, metric_name in cls._registry[blockchain_name]:
            if metric_class.__name__ == "SolanaLandingMetric":
                metrics.extend(
                    cls._create_solana_metrics(
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
            else:
                metrics.append(
                    cls._create_single_metric(
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

        return metrics

    @staticmethod
    def _create_solana_metrics(
        blockchain_name,
        metric_class,
        metric_name,
        metrics_handler,
        config,
        kwargs,
        source_region,
        target_region,
        provider,
    ) -> List[BaseMetric]:
        """Creates SolanaLandingMetric-specific instances, handling both http_endpoint and tx_endpoint."""
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
            config_copy = copy.deepcopy(config)
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
        blockchain_name,
        metric_class,
        metric_name,
        metrics_handler,
        config,
        kwargs,
        source_region,
        target_region,
        provider,
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
            **kwargs,
        )
        return metric_instance
