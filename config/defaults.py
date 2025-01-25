class MetricsServiceConfig:
    """Default configuration for metrics collection and processing."""
    
    # Grafana push settings
    GRAFANA_PUSH_MAX_RETRIES = 3
    GRAFANA_PUSH_RETRY_DELAY = 1
    GRAFANA_PUSH_TIMEOUT = 3
    
    # Metrics collection settings
    METRIC_REQUEST_TIMEOUT = 45
    METRIC_MAX_LATENCY = 45